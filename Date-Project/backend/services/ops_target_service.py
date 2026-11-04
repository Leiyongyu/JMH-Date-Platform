"""财务中心「运营目标与人效」：在手工维护的部门目标上计算合计、达成率、年度/月度合计与人效预警。

计算口径（与原 Excel 一致的沿用，Excel 里明显有误的在注释中说明）：
- 累计目标达成率 = 年度实际（含退款）÷ 年度冲刺目标；合计行同样按合计值相除；
- 季度表「全年目标」= Q1~Q4 目标之和（Excel 中为手填，与各季度之和一致）；月度「合计」= 1~12 月之和；
- 合计行：金额、个数、编制求和；月均目标毛利率、人效目标取各部门简单平均（Excel 的「合计/平均」）。
  Excel 年度汇总里合计毛利率写的是「全年预估毛利润 ÷ 年度实际」（=119%），不是毛利率，这里改为各部门平均；
- 人效预警按「人效管控规则」：实际人效 = 季度实际 ÷ 当前编制，<20 万/人红色；
  人力成本率 = 人力成本包 ÷ 年度实际，>10% 黄色、>12% 红色；人均毛利贡献 = 全年预估毛利润 ÷ 编制，<50 万/人黄色。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.repositories import ops_target_repository as repo

QUARTERS = (1, 2, 3, 4)
MONTHS = tuple(range(1, 13))
SUM_FIELDS = ("floor_target", "sprint_target", "actual_amount", "new_product_target", "new_product_actual",
              "est_gross_profit", "labor_cost_pack", *(f"q{q}_target" for q in QUARTERS),
              *(f"q{q}_actual" for q in QUARTERS), *(f"m{m:02d}_target" for m in MONTHS), "headcount")
AVG_FIELDS = ("target_margin_rate", *(f"q{q}_efficiency_target" for q in QUARTERS), "annual_efficiency_target")
EFFICIENCY_RED = 20
LABOR_RATE_YELLOW, LABOR_RATE_RED = 0.10, 0.12
GROSS_PER_HEAD_YELLOW = 50
MAX_MONEY = Decimal("100000000")


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _sum(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present), 4) if present else None


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator, 4)


def _level(value: float | None, *, red_below: float | None = None, yellow_above: float | None = None,
           red_above: float | None = None, yellow_below: float | None = None) -> str | None:
    if value is None:
        return None
    if red_below is not None and value < red_below:
        return "red"
    if red_above is not None and value > red_above:
        return "red"
    if yellow_above is not None and value > yellow_above:
        return "yellow"
    if yellow_below is not None and value < yellow_below:
        return "yellow"
    return None


def _derive(row: dict[str, Any]) -> dict[str, Any]:
    quarter_targets = [row.get(f"q{q}_target") for q in QUARTERS]
    derived: dict[str, Any] = {
        "achievement_rate": _ratio(row.get("actual_amount"), row.get("sprint_target")),
        "quarter_target_total": _sum(quarter_targets),
        "month_target_total": _sum([row.get(f"m{m:02d}_target") for m in MONTHS]),
        "labor_cost_rate": _ratio(row.get("labor_cost_pack"), row.get("actual_amount")),
        "gross_profit_per_head": _ratio(row.get("est_gross_profit"), row.get("headcount")),
    }
    for q in QUARTERS:
        derived[f"q{q}_achievement_rate"] = _ratio(row.get(f"q{q}_actual"), row.get(f"q{q}_target"))
        derived[f"q{q}_actual_efficiency"] = _ratio(row.get(f"q{q}_actual"), row.get("headcount"))
    levels = {f"q{q}_actual_efficiency": _level(derived[f"q{q}_actual_efficiency"], red_below=EFFICIENCY_RED)
              for q in QUARTERS}
    levels["labor_cost_rate"] = _level(derived["labor_cost_rate"], yellow_above=LABOR_RATE_YELLOW,
                                       red_above=LABOR_RATE_RED)
    levels["gross_profit_per_head"] = _level(derived["gross_profit_per_head"], yellow_below=GROSS_PER_HEAD_YELLOW)
    derived["levels"] = {k: v for k, v in levels.items() if v}
    return derived


def _clean(raw: dict[str, Any]) -> dict[str, Any]:
    row = {"dept_code": raw["dept_code"], "sort_no": raw["sort_no"], "remark": raw.get("remark") or "",
           "updated_by": raw.get("updated_by") or "",
           "updated_at": raw["updated_at"].isoformat(timespec="seconds") if isinstance(raw.get("updated_at"), datetime)
           else raw.get("updated_at")}
    for field, kind in repo.EDITABLE_FIELDS.items():
        if kind == "text":
            continue
        value = _num(raw.get(field))
        row[field] = int(value) if kind == "int" and value is not None else value
    return row


def _consistency(rows: list[dict[str, Any]]) -> list[str]:
    """月度合计、季度合计、冲刺目标三者不一致时提示（只提示，不阻止保存）。"""
    notes = []
    for row in rows:
        month, quarter, sprint = (row["month_target_total"], row["quarter_target_total"], row.get("sprint_target"))
        if month is not None and quarter is not None and abs(month - quarter) > 0.01:
            notes.append(f"{row['dept_code']}：月度目标合计 {month:g} 万元，与季度目标合计 {quarter:g} 万元不一致")
        if quarter is not None and sprint is not None and abs(quarter - sprint) > 0.01:
            notes.append(f"{row['dept_code']}：季度目标合计 {quarter:g} 万元，与年度冲刺目标 {sprint:g} 万元不一致")
    return notes


def get_report(year: int | None) -> dict[str, Any]:
    available = repo.years()
    if not available:
        return {"year": year, "years": [], "rows": [], "total": None, "notes": ["还没有目标数据，请先执行数据库迁移"]}
    year = year if year in available else available[0]
    rows = []
    for raw in repo.rows(year):
        row = _clean(raw)
        row.update(_derive(row))
        rows.append(row)
    total: dict[str, Any] = {"dept_code": "合计"}
    for field in SUM_FIELDS:
        total[field] = _sum([r.get(field) for r in rows])
    for field in AVG_FIELDS:
        total[field] = _avg([r.get(field) for r in rows])
    # 合计行的达成率、实际人效等按合计值计算（合计实际 ÷ 合计编制），预警同样适用
    total.update(_derive(total))
    latest = max((r for r in rows if r.get("updated_at")), key=lambda r: r["updated_at"], default=None)
    return {
        "year": year, "years": available, "rows": rows, "total": total,
        "notes": _consistency(rows),
        "updatedAt": latest["updated_at"] if latest else None,
        "updatedBy": latest["updated_by"] if latest else None,
        "thresholds": {"efficiencyRed": EFFICIENCY_RED, "laborRateYellow": LABOR_RATE_YELLOW,
                       "laborRateRed": LABOR_RATE_RED, "grossPerHeadYellow": GROSS_PER_HEAD_YELLOW},
    }


def _validate(field: str, value: Any) -> Any:
    kind = repo.EDITABLE_FIELDS.get(field)
    if kind is None:
        raise ValueError(f"字段 {field} 不允许修改")
    if value is None or value == "":
        return None
    if kind == "text":
        return str(value).strip()[:500]
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} 必须是数字") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} 不能为负数")
    if kind == "int":
        if number != number.to_integral_value():
            raise ValueError(f"{field} 必须是整数")
        return int(number)
    if kind == "rate" and number > 1:
        raise ValueError(f"{field} 是小数比例（15% 填 0.15），不能大于 1")
    if number >= MAX_MONEY:
        raise ValueError(f"{field} 数值过大")
    return number.quantize(Decimal("0.0001"))


def update_row(year: int, dept_code: str, values: dict[str, Any], operator: str) -> dict[str, Any]:
    cleaned = {field: _validate(field, value) for field, value in (values or {}).items()}
    if not repo.update_row(year, dept_code, cleaned, operator or "unknown"):
        raise LookupError(f"{year} 年没有部门 {dept_code}")
    return get_report(year)
