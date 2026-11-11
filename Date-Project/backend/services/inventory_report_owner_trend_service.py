"""月度库存「个人」维度趋势：每个负责人逐月的销售额、毛利、周转天数（货值）、181天以上库龄成本。

月份一律按页面上展示的月份（报表月）对齐：
- 销售额 / 毛利：绩效排名（AMZ+eBay 合并）同月的净销售额、毛利润，CNY；
- 周转天数（货值）、181天以上库龄成本：报表月对应的个人维度快照（计算月 = 报表月上一个月）。
同一负责人分在多个组别时：库龄成本直接相加；周转天数按各组实际达成加权，
等价于把各组「折算后库存货值 × 28」相加后再除以实际达成合计。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.repositories import inventory_report_etl_repository as repo

MAX_MONTHS = 24
METRICS = ("sales_amount", "gross_profit", "turnover_days", "aged_181_plus_cost")
ZERO = Decimal("0")


def _parse_month(value: str) -> date:
    try:
        year, month = str(value).split("-")
        return date(int(year), int(month), 1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"月份格式应为 YYYY-MM：{value}") from exc


def _shift(month: date, offset: int) -> date:
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _label(month: date) -> str:
    return month.strftime("%Y-%m")


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _number(value: Decimal | None) -> float | None:
    return None if value is None else float(round(value, 2))


def owner_trend(start_month: str, end_month: str) -> dict[str, Any]:
    start, end = _parse_month(start_month), _parse_month(end_month)
    if start > end:
        raise ValueError("开始月份不能晚于结束月份")
    months = []
    cursor = start
    while cursor <= end:
        months.append(_label(cursor))
        cursor = _shift(cursor, 1)
    if len(months) > MAX_MONTHS:
        raise ValueError(f"时间段最多 {MAX_MONTHS} 个月")
    index = {month: position for position, month in enumerate(months)}
    owners: dict[str, dict[str, list]] = {}

    def series(owner: str) -> dict[str, list]:
        return owners.setdefault(owner, {metric: [None] * len(months) for metric in METRICS})

    for row in repo.owner_performance_rows(months[0], months[-1]):
        position = index.get(str(row.get("stat_month")))
        owner = str(row.get("principal_name") or "").strip()
        if position is None or not owner:
            continue
        data = series(owner)
        data["sales_amount"][position] = _number(_decimal(row.get("net_sales_amount")))
        data["gross_profit"][position] = _number(_decimal(row.get("gross_profit")))

    inventory_months = set()
    snapshots = repo.owner_view_snapshots(_label(_shift(start, -1)), _label(_shift(end, -1)))
    for snapshot in snapshots:
        payload = snapshot["payload"] or {}
        report_month = payload.get("report_month") or _label(
            _shift(_parse_month(snapshot["stat_month"]), 1)
        )
        position = index.get(report_month)
        if position is None:
            continue
        inventory_months.add(report_month)
        weighted: dict[str, list[Decimal]] = {}
        aged: dict[str, Decimal] = {}
        for item in payload.get("items") or []:
            if str(item.get("is_dimension_total") or "0") == "1":
                continue
            owner = str(item.get("dimension_value") or "").strip()
            if not owner:
                continue
            series(owner)
            turnover = _decimal(item.get("turnover_days_by_value"))
            actual = _decimal(item.get("actual_achievement_amount"))
            if turnover is not None and actual is not None and actual > ZERO:
                pair = weighted.setdefault(owner, [ZERO, ZERO])
                pair[0] += turnover * actual
                pair[1] += actual
            cost = _decimal(item.get("inventory_age_180_plus_cost"))
            if cost is not None:
                aged[owner] = aged.get(owner, ZERO) + cost
        for owner, (numerator, denominator) in weighted.items():
            owners[owner]["turnover_days"][position] = _number(numerator / denominator)
        for owner, cost in aged.items():
            owners[owner]["aged_181_plus_cost"][position] = _number(cost)

    ranked = sorted(
        owners,
        key=lambda owner: (
            owner in {"未分配", "注销"},
            -sum(value or 0 for value in owners[owner]["sales_amount"]),
            owner,
        ),
    )
    return {
        "months": months,
        "inventory_months": sorted(inventory_months),
        "owners": ranked,
        "series": {owner: owners[owner] for owner in ranked},
    }
