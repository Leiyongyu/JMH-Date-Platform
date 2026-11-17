"""Display-only group rows; never write synthetic US3 into source/DWS totals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


SPLIT_GROUPS = ("AMZ-US2-MJ", "AMZ-US1-ZXY")
US3 = "AMZ-US3"
SUBTOTAL = "AUTO-PARTS-TOTAL"

# These are report values, not identifiers or month/rate metadata. The
# historical workbook uses column-wise addition for US3, including ratios.
SUM_FIELDS = (
    "source_rows",
    "total_goods_value",
    "local_end_in_transit_qty",
    "local_end_in_transit_total_cost",
    "local_end_inventory_qty",
    "local_end_inventory_total_cost",
    "overseas_end_in_transit_qty",
    "overseas_end_in_transit_total_cost",
    "overseas_end_inventory_qty",
    "overseas_end_inventory_total_cost",
    "fba_end_in_transit_qty",
    "fba_end_in_transit_total_cost",
    "fba_end_inventory_qty",
    "fba_end_inventory_total_cost",
    "fba_transit_inventory_amount",
    "inventory_181_plus_sku_count",
    "inventory_health_rate",
    "sales_target_amount",
    "sales_target_usd",
    "actual_achievement_amount",
    "actual_achievement_amount_usd",
    "target_achievement_rate",
    "turnover_days_by_value",
    "next_month_opening_inventory_qty",
    "monthly_sales_qty",
    "opening_inventory_sales_ratio",
    "turnover_days_by_sku",
    "ctu_over_30_cost",
    "inventory_age_90_180_cost",
    "inventory_age_180_plus_cost",
)
METADATA_FIELDS = (
    "stat_month",
    "ctu_cost_month",
    "inventory_age_cost_month",
    "inventory_health_month",
    "sales_volume_month",
    "actual_achievement_month",
    "rate_month",
    "usd_rate",
)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _sum_column(rows: list[dict[str, Any]], field: str) -> str | None:
    values = [_decimal(row.get(field)) for row in rows]
    present = [value for value in values if value is not None]
    return str(sum(present, Decimal("0"))) if present else None


def _make_row(
    rows: list[dict[str, Any]], code: str, name: str, *,
    is_total: bool, historical: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "department_code": code,
        "department_name": name,
        "display_order": 99 if is_total else 7,
        "is_total": 1 if is_total else 0,
    }
    if historical:
        result["historical_import"] = True
    if rows:
        result.update({field: rows[0].get(field) for field in METADATA_FIELDS
                       if field in rows[0]})
    result.update({field: _sum_column(rows, field) for field in SUM_FIELDS})
    if not is_total and not historical:
        # The CTU US3 value is already repeated on both split rows because
        # they share one warehouse snapshot. Keep it once, as the existing
        # subtotal does, instead of doubling the same inventory value.
        costs = [_decimal(row.get("ctu_over_30_cost")) for row in rows]
        if len(costs) == 2 and costs[0] is not None and costs[0] == costs[1]:
            result["ctu_over_30_cost"] = str(costs[0])
    return result


def with_group_display_rows(payload: dict[str, Any]) -> dict[str, Any]:
    """Add missing display rows without changing stored snapshots or totals."""
    items = list(payload.get("items") or [])
    groups = {str(item.get("department_code") or ""): item for item in items}
    historical = bool(payload.get("historical_import"))
    changed = False
    if not historical and US3 not in groups and all(code in groups for code in SPLIT_GROUPS):
        split = [groups[code] for code in SPLIT_GROUPS]
        us3_row = _make_row(split, US3, US3, is_total=False, historical=False)
        position = max(items.index(row) for row in split) + 1
        items.insert(position, us3_row)
        groups[US3] = us3_row
        changed = True
    if historical and SUBTOTAL not in groups and US3 in groups:
        distinct = [item for item in items
                    if str(item.get("department_code") or "") not in SPLIT_GROUPS
                    and int(item.get("is_total") or 0) != 1]
        items.append(_make_row(distinct, SUBTOTAL, "汽配小计",
                               is_total=True, historical=True))
        changed = True
    return {**payload, "items": items} if changed else payload
