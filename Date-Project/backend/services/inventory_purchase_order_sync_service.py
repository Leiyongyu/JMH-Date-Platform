"""Read Lingxing purchase orders; atomically publish the current report's transit."""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.integrations.lingxing.client import LingXingClient
from backend.parsers.inventory_report_purchase_order_parser import purchase_warehouse_assignment
from backend.parsers.performance_common import money
from backend.repositories import inventory_purchase_order_api_repository as repo
from backend.repositories import inventory_report_etl_repository as report_repo
from backend.repositories.performance_repository import named_lock
from backend.services.inventory_report_etl_service import publish_inventory_report_purchase_order
from backend.services.weekly_inventory_api import MAX_ATTEMPTS, RETRY_BUSINESS, _retry_delay, _transport_failure

TASK_CODE = repo.TASK_CODE
TASK_NAME = "月度库存采购在途同步"
API = "erp/sc/routing/data/local_inventory/purchaseOrderList"
PAGE_SIZE = 500
FULL_START = "2000-01-01"  # Earlier than Lingxing's service inception; never a rolling 30/90-day cut-off.
ORDER_FIELDS = ("order_sn", "custom_order_sn", "status", "status_shipped", "wid",
                "ware_house_name", "create_time", "update_time", "purchase_currency")
ITEM_FIELDS = ("id", "sku", "wid", "ware_house_name", "sid", "price", "tax_rate",
               "quantity_receive", "quantity_real", "quantity_entry", "is_delete")


class PurchaseOrderSyncError(ValueError):
    def __init__(self, message, *, stage="EXTRACT", metrics=None):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics or {}


def now_shanghai():
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def current_source_month(now=None):
    now = now or now_shanghai()
    return (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _request(client, body):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        time.sleep(1.1)  # One-token bucket; do not parallelize pages.
        retry_after = None
        try:
            response = client.post_signed_query_auth(API, dict(body))
        except Exception as exc:
            retryable, retry_after, _ = _transport_failure(exc, client)
            detail = f"传输错误 {type(exc).__name__}"
        else:
            code = str(response.get("code")) if isinstance(response, dict) else "invalid"
            if code == "0" and isinstance(response.get("data"), list):
                return response
            retryable = code in RETRY_BUSINESS
            # Do not persist upstream messages, URLs or response bodies.
            detail = f"业务错误码 {code}" if code.isdecimal() else "接口响应格式错误"
        if retryable and attempt < MAX_ATTEMPTS:
            delay = _retry_delay(attempt, retry_after)
            if delay is not None:
                time.sleep(delay)
                continue
        raise PurchaseOrderSyncError(f"采购单查询失败：{detail}，offset={body['offset']}")


def _integer(value, field):
    text = str(value)
    if isinstance(value, bool) or not text.isascii() or not text.isdecimal():
        raise ValueError(f"采购单{field}缺失或不是非负整数")
    return int(text)


def _decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"采购单{field}缺失或不是数字") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"采购单{field}必须是有限非负数")
    return result


def _text(value):
    return str(value or "").strip()


def fetch_orders(client, start_date, end_date, *, full):
    offset, expected = 0, None
    orders = {}
    while True:
        body = {"start_date": start_date, "end_date": end_date,
                "search_field_time": "create_time" if full else "update_time",
                "offset": offset, "length": PAGE_SIZE}
        # status is a response field, not a documented request filter.
        response = _request(client, body)
        total = _integer(response.get("total"), "total")
        if expected is None:
            expected = total
        elif total != expected:
            raise ValueError("采购单分页total发生变化，保留旧数据，请重试")
        page = response["data"]
        if len(page) != min(PAGE_SIZE, total - offset):
            raise ValueError("采购单分页不完整，保留旧数据")
        for source in page:
            if not isinstance(source, dict):
                raise ValueError("采购单格式错误")
            order_sn = _text(source.get("order_sn"))
            if not order_sn or len(order_sn) > 100 or order_sn in orders:
                raise ValueError("采购单系统单号缺失、过长或重复，拒绝覆盖")
            _integer(source.get("status"), "status")
            items = source.get("item_list")
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError(f"采购单 {order_sn} 缺少商品明细")
            clean = {field: source.get(field) for field in ORDER_FIELDS}
            clean["order_sn"] = order_sn
            clean["item_list"] = [{field: item.get(field) for field in ITEM_FIELDS} for item in items]
            orders[order_sn] = clean
        offset += len(page)
        if offset == total:
            break
    if full and not orders:
        raise ValueError("采购单全量返回空数据，拒绝清空；请检查接口授权")
    return orders


def transform_orders(orders, month, batch_id, shops):
    rows, active_orders = [], []
    excluded = Counter()
    deleted = 0
    for order in orders.values():
        if _integer(order.get("status"), "status") != 2:
            continue
        active_orders.append(order)
        if not order["item_list"]:
            raise ValueError(f"待到货采购单 {order['order_sn']} 没有明细")
        seen = set()
        for item in order["item_list"]:
            item_id = _text(item.get("id"))
            if not item_id or item_id in seen:
                raise ValueError(f"采购单 {order['order_sn']} 明细ID缺失或重复")
            seen.add(item_id)
            is_delete = _integer(item.get("is_delete"), "is_delete")
            if is_delete not in (0, 1):
                raise ValueError("采购明细删除标记不是0或1")
            if is_delete:
                deleted += 1
                continue
            quantity = _decimal(item.get("quantity_receive"), "待到货量")
            warehouse = _text(item.get("ware_house_name"))
            if not warehouse:
                if item.get("wid") and str(item["wid"]) != str(order.get("wid")):
                    raise ValueError(f"采购单 {order['order_sn']} 明细仓库名称缺失，不能回退到其他仓库")
                warehouse = _text(order.get("ware_house_name"))
            if not warehouse:
                raise ValueError("采购单仓库名称缺失")
            try:
                platform, group, department = purchase_warehouse_assignment(warehouse)
            except ValueError:
                excluded[warehouse] += 1
                continue
            if _text(order.get("purchase_currency")).upper() != "CNY":
                raise ValueError(f"采购单 {order['order_sn']} 不是人民币，不能直接合计为人民币成本")
            price = _decimal(item.get("price"), "含税单价")
            tax = _decimal(item.get("tax_rate"), "税率")
            if tax > 100:
                raise ValueError("采购单税率超出0到100范围")
            price = (price / (1 + tax / 100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            sku = _text(item.get("sku"))
            if not sku or len(sku) > 255:
                raise ValueError("采购单SKU缺失或过长")
            sid = str(_integer(item.get("sid") or 0, "sid"))
            store = shops.get(sid) if sid != "0" else None
            if sid != "0" and not store:
                raise ValueError(f"采购单店铺SID {sid} 无法对应店铺，请先同步店铺数据")
            rows.append({"stat_month": month, "purchase_order_no": order["order_sn"],
                         "purchase_warehouse": _text(order.get("ware_house_name")) or warehouse,
                         "purchase_warehouse_detail": warehouse, "sku": sku, "store_name": store,
                         "unit_price": price, "pending_arrival_qty": quantity,
                         "sku_pending_total_cost": money(price * quantity), "product_dimension": None,
                         "platform_code": platform, "group_code": group, "department_code": department,
                         "source_file_name": "领星API:purchaseOrderList", "source_sheet": "item_list",
                         "source_row": len(rows) + 1, "import_batch_id": batch_id, "imported_by": "API"})
    if not rows and excluded:
        raise ValueError("全部待到货明细的仓库均无法映射，拒绝清空月报")
    return {
        "stat_month": month, "batch_id": batch_id, "rows": rows,
        "source_rows": sum(len(order["item_list"]) for order in active_orders),
        "skipped_rows": sum(excluded.values()) + deleted,
        "excluded_warehouses": dict(excluded), "active_orders": active_orders,
        "total_pending_arrival_qty": sum((r["pending_arrival_qty"] for r in rows), Decimal(0)),
        "total_pending_cost": sum((r["sku_pending_total_cost"] for r in rows), Decimal(0)),
    }


def _require_current_report(month):
    if month != current_source_month():
        raise ValueError("采购单接口仅提供当前状态，禁止覆盖历史月份；请在当前报表月份同步")
    snapshot = report_repo.view_snapshot(month, "GROUP")
    if snapshot and snapshot.get("historical_import"):
        raise ValueError("该月份是历史导入快照，不能使用实时采购单覆盖")


def sync_purchase_orders():
    pulled_at = now_shanghai()
    month = current_source_month(pulled_at)
    batch_id = str(uuid4())
    metrics = {"sync_batch_id": batch_id, "extract_rows": 0, "ods_rows": 0}
    stage = "EXTRACT"
    try:
        _require_current_report(month)
        previous = repo.state()
        full = not previous or pulled_at - previous["full_pulled_at"] >= timedelta(days=7)
        start = FULL_START if full else (previous["pulled_at"] - timedelta(days=2)).strftime("%Y-%m-%d")
        changed = fetch_orders(LingXingClient(max_retries=0), start, pulled_at.strftime("%Y-%m-%d"), full=full)
        metrics["extract_rows"] = len(changed)
        orders = {} if full else repo.cached_orders()
        if not full and not orders:
            raise ValueError("采购单增量缓存为空，请检查缓存与同步水位")
        # Replace entire orders: finished/cancelled orders and deleted/missing lines leave transit.
        orders.update(changed)
        stage = "TRANSFORM"
        parsed = transform_orders(orders, month, batch_id, repo.shop_map())
        stage = "LOAD"
        with named_lock(f"inventory:monthly-report-source:{month}") as acquired:
            if not acquired:
                raise ValueError("该月份正在计算或导入，请稍后重试采购在途同步")
            _require_current_report(month)  # Also rejects a long sync crossing midnight/month-end.
            with report_repo.purchase_order_transaction() as connection:
                result = publish_inventory_report_purchase_order(parsed)
                result.update(metrics)
                result.update({"ods_rows": len(parsed["rows"]), "mode": "FULL" if full else "INCREMENTAL",
                               "pulled_at": pulled_at.isoformat(sep=" "), "report_month": pulled_at.strftime("%Y-%m"),
                               "order_count": len(parsed["active_orders"]), "excluded_warehouses": parsed["excluded_warehouses"],
                               "query_start": start, "query_end": pulled_at.strftime("%Y-%m-%d")})
                repo.publish_cache(connection, changed, full=full, pulled_at=pulled_at, batch_id=batch_id,
                                   previous_state=previous, stat_month=month, result=result, active_orders=parsed["active_orders"])
        return result
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise PurchaseOrderSyncError(f"采购在途同步失败（{stage}）：{detail}", stage=stage, metrics=metrics) from None
