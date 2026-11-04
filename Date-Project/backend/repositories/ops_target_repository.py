"""财务中心「运营目标与人效」的存储：fin_ops_dept_target，一行 = 年度 × 部门，手工维护。"""
from __future__ import annotations

from typing import Any

from backend.database import db_connection

TABLE = "fin_ops_dept_target"

# 可在页面上修改的字段 → 类型（money=万元金额，rate=小数比例，int=整数）
EDITABLE_FIELDS: dict[str, str] = {
    "floor_target": "money", "sprint_target": "money", "actual_amount": "money",
    "new_product_target": "int", "new_product_actual": "int", "target_margin_rate": "rate",
    "est_gross_profit": "money", "labor_cost_pack": "money",
    **{f"q{q}_target": "money" for q in range(1, 5)},
    **{f"q{q}_actual": "money" for q in range(1, 5)},
    **{f"m{m:02d}_target": "money" for m in range(1, 13)},
    **{f"q{q}_efficiency_target": "money" for q in range(1, 5)},
    "annual_efficiency_target": "money", "headcount": "int", "remark": "text",
}
COLUMNS = ("target_year", "dept_code", "sort_no", *EDITABLE_FIELDS, "updated_by", "updated_at")


def years() -> list[int]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT DISTINCT target_year FROM {TABLE} ORDER BY target_year DESC")
        return [int(row["target_year"]) for row in cursor.fetchall()]


def rows(year: int) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(COLUMNS)} FROM {TABLE} WHERE target_year=%s ORDER BY sort_no, dept_code",
            (year,),
        )
        return list(cursor.fetchall())


def update_row(year: int, dept_code: str, values: dict[str, Any], operator: str) -> bool:
    """只更新传入的字段（值已由 service 校验）；部门不存在时返回 False。"""
    unknown = set(values) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"不允许修改的字段：{'、'.join(sorted(unknown))}")
    if not values:
        return True
    assignments = ", ".join(f"{field}=%s" for field in values)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {TABLE} WHERE target_year=%s AND dept_code=%s", (year, dept_code))
            if not cursor.fetchone():
                return False
            cursor.execute(
                f"UPDATE {TABLE} SET {assignments}, updated_by=%s WHERE target_year=%s AND dept_code=%s",
                (*values.values(), operator[:64], year, dept_code),
            )
        connection.commit()
    return True
