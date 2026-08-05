from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from uuid import uuid4

import pandas as pd


MONTH_PATTERN = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
COST_91_HEADERS = ("海外仓90-180货值", "海外仓91-180货值")
COST_181_HEADERS = ("海外仓180+货值", "海外仓181+货值", "海外仓181天以上货值")


def parse_inventory_age_cost_excel(content: bytes, file_name: str) -> dict[str, Any]:
    workbook = pd.ExcelFile(BytesIO(content))
    month_sheets = [name.strip() for name in workbook.sheet_names if MONTH_PATTERN.fullmatch(name.strip())]
    if not month_sheets:
        raise ValueError("库存成本文件必须包含名称为 YYYY-MM 的月份工作表，例如 2026-07")
    if len(month_sheets) > 1:
        raise ValueError("库存成本文件只能包含一个 YYYY-MM 月份工作表")

    sheet_name = month_sheets[0]
    frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    frame.columns = [str(column).strip() for column in frame.columns]
    cost_91_column = _find_column(frame, COST_91_HEADERS)
    cost_181_column = _find_column(frame, COST_181_HEADERS)
    if "部门" not in frame.columns:
        raise ValueError(f"{sheet_name} 缺少列：部门")

    batch_id = str(uuid4())
    rows: list[dict[str, Any]] = []
    seen_departments: dict[str, int] = {}
    for index, record in frame.iterrows():
        source_row = int(index) + 2
        department_code = _text(record.get("部门")).upper()
        if not department_code:
            continue
        if department_code in seen_departments:
            raise ValueError(
                f"{sheet_name} 第{source_row}行部门“{department_code}”与"
                f"第{seen_departments[department_code]}行重复"
            )
        seen_departments[department_code] = source_row
        rows.append({
            "cost_month": sheet_name,
            "department_code": department_code,
            "group_code": _group_code(department_code),
            "inventory_91_180_cost": _money(record.get(cost_91_column), sheet_name, source_row, cost_91_column),
            "inventory_181_plus_cost": _money(record.get(cost_181_column), sheet_name, source_row, cost_181_column),
            "source_file_name": file_name,
            "source_sheet": sheet_name,
            "source_row": source_row,
            "import_batch_id": batch_id,
        })
    if not rows:
        raise ValueError(f"{sheet_name} 没有可导入的数据行")
    if not any(row["group_code"] for row in rows):
        raise ValueError(f"{sheet_name} 没有 AMZ 部门数据")
    return {
        "batch_id": batch_id,
        "file_hash": hashlib.sha256(content).hexdigest(),
        "cost_month": sheet_name,
        "rows": rows,
        "amz_rows": sum(1 for row in rows if row["group_code"]),
    }


def _find_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    column = next((candidate for candidate in candidates if candidate in frame.columns), None)
    if column:
        return column
    raise ValueError(f"库存成本文件缺少列：{' 或 '.join(candidates)}")


def _group_code(department_code: str) -> str | None:
    if not department_code.startswith("AMZ-"):
        return None
    return department_code.removeprefix("AMZ-")


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _money(value: Any, sheet: str, row: int, column: str) -> Decimal:
    if value is None or pd.isna(value) or not str(value).strip():
        return Decimal("0")
    text = str(value).replace(",", "").replace("￥", "").replace("¥", "").strip()
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{sheet} 第{row}行“{column}”不是有效金额：{value}") from exc
    if result < 0:
        raise ValueError(f"{sheet} 第{row}行“{column}”不能为负数")
    return result
