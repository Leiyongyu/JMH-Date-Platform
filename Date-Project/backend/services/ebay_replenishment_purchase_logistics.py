"""补货2.0「物流状态」：SKU 从采购下单 → 成都仓 → 谷仓的完整链路。

三段数据，读取时实时附加，不写进补货计算结果（采购单状态一天变好几次，放进结果表就得跟着重算整版补货）：
  1. 采购下单 → 发货（飞书「汽配订单」，同步时已只留未完成的单）：
     按采购仓库认站点，站点 + 完整 SKU 精确匹配（SKU 不区分大小写）；一个 SKU 可以有多张单，
     按订单状态汇总单数和件数，悬停看每张单的 PO、数量、下单日期、预计发货时间。
  2. 到成都仓（领星库存明细 inventoryDetails，成都 eBay-DE / UK / US 中转仓）：
     product_qc_num 待检待上架量 = 已到成都仓、等待质检上架；
     product_valid_num 可用量 = 已上架、可以直接使用。
  3. 成都仓 → 谷仓（同一接口，谷仓德国 / 英国 / 美国新泽西 / 美国加州，美国两个仓合并）：
     product_lock_num 可用锁定量 = 准备发往谷仓；
     product_onway 调拨在途 = 在路上、待到谷仓；
     product_valid_num 可用量 = 已到谷仓。

只给 SKU 行附加；站点、品牌＋中间码汇总行不显示。预计发货时间早于今天（北京时间）仍未完成的单标记为逾期。
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from pymysql.err import ProgrammingError

from backend.repositories import ebay_replenishment_v2_repository as replenishment_repo
from backend.repositories import feishu_auto_parts_order_repository as repo
from backend.services.ebay_inventory_shared import _CHENGDU_WIDS, _INVENTORY_SITE_BY_WID, _OVERSEAS_WIDS
from backend.services.ebay_replenishment_periods import reference_today

FIELD = "purchase_logistics"
NO_STATUS = "状态未填"
# 采购单状态固定按这个顺序全部列出（没有的显示 0）；越靠后越接近发货。表里出现新状态时排在后面。
STATUS_ORDER = ("已下单", "待付款", "已付款", "待发货", NO_STATUS)
# 库存项：(键, 所属物流阶段, 名称, 单元格简称)。
STOCK_STAGES = (
    ("chengdu_pending_qc", "to_chengdu", "成都待检待上架", "待上架"),
    ("chengdu_available", "to_chengdu", "成都可用", "成都可用"),
    ("goodcang_locked", "to_goodcang", "准备发往谷仓（可用锁定）", "待发谷仓"),
    ("goodcang_onway", "to_goodcang", "调拨在途（待到谷仓）", "在途谷仓"),
    ("goodcang_available", "to_goodcang", "已到谷仓（谷仓可用）", "谷仓可用"),
)
PHASES = (("to_chengdu", "采购下单 → 成都仓"), ("to_goodcang", "成都仓 → 谷仓"))
# (键, 仓库组, 库存明细列)
STOCK_COLUMNS = (
    ("chengdu_pending_qc", _CHENGDU_WIDS, "product_qc_num"),
    ("chengdu_available", _CHENGDU_WIDS, "product_valid_num"),
    ("goodcang_locked", _OVERSEAS_WIDS, "product_lock_num"),
    ("goodcang_onway", _OVERSEAS_WIDS, "product_onway"),
    ("goodcang_available", _OVERSEAS_WIDS, "product_valid_num"),
)


def _is_sku_item(item: dict[str, Any]) -> bool:
    return item.get("node_kind") in (None, "sku")


def _number(value) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _quantity(value) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return format(number.quantize(Decimal(1)) if number == number.to_integral_value() else number.normalize(), "f")


def _date(value) -> str | None:
    return value.isoformat() if value is not None else None


def _sum(values) -> Decimal | None:
    known = [value for value in values if value is not None]
    return sum(known, Decimal(0)) if known else None


def build(rows: list[dict[str, Any]], today, stock: dict[str, Decimal | None] | None = None) -> dict[str, Any] | None:
    """一个 SKU 的未完成采购单 + 成都仓 / 谷仓库存 -> 两个物流阶段；三段都没有时返回 None。

    两个阶段的每一项都固定列出，没有数据按 0 显示：
      采购下单 → 成都仓：已下单 / 待付款 / 已付款 / 待发货 / 状态未填（单数 + 件数），成都待检待上架、成都可用；
      成都仓 → 谷仓：准备发往谷仓（可用锁定）、调拨在途（待到谷仓）、已到谷仓（谷仓可用）。
    rows 已按预计发货时间排好序。
    """
    stock = stock or {}
    if not rows and not any(stock.get(key) for key, *_ in STOCK_STAGES):
        return None
    orders, counts, quantities = [], defaultdict(int), defaultdict(lambda: Decimal(0))
    for row in rows:
        status = (row.get("order_status") or "").strip() or NO_STATUS
        expected = row.get("expected_ship_date")
        counts[status] += 1
        quantities[status] += _number(row.get("quantity")) or Decimal(0)
        orders.append({
            "po": row.get("po"),
            "order_status": status,
            "quantity": _quantity(row.get("quantity")),
            "order_date": _date(row.get("order_date")),
            "expected_ship_date": _date(expected),
            "purchaser": row.get("purchaser"),
            "overdue": expected is not None and expected < today,
        })
    statuses = [*STATUS_ORDER, *sorted(set(counts) - set(STATUS_ORDER))]
    phase_items = {key: [] for key, _ in PHASES}
    for status in statuses:
        phase_items["to_chengdu"].append({"key": "purchase", "label": status, "order_count": counts[status],
                                          "quantity": _quantity(quantities[status])})
    for key, phase, label, _short in STOCK_STAGES:
        phase_items[phase].append({"key": key, "label": label, "order_count": None,
                                   "quantity": _quantity(stock.get(key) or Decimal(0))})
    phases = []
    for key, label in PHASES:
        items = phase_items[key]
        phases.append({"key": key, "label": label, "items": items,
                       "order_count": sum(i["order_count"] or 0 for i in items),
                       "quantity": _quantity(sum((Decimal(i["quantity"]) for i in items), Decimal(0)))})
    parts = [f"{status}{counts[status]}单{_quantity(quantities[status])}件" for status in statuses if counts[status]]
    parts += [f"{short}{_quantity(stock[key])}件" for key, _phase, _label, short in STOCK_STAGES if stock.get(key)]
    expected_dates = [o["expected_ship_date"] for o in orders if o["expected_ship_date"]]
    return {
        "order_count": len(orders),
        "total_quantity": _quantity(sum(quantities.values(), Decimal(0))),
        # 全链路合计：两个阶段件数相加；领星里锁定量与可用量互不包含，不会重复。
        "chain_total_quantity": _quantity(sum((Decimal(p["quantity"]) for p in phases), Decimal(0))),
        "status_summary": " · ".join(parts),
        "earliest_expected_ship_date": min(expected_dates) if expected_dates else None,
        "overdue_count": sum(1 for o in orders if o["overdue"]),
        "phases": phases,
        "orders": orders,
    }


def warehouse_stock(cursor, pairs: list[tuple[str, str]]) -> tuple[dict[tuple[str, str], dict], Any]:
    """成都 eBay 中转仓与谷仓按 (站点, SKU 大写) 汇总各阶段库存，并返回这些仓最近一次同步时间。

    某阶段在该 SKU 的仓里整列为空（如待检量在 Java 补存之前同步的数据）时为 None，不当 0。
    """
    all_wids = (*_CHENGDU_WIDS, *_OVERSEAS_WIDS)
    wids = ",".join(f"'{wid}'" for wid in all_wids)
    site_case = " ".join(f"WHEN '{wid}' THEN '{_INVENTORY_SITE_BY_WID[wid]}'" for wid in all_wids)
    table = f"`{replenishment_repo._source_database()}`.warehouse_inventory_detail"
    cursor.execute(f"SELECT MAX(sync_time) synced_at FROM {table} WHERE wid IN ({wids})")
    synced_at = (cursor.fetchone() or {}).get("synced_at")
    columns, aggregates = [], []
    for key, group, column in STOCK_COLUMNS:
        group_wids = ",".join(f"'{wid}'" for wid in group)
        columns.append(f"CASE WHEN wid IN ({group_wids}) THEN CAST(NULLIF(TRIM({column}),'') AS DECIMAL(18,4)) END {key}")
        aggregates.append(f"CASE WHEN COUNT({key})=0 THEN NULL ELSE SUM({key}) END {key}")
    stock: dict[tuple[str, str], dict] = {}
    for offset in range(0, len(pairs), 500):
        chunk = pairs[offset:offset + 500]
        cursor.execute(
            f"""SELECT site,sku,{','.join(aggregates)}
                FROM (SELECT CASE wid {site_case} END site,UPPER(TRIM(sku)) sku,{','.join(columns)}
                      FROM {table} WHERE wid IN ({wids})
                        AND UPPER(TRIM(sku)) IN ({','.join(['%s'] * len(chunk))})) inventory
                WHERE (site,sku) IN ({','.join(['(%s,%s)'] * len(chunk))})
                GROUP BY site,sku""",
            [sku for _, sku in chunk] + [value for pair in chunk for value in pair],
        )
        for row in cursor.fetchall():
            stock[(row["site"], str(row["sku"]).upper())] = {key: _number(row[key]) for key, *_ in STOCK_COLUMNS}
    return stock, synced_at


def attach(cursor, items: list[dict[str, Any]]) -> dict[str, Any]:
    """给 SKU 行写入 purchase_logistics（三段都没有时为 None），返回各来源的可用状态与同步时间。"""
    targets = [item for item in items if _is_sku_item(item)]
    for item in targets:
        item[FIELD] = None
    pairs = sorted({(str(item.get("site") or "").strip(), str(item.get("sku") or "").strip().upper())
                    for item in targets if str(item.get("site") or "").strip() and str(item.get("sku") or "").strip()})
    meta = {"purchase_logistics_available": False, "purchase_logistics_synced_at": None,
            "inventory_stock_synced_at": None}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    try:
        rows, synced_at = repo.open_orders(cursor, pairs)
        meta.update(purchase_logistics_available=synced_at is not None,
                    purchase_logistics_synced_at=str(synced_at) if synced_at is not None else None)
        for row in rows:
            grouped[(row["site"], str(row["sku"]).upper())].append(row)
    except Exception as exc:
        if not repo.missing_table(exc):
            raise
    stock: dict[tuple[str, str], dict] = {}
    try:
        stock, stock_synced = warehouse_stock(cursor, pairs) if pairs else ({}, None)
        meta["inventory_stock_synced_at"] = str(stock_synced) if stock_synced is not None else None
    except ProgrammingError as exc:
        if exc.args[0] != 1146:
            raise
    today = reference_today()
    for item in targets:
        key = (str(item.get("site") or "").strip(), str(item.get("sku") or "").strip().upper())
        item[FIELD] = build(grouped.get(key, []), today, stock.get(key))
    return meta
