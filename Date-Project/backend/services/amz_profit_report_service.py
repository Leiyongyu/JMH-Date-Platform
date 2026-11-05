"""AMZ profit report by group, store or owner, in CNY or USD.

Sources are pulled in USD; CNY converts a whole period with the LingXing USD
我的汇率 (dim_lingxing_currency_month.my_rate, never the official rate_org) of
the period's last (largest) month.

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
DIMENSIONS = ("GROUP", "STORE", "OWNER")
DIMENSION_LABELS = {"GROUP": "组别", "STORE": "店铺", "OWNER": "个人"}
ZERO = Decimal("0")
MONEY = Decimal("0.01")
ONE = Decimal("1")
CURRENCIES = ("CNY", "USD")
CURRENCY_LABELS = {"CNY": "人民币", "USD": "美元"}
# Summed fields that are amounts (converted); the rest are quantities.
MONEY_FIELDS = (
    "sales_amount", "settlement_gross_profit", "margin_base", "ads_cost",
    "ads_sales", "order_gross_profit", "order_amount",
)
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
    ("target_usd", "业绩目标（USD）", "money"),
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


def get_report(
    start_month: str, dimension: str = "STORE", end_month: str | None = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Sum the months start_month..end_month (a single month when end_month is
    omitted) and compare with the period of equal length right before it."""
    months = _month_range(start_month, end_month or start_month)
    dim = str(dimension or "").strip().upper()
    if dim not in DIMENSIONS:
        raise ValueError("dimension 必须是 GROUP、STORE 或 OWNER")
    cur = _currency(currency)
    previous_months = _month_range(
        _shift_month(months[0], -len(months)), _shift_month(months[0], -1),
    )
    rates = _period_rates(months, previous_months, cur)
    if months[-1] not in rates:
        raise ValueError(
            f"{months[-1]} 缺少领星 USD「我的汇率」（dim_lingxing_currency_month），"
            "时间段按最大月份的汇率换算人民币；请先同步该月汇率，或切换为美元查看"
        )
    shops = inventory_repo.amazon_shop_map()
    current = _aggregate_months(months, dim, shops, rates)
    prior = _aggregate_months(previous_months, dim, shops, rates)
    targets, target_note, _missing = _range_targets(months, dim, rates)
    # Arrows and 环比 only compare against a fully pulled previous period;
    # half a period would make every metric look like a sharp rise.
    previous_ready = (
        prior["settlement_ready"] and not prior["missing_settlement_months"]
        and not prior["missing_rate_months"]
    )
    prior_rows = prior["rows"] if previous_ready else {}

    keys = set(current["rows"]) | set(targets)
    rows = []
    for key in sorted(keys, key=_sort_key):
        sums = current["rows"].get(key) or _empty()
        previous_sums = prior_rows.get(key)
        rows.append({
            "department_code": key[0],
            "dimension_value": key[1],
            **_ready(_metrics(sums, targets.get(key), previous_sums), current),
            "previous": _ready(_metrics(previous_sums, None, None), prior) if previous_sums else None,
        })
    target_values = [value for value in targets.values() if value is not None]
    total_target = sum(target_values, ZERO) if target_values else None
    total = _total(current["rows"].values())
    prior_total = _total(prior_rows.values()) if prior_rows else None
    return {
        "start_month": months[0],
        "end_month": months[-1],
        "months": months,
        "previous_start_month": previous_months[0],
        "previous_end_month": previous_months[-1],
        "dimension": dim,
        "currency_code": cur,
        # CNY per 1 USD applied to the whole period: 我的汇率 of its last month (USD: null).
        "exchange_rate": str(rates[months[-1]]) if cur == "CNY" else None,
        "exchange_rate_month": months[-1] if cur == "CNY" else None,
        "previous_exchange_rate": (
            str(rates[previous_months[-1]]) if cur == "CNY" and previous_months[-1] in rates else None
        ),
        # 销售目标 for month M is frozen in the inventory report of stock month M-1;
        # a period's target is the sum of its months' targets.
        "target_note": target_note,
        "settlement_ready": current["settlement_ready"],
        "order_ready": current["order_ready"],
        "missing_settlement_months": current["missing_settlement_months"],
        "missing_order_months": current["missing_order_months"],
        "previous_ready": previous_ready,
        "excluded": current["excluded"],
        "rows": rows,
        "total": {
            **_ready(_metrics(total, total_target, prior_total), current),
            "previous": _ready(_metrics(prior_total, None, None), prior) if prior_total else None,
        },
    }


def export_report(
    start_month: str, end_month: str, dimensions: list[str] | None = None,
    currency: str = "USD",
) -> tuple[str, bytes]:
    """Exactly what the page shows for the chosen period: one sheet per
    dimension, 合计 then the rows, every figure summed over the period."""
    months = _month_range(start_month, end_month)
    selected = [str(item).strip().upper() for item in (dimensions or DIMENSIONS)]
    if not selected or any(item not in DIMENSIONS for item in selected):
        raise ValueError("dimensions 只能是 GROUP、STORE、OWNER")
    cur = _currency(currency)
    period = _period_label(months[0], months[-1])
    available = {row["stat_month"] for row in list_months(120)}
    if not any(month in available for month in months):
        raise ValueError(f"{period} 没有已拉取的数据")

    workbook = Workbook()
    workbook.remove(workbook.active)
    header_fill = PatternFill("solid", fgColor="DCE6F1")
    total_fill = PatternFill("solid", fgColor="F2F2F2")
    for dim in DIMENSIONS:
        if dim not in selected:
            continue
        report = get_report(months[0], dim, months[-1], currency=cur)
        sheet = workbook.create_sheet(DIMENSION_LABELS[dim])
        name_header = {"GROUP": [], "STORE": ["店铺"], "OWNER": ["负责人"]}[dim]
        headers = ["统计区间", "组别", *name_header,
                   *(label.replace("USD", cur) for _field, label, _kind in EXPORT_COLUMNS)]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        lines = [("合计", "", report["total"], True)] + [
            (row["department_code"].removeprefix("AMZ-"), row["dimension_value"], row, False)
            for row in report["rows"]
        ]
        first_value_column = 4 if name_header else 3
        for group, name, values, is_total in lines:
            sheet.append([period, group, *([name] if name_header else []), *(
                _export_value(values.get(field), kind)
                for field, _label, kind in EXPORT_COLUMNS
            )])
            for index, (_field, _label, kind) in enumerate(EXPORT_COLUMNS, start=first_value_column):
                sheet.cell(sheet.max_row, index).number_format = EXPORT_FORMATS[kind]
            if is_total:
                for cell in sheet[sheet.max_row]:
                    cell.font = Font(bold=True)
                    cell.fill = total_fill
        notes = _export_notes(report)
        if notes:
            sheet.append([])
            for note in notes:
                sheet.append([note])
                sheet.cell(sheet.max_row, 1).font = Font(color="7A869A")
        sheet.freeze_panes = "D2" if name_header else "C2"
        widths = [20, 12, *([14] if name_header else []), *([14] * len(EXPORT_COLUMNS))]
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
    buffer = BytesIO()
    workbook.save(buffer)
    suffix = months[0] if len(months) == 1 else f"{months[0]}至{months[-1]}"
    return f"AMZ利润报表-{suffix}-{CURRENCY_LABELS[cur]}.xlsx", buffer.getvalue()


def _period_label(start: str, end: str) -> str:
    return start if start == end else f"{start} 至 {end}"


def _export_notes(report: dict[str, Any]) -> list[str]:
    """Same caveats the page shows above the table."""
    notes = []
    if report.get("exchange_rate"):
        notes.append(
            f"说明：金额为人民币，整个时间段统一按最大月份 {report['exchange_rate_month']} 的"
            f"领星 USD「我的汇率」{report['exchange_rate']} 换算"
        )
    if report.get("missing_settlement_months"):
        notes.append("说明：" + "、".join(report["missing_settlement_months"]) + " 结算数据未拉取，合计只包含已拉取的月份")
    if report.get("missing_order_months"):
        notes.append("说明：" + "、".join(report["missing_order_months"]) + " 订单利润未拉取，订单毛利润只包含已拉取的月份")
    if report.get("previous_start_month"):
        previous = _period_label(report["previous_start_month"], report["previous_end_month"])
        notes.append(f"说明：销售额环比与上期 {previous} 比较" + ("" if report.get("previous_ready") else "（上期未完整拉取，不计算）"))
    if report.get("target_note"):
        notes.append("说明：" + report["target_note"])
    return notes


def _export_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    number = Decimal(str(value))
    return int(number) if kind == "qty" else float(number)


def _month_range(start_month: str, end_month: str) -> list[str]:
    start, end = inventory._month(start_month), inventory._month(end_month)
    if start > end:
        raise ValueError("开始月份不能晚于结束月份")
    months = [start]
    while months[-1] < end:
        months.append(inventory._next_month(months[-1]))
        if len(months) > MAX_EXPORT_MONTHS:
            raise ValueError(f"一次最多查询{MAX_EXPORT_MONTHS}个月")
    return months


def _shift_month(month: str, delta: int) -> str:
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + number - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _currency(currency: str | None) -> str:
    value = str(currency or "USD").strip().upper()
    if value not in CURRENCIES:
        raise ValueError("currency 必须是 CNY 或 USD")
    return value


def _period_rates(
    months: list[str], previous_months: list[str], currency: str,
) -> dict[str, Decimal]:
    """Multiplier per month from the stored USD amounts to the chosen currency.

    CNY: every month of a period uses the 我的汇率 of that period's last
    (largest) month; the previous period likewise uses its own last month.
    A period whose last month has no rate gets no entries.
    """
    if currency == "USD":
        return {month: ONE for month in (*previous_months, *months)}
    found = {}
    for month, value in repo.usd_my_rates([previous_months[-1], months[-1]]).items():
        rate = _num(value)
        if rate > ZERO:
            found[month] = rate
    rates: dict[str, Decimal] = {}
    for period in (previous_months, months):
        rate = found.get(period[-1])
        if rate is not None:
            rates.update({month: rate for month in period})
    return rates


def _aggregate_months(
    months: list[str], dim: str, shops: dict[str, str], rates: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    """Each month keeps its own owner rules and exchange rate; the period is the
    sum of its months. A month with data but no rate is reported, not added."""
    rows: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(_empty)
    excluded: dict[str, int] = defaultdict(int)
    missing_settlement, missing_order, missing_rate = [], [], []
    for month in months:
        result = _aggregate(month, dim, shops)
        rate = ONE if rates is None else rates.get(month)
        if rate is None:
            if result["settlement_ready"] or result["order_ready"]:
                missing_rate.append(month)
            result = {**result, "rows": {}}
        for key, sums in result["rows"].items():
            for field in SUM_FIELDS:
                value = sums[field]
                rows[key][field] += value * rate if field in MONEY_FIELDS else value
        for reason, count in result["excluded"].items():
            excluded[reason] += count
        if not result["settlement_ready"]:
            missing_settlement.append(month)
        if not result["order_ready"]:
            missing_order.append(month)
    return {
        "rows": dict(rows),
        "settlement_ready": len(missing_settlement) < len(months),
        "order_ready": len(missing_order) < len(months),
        "missing_settlement_months": missing_settlement,
        "missing_order_months": missing_order,
        "missing_rate_months": missing_rate,
        "excluded": dict(excluded),
    }


def _range_targets(
    months: list[str], dim: str, rates: dict[str, Decimal] | None = None,
) -> tuple[dict[tuple[str, str], Decimal | None], str | None, list[str]]:
    """Sum each month's target, converted with that month's rate (same rate as
    the sales, so 达成率 does not change with the currency of a single month)."""
    targets: dict[tuple[str, str], Decimal | None] = {}
    notes, missing_rate = [], []
    for month in months:
        month_targets, note = _targets(month, dim)
        if note:
            notes.append(f"{month}：{note}")
        rate = ONE if rates is None else rates.get(month)
        if rate is None and any(value is not None for value in month_targets.values()):
            missing_rate.append(month)
            continue
        for key, value in month_targets.items():
            if value is None:
                targets.setdefault(key, None)
            else:
                targets[key] = (targets.get(key) or ZERO) + value * rate
    return targets, "；".join(notes) or None, missing_rate


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
    if dim == "GROUP":
        return department, department.removeprefix("AMZ-")
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
        payload = (
            inventory.get_department_summary(stat_month) if dim == "GROUP"
            else inventory.get_dimension_summary(dim, stat_month)
        )
    except Exception:
        LOG.exception("AMZ利润报表读取月度库存销售目标失败 month=%s dim=%s", month, dim)
        return {}, "月度库存销售目标读取失败"
    if payload.get("historical_import") or not payload.get("items"):
        return {}, f"月度库存{stat_month}没有{DIMENSION_LABELS[dim]}维度销售目标"
    if dim == "GROUP":
        return _group_targets(payload["items"]), None
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


def _group_targets(items: list[dict[str, Any]]) -> dict[tuple[str, str], Decimal | None]:
    """AMZ department rows of the inventory GROUP view.

    Skips the total, eBay and the display-only AMZ-US3 row (MJ + ZXY), so the
    profit report's MJ and ZXY rows each keep their own target.
    """
    targets: dict[tuple[str, str], Decimal | None] = {}
    for item in items:
        department = inventory.normalize_text(item.get("department_code")).upper()
        if int(item.get("is_total") or 0) or department not in inventory.VALID_DEPARTMENTS \
                or not department.startswith("AMZ-"):
            continue
        value = item.get("sales_target_usd")
        targets[(department, department.removeprefix("AMZ-"))] = _num(value) if value is not None else None
    return targets


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
