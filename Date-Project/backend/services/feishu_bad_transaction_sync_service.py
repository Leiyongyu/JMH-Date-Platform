"""飞书「不良交易刊登」增量同步。

增量怎么做：
  飞书多维表格没有"改动游标"这种东西，也不能按更新时间做服务端过滤——这张表里
  没有可见的「最后更新时间」字段，records/search 的 filter 只能过滤可见字段。
  所以增量落在两处：

  1. 取数端：默认只拉业务方配的那个视图。该视图筛的是当周那一批（实测370条，
     全表10655条），一次请求就够，不是每周把26周的历史重新拉一遍。
  2. 写库端：按飞书 record_id upsert，并比对内容指纹；内容没变的行只更新
     last_synced_at，不改业务列、不动 last_changed_at。所以能分清
     「新增 / 更新 / 没变」，而不是每次全表重写。

  接口带 automatic_fields=True，顺带取回每条的 created_time / last_modified_time
  存下来，方便之后追"这条是哪天被业务改的"。

同批次内消失的记录：本次拉到的登记日期批次里，库里有、飞书没有的记录会被删掉
（业务方在飞书删了行，本地要跟着删）。其他批次一行不碰；登记日期为空的记录
只 upsert、不参与这个清理，因为它们归不到任何批次。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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


def sync_feishu_bad_transactions(*, full=False):
    """同步一次。full=True 拉全表（首次回填用），否则只拉视图那一批。"""
    app_token = settings.feishu_bad_transaction_app_token
    table_id = settings.feishu_bad_transaction_table_id
    view_id = "" if full else settings.feishu_bad_transaction_view_id
    if not app_token or not table_id:
        raise FeishuBadTransactionSyncError(
            "请先配置FEISHU_BAD_TRANSACTION_APP_TOKEN和FEISHU_BAD_TRANSACTION_TABLE_ID")
    if not full and not view_id:
        raise FeishuBadTransactionSyncError(
            "增量同步要靠视图筛出当周那一批；请配置FEISHU_BAD_TRANSACTION_VIEW_ID，或用全量回填")

    warnings = set()
    started = datetime.now(CHINA).replace(tzinfo=None)
    try:
        with FeishuClient() as client:
            records = client.fetch_records(app_token, table_id, view_id, automatic_fields=True)
    except FeishuRequestError as exc:
        raise FeishuBadTransactionSyncError(f"拉取飞书不良交易刊登失败；{exc}") from None

    rows = [to_row(record, warnings) for record in records]
    seen = {row["record_id"] for row in rows}
    if len(seen) != len(rows):
        raise FeishuBadTransactionSyncError("飞书返回了重复的record_id，疑似翻页游标异常，已中止未写库")
    # 只清理本次真正拉到的那些批次；登记日期为空的记录归不到批次，不参与清理。
    batches = sorted({row["reg_date"] for row in rows if row["reg_date"]})

    metrics = repo.upsert(rows, batches=batches, synced_at=started)
    result = {
        "task_code": TASK_CODE, "mode": "FULL" if full else "VIEW",
        "fetched_rows": len(rows), "batches": [str(b) for b in batches],
        **metrics, "warnings": sorted(warnings),
    }
    LOG.info("飞书不良交易刊登同步完成 mode=%s 拉取=%s 新增=%s 更新=%s 未变=%s 删除=%s",
             result["mode"], result["fetched_rows"], metrics["inserted_rows"],
             metrics["updated_rows"], metrics["unchanged_rows"], metrics["deleted_rows"])
    return result
