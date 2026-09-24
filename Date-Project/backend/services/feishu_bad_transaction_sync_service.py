"""飞书「不良交易刊登」增量同步。

增量怎么做：
  飞书多维表格没有"改动游标"这种东西，也不能按更新时间做服务端过滤——这张表里
  没有可见的「最后更新时间」字段，records/search 的 filter 只能过滤可见字段。
  所以增量落在两处：

  1. 取数端：只拉当月（实测2026-09是1630行，全表10722行），不是每周重拉全表。
  2. 写库端：按飞书 record_id upsert，并比对内容指纹；内容没变的行只更新
     last_synced_at，不改业务列、不动 last_changed_at。所以能分清
     「新增 / 更新 / 没变」，而不是每次全表重写。

  接口带 automatic_fields=True，顺带取回每条的 created_time / last_modified_time
  存下来，方便之后追"这条是哪天被业务改的"。

取数范围：默认只拉**当月**（按登记日期做服务端过滤），一个月4~5批。
既覆盖本周新增，也带上业务方回头改的同月历史批次，而不用把整表一万多行重拉。
不依赖视图——视图的筛选条件会被人改掉，实测业务方重传整表之后它就失效了，
每周变成全表拉取。

清理范围跟着取数范围走：按月拉就按月对齐（该月库里有、本次没拉到的删掉），
全量拉就整表对齐（含登记日期为空的行）。绝不会动没拉到的月份。
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from backend.config import settings
from backend.integrations.feishu.client import FeishuClient, FeishuRequestError, field_text
from backend.repositories import feishu_bad_transaction_repository as repo

TASK_CODE = "feishu_bad_transaction_sync"
TASK_NAME = "飞书不良交易刊登每周同步"
CHINA = timezone(timedelta(hours=8))
LOG = logging.getLogger(__name__)

# 飞书字段名 -> 本地列名。改飞书字段名会让这里对不上，同步会把该列当缺失记进
# warnings，而不是静默丢数据。
FIELD_MAP = {
    "登记日期": "reg_date",
    "店铺": "shop",
    "评估日期": "evaluate_date",
    "物品编号": "item_id",
    "刊登标题": "title",
    "刊登状态：Y=在线，N=已下线": "listing_status",
    "SKU": "sku",
    "总交易额": "total_amount",
    "总交易量": "total_qty",
    "不良交易量": "defect_qty",
    "物品未收到纠纷数量": "inr_qty",
    "物品与描述不符退货数量": "snad_qty",
    "中差评数量": "neutral_negative_qty",
    "物品描述评分低分数量": "low_dsr_qty",
    "因缺货而取消的交易数量": "oos_cancel_qty",
    "不良交易率": "defect_rate",
    "父记录": "parent_json",
    "字段 1": "spare_date_1",
    "字段 2": "spare_date_2",
    "字段 3": "spare_date_3",
    "字段 4": "spare_text_4",
    "字段 5": "spare_text_5",
    "字段 6": "spare_text_6",
    "字段 7": "spare_text_7",
    "字段 8": "spare_text_8",
}
DATE_COLUMNS = frozenset({"reg_date", "spare_date_1", "spare_date_2", "spare_date_3"})
JSON_COLUMNS = frozenset({"parent_json"})
# 列宽见迁移脚本；超长按列宽截断而不是让MySQL报错整批回滚，同时记进warnings。
MAX_LENGTH = {
    "shop": 128, "evaluate_date": 32, "item_id": 32, "title": 255, "listing_status": 8,
    "sku": 64, "total_amount": 32, "total_qty": 16, "defect_qty": 16, "inr_qty": 16,
    "snad_qty": 16, "neutral_negative_qty": 16, "low_dsr_qty": 16, "oos_cancel_qty": 16,
    "defect_rate": 16, "spare_text_4": 64, "spare_text_5": 64, "spare_text_6": 64,
    "spare_text_7": 64, "spare_text_8": 64,
}


class FeishuBadTransactionSyncError(RuntimeError):
    """对外的失败原因；不含任何凭证。"""


def to_date(value):
    """飞书日期字段给的是毫秒时间戳，按北京时区换算成日期。

    时区必须显式指定：用本地时区的话，服务器时区一变，跨零点的日期就会漂一天。
    """
    if value in (None, "", []):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000, CHINA).date()


def to_datetime(value):
    if value in (None, "", []):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000, CHINA).replace(tzinfo=None)


def to_row(record, warnings):
    """把一条飞书记录转成本地表的一行。未知字段记进warnings，不静默丢弃。"""
    fields = record.get("fields") or {}
    for name in fields:
        if name not in FIELD_MAP:
            warnings.add(f"飞书新增了未映射的字段「{name}」，本次未入库")
    row = {"record_id": record.get("record_id")}
    if not row["record_id"]:
        raise FeishuBadTransactionSyncError("飞书记录缺少record_id，无法作为主键，已中止")
    for name, column in FIELD_MAP.items():
        value = fields.get(name)
        if column in DATE_COLUMNS:
            row[column] = to_date(value)
        elif column in JSON_COLUMNS:
            # 关联字段是对象，空对象按NULL存，别拿"{}"占位。
            row[column] = repo.dumps(value) if value not in (None, "", [], {}) else None
        else:
            text = field_text(value) or None
            limit = MAX_LENGTH.get(column)
            if text and limit and len(text) > limit:
                warnings.add(f"字段「{name}」有值超过{limit}字符，已截断入库")
                text = text[:limit]
            row[column] = text
    row["feishu_created_at"] = to_datetime(record.get("created_time"))
    row["feishu_updated_at"] = to_datetime(record.get("last_modified_time"))
    row["content_hash"] = repo.content_hash(row)
    return row


def month_filter(month):
    """按「登记日期」落在某个统计月份做服务端过滤。

    日期字段没有"属于某月"的算子，用 ExactDate 夹出一个左闭右开区间：
    isGreater 给上月最后一天（等价于 >= 本月1号），isLess 给下月1号。
    这样每周只拉当月那几批，不用把整表10000多行重拉一遍。
    """
    year, mon = int(month[:4]), int(month[5:7])
    start = date(year, mon, 1)
    nxt = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
    stamp = lambda d: str(int(datetime(d.year, d.month, d.day, tzinfo=CHINA).timestamp() * 1000))
    return {"conjunction": "and", "conditions": [
        {"field_name": "登记日期", "operator": "isGreater",
         "value": ["ExactDate", stamp(start - timedelta(days=1))]},
        {"field_name": "登记日期", "operator": "isLess", "value": ["ExactDate", stamp(nxt)]},
    ]}


def sync_feishu_bad_transactions(*, full=False, month=""):
    """同步一次。

    full=True 拉全表（首次回填、或需要整表对齐时用）；
    否则只拉某个统计月份，默认当月——源表每周三更新一批，一个月4~5批，
    拉当月既能覆盖本周新增，也能带上业务方回头修改的同月历史批次。
    """
    app_token = settings.feishu_bad_transaction_app_token
    table_id = settings.feishu_bad_transaction_table_id
    if not app_token or not table_id:
        raise FeishuBadTransactionSyncError(
            "请先配置FEISHU_BAD_TRANSACTION_APP_TOKEN和FEISHU_BAD_TRANSACTION_TABLE_ID")
    month = "" if full else (month.strip() or datetime.now(CHINA).strftime("%Y-%m"))
    if month and not re.fullmatch(r"\d{4}-\d{2}", month):
        raise FeishuBadTransactionSyncError(f"统计月份格式应为YYYY-MM，收到：{month}")

    warnings = set()
    started = datetime.now(CHINA).replace(tzinfo=None)
    batch_id = str(uuid4())
    try:
        with FeishuClient() as client:
            # 不再依赖视图：视图的筛选条件会被人改掉（实测重传整表后就失效了），
            # 按登记日期过滤是确定的。
            records = client.fetch_records(app_token, table_id, "", automatic_fields=True,
                                           filter=None if full else month_filter(month))
    except FeishuRequestError as exc:
        raise FeishuBadTransactionSyncError(f"拉取飞书不良交易刊登失败；{exc}") from None

    rows = [to_row(record, warnings) for record in records]
    seen = {row["record_id"] for row in rows}
    if len(seen) != len(rows):
        raise FeishuBadTransactionSyncError("飞书返回了重复的record_id，疑似翻页游标异常，已中止未写库")
    # 只清理本次真正拉到的那些批次；登记日期为空的记录归不到批次，不参与清理。
    batches = sorted({row["reg_date"] for row in rows if row["reg_date"]})

    # 全量拉取时按整表对齐：飞书删掉的行本地也要删，包括登记日期为空、
    # 归不到批次的那些。只拉视图时绝不能这么做，会把没拉的历史批次删光。
    metrics = repo.upsert(rows, batches=batches, synced_at=started, full=full, month=month)
    result = {
        "task_code": TASK_CODE, "mode": "FULL" if full else "MONTH", "stat_month": month,
        "fetched_rows": len(rows), "batches": [str(b) for b in batches],
        **metrics,
        # 调度框架记录运行结果时直接下标取这三个键（不是 .get），少一个就 KeyError，
        # 表现为任务报 HTTP 502「内部任务执行失败: 'extract_rows'」——
        # 而数据其实已经在上面那个事务里提交了，只是运行记录没写成。
        "sync_batch_id": batch_id,
        "extract_rows": len(rows),
        "ods_rows": metrics["inserted_rows"] + metrics["updated_rows"] + metrics["unchanged_rows"],
        "warnings": sorted(warnings),
    }
    LOG.info("飞书不良交易刊登同步完成 mode=%s 拉取=%s 新增=%s 更新=%s 未变=%s 删除=%s",
             result["mode"], result["fetched_rows"], metrics["inserted_rows"],
             metrics["updated_rows"], metrics["unchanged_rows"], metrics["deleted_rows"])
    return result
