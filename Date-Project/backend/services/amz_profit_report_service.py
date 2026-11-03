"""AMZ profit report by store or owner (USD).

Settlement figures (利润统计) drive the report; only 订单毛利润/订单毛利率 come
from 订单利润. Rows use the monthly-inventory classification so store and owner
keys, exclusions and owner rules match the 销售目标（USD） taken from there.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from backend.repositories import amz_profit_report_repository as repo
from backend.repositories import inventory_report_etl_repository as inventory_repo
from backend.services import inventory_report_etl_service as inventory


LOG = logging.getLogger(__name__)
DIMENSIONS = ("STORE", "OWNER")
ZERO = Decimal("0")
MONEY = Decimal("0.01")
RATE = Decimal("0.000001")
SUM_FIELDS = (
    "sales_qty", "sales_amount", "settlement_gross_profit", "margin_base",
    "returns_qty", "refunds_qty", "ads_cost", "ads_sales",
    "order_gross_profit", "order_amount",
)
# LingXing 毛利率 denominator: 销售额+买家运费+促销折扣+FBA库存赔偿+COD+其他收入+收入退款额.
MARGIN_BASE_COLUMNS = (
    "total_sales_amount", "shipping_credits", "promotional_rebates",
    "fba_inventory_credit", "cash_on_delivery", "other_in_amount",
    "total_sales_refunds",
)
SETTLEMENT_METRIC_KEYS = (
    "sales_qty", "sales_amount", "achievement_rate", "sales_mom",
    "settlement_gross_profit", "settlement_gross_margin",
    "return_rate", "refund_rate", "acos", "ad_ratio",
)
ORDER_METRIC_KEYS = ("order_gross_profit", "order_gross_margin")
# (field, header, format) in page order; formats match the page display.
EXPORT_COLUMNS = (
    ("target_usd", "每月业绩目标（USD）", "money"),
    ("achievement_rate", "达成率", "rate"),
    ("sales_qty", "销量", "qty"),
    ("sales_amount", "销售额（USD）", "money"),
    ("sales_mom", "销售额环比", "rate"),
    ("order_gross_profit", "订单毛利润（USD）", "money"),
    ("order_gross_margin", "订单毛利率", "rate"),
    ("settlement_gross_profit", "结算毛利润（USD）", "money"),
    ("settlement_gross_margin", "结算毛利率", "rate"),
    ("return_rate", "退货率", "rate"),
    ("refund_rate", "退款率", "rate"),
    ("acos", "ACOS", "rate"),
    ("ad_ratio", "广告占比", "rate"),
)
EXPORT_FORMATS = {"money": "#,##0.00", "rate": "0.00%", "qty": "#,##0"}
MAX_EXPORT_MONTHS = 24
DEPARTMENT_ORDER = {code: order for code, _name, order in inventory.DEPARTMENTS}


def list_months(limit: int = 24) -> list[dict[str, Any]]:
    return [
        {
            "stat_month": str(row["stat_month"]),
            "synced_at": str(row["synced_at"]) if row.get("synced_at") else None,
            "has_settlement": bool(row.get("has_settlement")),
            "has_order": bool(row.get("has_order")),
        }
        for row in repo.months(limit)
    ]


def get_report(stat_month: str, dimension: str = "STORE") -> dict[str, Any]:
    month = inventory._month(stat_month)
    dim = str(dimension or "").strip().upper()
    if dim not in DIMENSIONS:
        raise ValueError("dimension 必须是 STORE 或 OWNER")
    previous = inventory._previous_month(month)
    shops = inventory_repo.amazon_shop_map()
    current = _aggregate(month, dim, shops)
    prior = _aggregate(previous, dim, shops)
    targets, target_note = _targets(month, dim)

    keys = set(current["rows"]) | set(targets)
    rows = []
    for key in sorted(keys, key=_sort_key):
        sums = current["rows"].get(key) or _empty()
        previous_sums = prior["rows"].get(key)
        rows.append({
            "department_code": key[0],
            "dimension_value": key[1],
            **_ready(_metrics(sums, targets.get(key), previous_sums), current),
            "previous": _ready(_metrics(previous_sums, None, None), prior) if previous_sums else None,
        })
    target_values = [value for value in targets.values() if value is not None]
    total_target = sum(target_values, ZERO) if target_values else None
    total = _total(current["rows"].values())
    prior_total = _total(prior["rows"].values()) if prior["rows"] else None
    return {
        "stat_month": month,
        "previous_month": previous,
        "dimension": dim,
        "currency_code": "USD",
        # 销售目标 for month M is frozen in the inventory report of stock month M-1.
        "target_stat_month": previous,
        "target_note": target_note,
        "settlement_ready": current["settlement_ready"],
        "order_ready": current["order_ready"],
        "previous_ready": prior["settlement_ready"],
        "excluded": current["excluded"],
        "rows": rows,
        "total": {
            **_ready(_metrics(total, total_target, prior_total), current),
            "previous": _ready(_metrics(prior_total, None, None), prior) if prior_total else None,
        },
    }


def export_report(
    start_month: str, end_month: str, dimensions: list[str] | None = None,
) -> tuple[str, bytes]:
    """Excel with one sheet per dimension; each month lists 合计 then its rows."""
    start, end = inventory._month(start_month), inventory._month(end_month)
    if start > end:
        raise ValueError("开始月份不能晚于结束月份")
    months = [start]
    while months[-1] < end:
        months.append(inventory._next_month(months[-1]))
    if len(months) > MAX_EXPORT_MONTHS:
        raise ValueError(f"一次最多导出{MAX_EXPORT_MONTHS}个月")
    selected = [str(item).strip().upper() for item in (dimensions or DIMENSIONS)]
    if not selected or any(item not in DIMENSIONS for item in selected):
        raise ValueError("dimensions 只能是 STORE、OWNER")
    available = {row["stat_month"] for row in list_months(120)}
    months = [month for month in months if month in available]
    if not months:
        raise ValueError(f"{start} 至 {end} 没有已拉取的数据")

    workbook = Workbook()
    workbook.remove(workbook.active)
    header_fill = PatternFill("solid", fgColor="DCE6F1")
    total_fill = PatternFill("solid", fgColor="F2F2F2")
    for dim in DIMENSIONS:
        if dim not in selected:
            continue
        sheet = workbook.create_sheet("店铺" if dim == "STORE" else "个人")
        headers = ["月份", "组别", "店铺" if dim == "STORE" else "负责人",
                   *(label for _field, label, _kind in EXPORT_COLUMNS)]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for month in months:
            report = get_report(month, dim)
            lines = [("合计", "", report["total"], True)] + [
                (row["department_code"].removeprefix("AMZ-"), row["dimension_value"], row, False)
                for row in report["rows"]
            ]
            for group, name, values, is_total in lines:
                sheet.append([month, group, name, *(
                    _export_value(values.get(field), kind)
                    for field, _label, kind in EXPORT_COLUMNS
                )])
                for index, (_field, _label, kind) in enumerate(EXPORT_COLUMNS, start=4):
                    sheet.cell(sheet.max_row, index).number_format = EXPORT_FORMATS[kind]
                if is_total:
                    for cell in sheet[sheet.max_row]:
                        cell.font = Font(bold=True)
                        cell.fill = total_fill
        sheet.freeze_panes = "D2"
        for index, width in enumerate([10, 12, 14, *([14] * len(EXPORT_COLUMNS))], start=1):
            sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
    buffer = BytesIO()
    workbook.save(buffer)
    return f"AMZ利润报表-{months[0]}至{months[-1]}.xlsx", buffer.getvalue()


def _export_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    number = Decimal(str(value))
    return int(number) if kind == "qty" else float(number)


def _aggregate(month: str, dim: str, shops: dict[str, str]) -> dict[str, Any]:
    rules = inventory._amazon_rule_maps(inventory_repo.owner_rules(month, "amazon"))
    rows: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(_empty)
    excluded: dict[str, int] = defaultdict(int)
    settlement = repo.msku_month_rows(month)
    orders = repo.order_month_rows(month)
    for row in settlement:
        key = _classify(row, dim, shops, rules, excluded)
        if key is None:
            continue
        sums = rows[key]
        sums["sales_qty"] += _num(row["total_sales_quantity"])
        sums["sales_amount"] += _num(row["total_sales_amount"])
        sums["settlement_gross_profit"] += _num(row["gross_profit"])
        sums["margin_base"] += sum((_num(row[c]) for c in MARGIN_BASE_COLUMNS), ZERO)
        sums["returns_qty"] += _num(row["fba_returns_quantity"])
        sums["refunds_qty"] += _num(row["refunds_quantity"])
        # LingXing reports costs as negative amounts.
        sums["ads_cost"] += abs(_num(row["total_ads_cost"]))
        sums["ads_sales"] += _num(row["total_ads_sales"])
    for row in orders:
        key = _classify(row, dim, shops, rules, None)
        if key is None:
            continue
        rows[key]["order_gross_profit"] += _num(row["gross_profit"])
        rows[key]["order_amount"] += _num(row["amount"])
    return {
        "rows": dict(rows),
        "settlement_ready": bool(settlement),
        "order_ready": bool(orders),
        "excluded": dict(excluded),
    }


def _classify(row, dim, shops, rules, excluded) -> tuple[str, str] | None:
    """Same exclusions, group and owner rules as the monthly inventory report."""
    sid = str(row.get("sid") or "").strip()
    if sid in inventory.INVENTORY_EXCLUDED_SIDS:
        return _skip(excluded, "excluded_shop")
    store = shops.get(sid) or str(row.get("store_name") or "").strip()
    msku = inventory.normalize_text(row.get("msku"))
    if inventory._exclude_special_store_msku(store, msku):
        return _skip(excluded, "excluded_special_msku")
    local_sku = inventory.normalize_text(row.get("local_sku"))
    principal, _source, matched_group = inventory._amazon_assignment(
        store, local_sku or msku, rules
    )
    department = inventory._department(inventory._amazon_group(store) or matched_group)
    if not department:
        return _skip(excluded, "unmatched_department")
    if dim == "STORE":
        return department, inventory._store_dimension_name(store) or "未知店铺"
    return department, inventory._principal(principal)


def _skip(excluded, reason) -> None:
    if excluded is not None:
        excluded[reason] += 1
    return None


def _targets(month: str, dim: str) -> tuple[dict[tuple[str, str], Decimal | None], str | None]:
    stat_month = inventory._previous_month(month)
    try:
        payload = inventory.get_dimension_summary(dim, stat_month)
    except Exception:
        LOG.exception("AMZ利润报表读取月度库存销售目标失败 month=%s dim=%s", month, dim)
        return {}, "月度库存销售目标读取失败"
    if payload.get("historical_import") or not payload.get("items"):
        return {}, f"月度库存{stat_month}没有{'店铺' if dim == 'STORE' else '个人'}维度销售目标"
    targets: dict[tuple[str, str], Decimal | None] = {}
    for item in payload["items"]:
        if int(item.get("is_age_cost_only") or 0) or str(item.get("platform_code") or "").upper() != "AMZ":
            continue
        key = (
            inventory.normalize_text(item.get("department_code")).upper(),
            inventory.normalize_text(item.get("dimension_value")),
        )
        value = item.get("sales_target_usd")
        if value is None:
            targets.setdefault(key, None)
            continue
        targets[key] = (targets.get(key) or ZERO) + _num(value)
    return targets, None


def _metrics(
    sums: dict[str, Decimal] | None,
    target: Decimal | None,
    previous: dict[str, Decimal] | None,
) -> dict[str, Any]:
    sums = sums or _empty()
    previous_sales = previous["sales_amount"] if previous else None
    return {
        "target_usd": _money(target),
        "sales_qty": str(int(sums["sales_qty"])),
        "sales_amount": _money(sums["sales_amount"]),
        "achievement_rate": _rate(sums["sales_amount"], target),
        "sales_mom": (
            _rate(sums["sales_amount"] - previous_sales, abs(previous_sales))
            if previous_sales is not None else None
        ),
        "order_gross_profit": _money(sums["order_gross_profit"]),
        "order_gross_margin": _rate(sums["order_gross_profit"], sums["order_amount"]),
        "settlement_gross_profit": _money(sums["settlement_gross_profit"]),
        "settlement_gross_margin": _rate(sums["settlement_gross_profit"], sums["margin_base"]),
        "return_rate": _rate(sums["returns_qty"], sums["sales_qty"]),
        "refund_rate": _rate(sums["refunds_qty"], sums["sales_qty"]),
        "acos": _rate(sums["ads_cost"], sums["ads_sales"]),
        "ad_ratio": _rate(sums["ads_cost"], sums["sales_amount"]),
    }


def _ready(metrics: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """A month that was never pulled shows blanks, not zero sales or 0% rates."""
    blank = ()
    if not source["settlement_ready"]:
        blank += SETTLEMENT_METRIC_KEYS
    if not source["order_ready"]:
        blank += ORDER_METRIC_KEYS
    return {key: None if key in blank else value for key, value in metrics.items()}


def _total(rows) -> dict[str, Decimal]:
    total = _empty()
    for sums in rows:
        for field in SUM_FIELDS:
            total[field] += sums[field]
    return total


def _empty() -> dict[str, Decimal]:
    return {field: ZERO for field in SUM_FIELDS}


def _sort_key(key: tuple[str, str]):
    department, value = key
    return (DEPARTMENT_ORDER.get(department, 99), value == inventory.UNASSIGNED, value)


def _num(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else inventory._num(value)


def _money(value: Decimal | None) -> str | None:
    return str(value.quantize(MONEY, rounding=ROUND_HALF_UP)) if value is not None else None


def _rate(numerator: Decimal, denominator: Decimal | None) -> str | None:
    if denominator is None or denominator == ZERO:
        return None
    return str((numerator / denominator).quantize(RATE, rounding=ROUND_HALF_UP))
