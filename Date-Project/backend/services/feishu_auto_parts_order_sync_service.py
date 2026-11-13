"""飞书「汽配订单」eBay 仓未完成采购单同步（每天 08:00 / 13:00 / 18:00），供 eBay 补货2.0 的物流状态使用。

只拉 CTUebay 仓、未完成的单，都在飞书服务端过滤：
  - 订单状态 不是 已完成 且 不是 已取消（状态没填的单保留）；
  - 采购仓库 是名字里带 eBay（不区分大小写）的选项之一，AMZ 仓的单不要。「采购仓库」是单选字段，
    飞书不支持按文字片段筛单选（contains "ebay" 报 1254018 InvalidFilter），所以每次先读字段的选项，
    把带 eBay 的选项交给 contains；以后新增 eBay 仓选项会自动带上。
  一万多行的表只拉回不到三百行（2026-11-13 实测 282 行，与客户端筛选逐条一致）。
  已完成的单已经到了成都仓，后半段看领星库存明细。

为什么整表替换：
  采购单的状态、预计发货时间会被反复改，单一旦完成就要从本地消失。整表替换在一个
  事务里完成，失败回滚，库里始终是上一次成功的完整快照。

不用视图：视图的筛选条件会被人改掉，改了之后同步结果会悄悄变少。

字段名对不上时直接失败，不静默写空：飞书改了字段名，物流状态会整列变空且没人发现。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from uuid import uuid4

from backend.config import settings
from backend.integrations.feishu.client import FeishuClient, FeishuRequestError, field_text
from backend.repositories import feishu_auto_parts_order_repository as repo

TASK_CODE = "feishu_auto_parts_order_sync"
TASK_NAME = "飞书汽配订单同步"
CHINA = timezone(timedelta(hours=8))
LOG = logging.getLogger(__name__)

# 飞书字段名 -> 本地列名。必需字段缺了直接失败；可选字段缺了只记 warnings。
REQUIRED_FIELDS = {
    "实际采购SKU": "sku",
    "采购仓库": "warehouse",
    "订单状态": "order_status",
    "下单日期": "order_date",
    "预计发货时间": "expected_ship_date",
}
OPTIONAL_FIELDS = {
    "PO": "po",
    "数量": "quantity",
    "订单金额": "order_amount",
    "申购日期": "apply_date",
    "采购员 (人员 )": "purchaser",
    "品名": "product_name",
    "未采购原因": "not_purchased_reason",
}
DATE_COLUMNS = frozenset({"order_date", "expected_ship_date", "apply_date"})
NUMBER_COLUMNS = frozenset({"quantity", "order_amount"})
MAX_LENGTH = {"po": 64, "sku": 128, "warehouse": 64, "order_status": 32, "purchaser": 64,
              "product_name": 255, "not_purchased_reason": 255}
# 成都 eBay 中转仓 -> 补货2.0 的站点名（与库存同口径：德国 / 英国 / 美国）。
EBAY_SITE_BY_CODE = {"DE": "德国", "UK": "英国", "US": "美国"}
# 服务端过滤：只要还没走完采购流程的单。单选字段的 isNot 对空值成立，状态没填的单会保留。
OPEN_ORDER_FILTER = {"conjunction": "and", "conditions": [
    {"field_name": "订单状态", "operator": "isNot", "value": [status]} for status in repo.CLOSED_STATUSES
]}


def ebay_warehouse_options(fields: list[dict[str, Any]]) -> list[str]:
    """「采购仓库」单选字段里名字带 eBay 的选项（CTUeBay-DE中转仓 / CTUebay-UK中转仓 …）。"""
    for field in fields:
        if field.get("field_name") == "采购仓库":
            options = (field.get("property") or {}).get("options") or []
            return [str(o.get("name")) for o in options if "EBAY" in str(o.get("name") or "").upper()]
    return []


def order_filter(ebay_options: list[str]) -> dict[str, Any]:
    return {"conjunction": "and", "conditions": [
        *OPEN_ORDER_FILTER["conditions"],
        {"field_name": "采购仓库", "operator": "contains", "value": list(ebay_options)},
    ]}


# 飞书权限类失败的特征：HTTP 403、角色无权限（1254302）、文档无权限（91403）。
PERMISSION_MARKS = ("HTTP 403", "1254302", "91403")


class FeishuAutoPartsOrderSyncError(RuntimeError):
    """带 stage / metrics，调度器据此还原失败运行记录；不含任何凭证。"""

    def __init__(self, stage: str, message: str, metrics: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.metrics = dict(metrics or {})


def to_date(value):
    """飞书日期是毫秒时间戳，按北京时区换算；用本地时区的话跨零点会漂一天。"""
    if value in (None, "", []):
        return None
    try:
        return datetime.fromtimestamp(int(Decimal(str(value))) / 1000, CHINA).date()
    except (InvalidOperation, ValueError, TypeError, OverflowError, OSError):
        return None


def to_datetime(value):
    if value in (None, "", []):
        return None
    try:
        return datetime.fromtimestamp(int(Decimal(str(value))) / 1000, CHINA).replace(tzinfo=None)
    except (InvalidOperation, ValueError, TypeError, OverflowError, OSError):
        return None


def to_number(value):
    text = field_text(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def warehouse_site(warehouse: str | None) -> tuple[str | None, str | None]:
    """采购仓库 -> (平台, eBay 站点)。飞书里同一个仓有 CTUeBay-UK / CTUebay-UK 两种写法，统一按大写判断。"""
    name = str(warehouse or "").strip().upper()
    if not name:
        return None, None
    if "EBAY" in name:
        for code, site in EBAY_SITE_BY_CODE.items():
            if f"-{code}" in name:
                return "EBAY", site
        return "EBAY", None
    if "AMZ" in name:
        return "AMZ", None
    return None, None


def to_row(record: dict[str, Any], warnings: set[str], *, batch_id: str, synced_at: datetime) -> dict[str, Any]:
    fields = record.get("fields") or {}
    record_id = record.get("record_id")
    if not record_id:
        raise FeishuAutoPartsOrderSyncError("TRANSFORM", "飞书记录缺少record_id，无法作为主键，已中止未写库")
    row: dict[str, Any] = {"record_id": record_id}
    for name, column in {**REQUIRED_FIELDS, **OPTIONAL_FIELDS}.items():
        value = fields.get(name)
        if column in DATE_COLUMNS:
            row[column] = to_date(value)
        elif column in NUMBER_COLUMNS:
            row[column] = to_number(value)
        else:
            text = field_text(value).strip() or None
            limit = MAX_LENGTH.get(column)
            if text and limit and len(text) > limit:
                warnings.add(f"字段「{name}」有值超过{limit}字符，已截断入库")
                text = text[:limit]
            row[column] = text
    if row["sku"]:
        row["sku"] = row["sku"].upper()
    row["platform"], row["site"] = warehouse_site(row["warehouse"])
    row["feishu_updated_at"] = to_datetime(record.get("last_modified_time"))
    row["sync_batch_id"] = batch_id
    row["synced_at"] = synced_at
    return row


def sync_feishu_auto_parts_orders(*, client_factory: Callable[[], FeishuClient] = FeishuClient) -> dict[str, Any]:
    app_token = settings.feishu_auto_parts_order_app_token.strip()
    table_id = settings.feishu_auto_parts_order_table_id.strip()
    if not app_token or not table_id:
        raise FeishuAutoPartsOrderSyncError(
            "CONFIG", "请先配置FEISHU_AUTO_PARTS_ORDER_APP_TOKEN和FEISHU_AUTO_PARTS_ORDER_TABLE_ID")
    batch_id = str(uuid4())
    synced_at = datetime.now(CHINA).replace(tzinfo=None)
    metrics = {"sync_batch_id": batch_id, "extract_rows": 0, "ods_rows": 0}
    try:
        with client_factory() as client:
            fields = client.list_fields(app_token, table_id)
            names = {f.get("field_name") for f in fields}
            missing = [name for name in REQUIRED_FIELDS if name not in names]
            if missing:
                raise FeishuAutoPartsOrderSyncError(
                    "EXTRACT", f"飞书汽配订单缺少字段：{'、'.join(missing)}（字段可能被改名），已中止未写库", metrics)
            ebay_options = ebay_warehouse_options(fields)
            if not ebay_options:
                raise FeishuAutoPartsOrderSyncError(
                    "EXTRACT", "飞书「采购仓库」没有名字带 eBay 的选项（选项可能被改名），已中止未写库", metrics)
            records = client.fetch_records(app_token, table_id, "", automatic_fields=True,
                                           filter=order_filter(ebay_options))
    except FeishuRequestError as exc:
        # 只有权限类错误才提示去高级权限里授权，其他错误（飞书临时故障等）别误导人去改权限。
        hint = ("（高级权限下需在角色里给应用「店铺巡查」授权这张表）"
                if any(mark in str(exc) for mark in PERMISSION_MARKS) else "")
        raise FeishuAutoPartsOrderSyncError("EXTRACT", f"拉取飞书汽配订单失败；{exc}{hint}", metrics) from None
    metrics["extract_rows"] = len(records)
    warnings = {f"飞书缺少可选字段「{name}」，该列本次为空" for name in OPTIONAL_FIELDS if name not in names}
    if not records:
        # 平时有几百张未完成的单，突然一张都没有，多半是权限被收回、字段选项被改名或表被清空；
        # 不能拿空结果把本地整表删光。
        raise FeishuAutoPartsOrderSyncError(
            "EXTRACT", "飞书汽配订单 eBay 仓未完成采购单返回0行，疑似权限变化、选项改名或表被清空，未写库", metrics)
    rows = [to_row(record, warnings, batch_id=batch_id, synced_at=synced_at) for record in records]
    leaked = sum(1 for row in rows if (row["order_status"] or "") in repo.CLOSED_STATUSES)
    not_ebay = sum(1 for row in rows if row["platform"] != "EBAY")
    if leaked or not_ebay:
        raise FeishuAutoPartsOrderSyncError(
            "TRANSFORM", f"飞书过滤后仍返回{leaked}条已完成/已取消、{not_ebay}条非 eBay 仓的单，"
                         "过滤条件可能失效，已中止未写库", metrics)
    if len({row["record_id"] for row in rows}) != len(rows):
        raise FeishuAutoPartsOrderSyncError("TRANSFORM", "飞书返回了重复的record_id，疑似翻页游标异常，已中止未写库", metrics)
    try:
        stored = repo.replace_all(rows)
    except Exception as exc:
        raise FeishuAutoPartsOrderSyncError("LOAD", f"写入飞书汽配订单失败，已回滚：{exc}", metrics) from exc
    ebay_rows = [row for row in rows if row["platform"] == "EBAY"]
    unknown_site = sum(1 for row in ebay_rows if row["site"] is None)
    if unknown_site:
        warnings.add(f"{unknown_site} 条 eBay 仓订单认不出站点（仓库名不含 -DE / -UK / -US），不会显示到补货2.0")
    result = {
        "task_code": TASK_CODE, "fetched_rows": len(rows), "ebay_rows": len(ebay_rows),
        "ebay_open_rows": sum(1 for row in ebay_rows if row["site"]),
        **stored,
        "sync_batch_id": batch_id, "extract_rows": len(rows), "ods_rows": stored["inserted_rows"],
        "warnings": sorted(warnings),
    }
    LOG.info("飞书汽配订单同步完成 拉取=%s eBay=%s 认出站点=%s 删除旧行=%s",
             result["fetched_rows"], result["ebay_rows"], result["ebay_open_rows"], result["deleted_rows"])
    return result
