from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import uuid4

import pandas as pd

from backend.parsers.performance_common import money, normalize_text


MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
SHEET_NAME = "产品信息"
REQUIRED_COLUMNS = {"采购单号", "采购仓库", "SKU", "单价", "待到货量"}


def _cell_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return normalize_text(value)


def _cell_number(value: Any, source_row: int, column: str) -> Decimal:
    if value is None or pd.isna(value) or (
        isinstance(value, str) and not value.strip()
    ):
        raise ValueError(f"第{source_row}行{column}为空")
    try:
        result = money(value)
    except ValueError as exc:
        raise ValueError(f"第{source_row}行{column}格式不正确: {value}") from exc
    if result < 0:
        raise ValueError(f"第{source_row}行{column}不能小于0")
    return result


def purchase_warehouse_assignment(warehouse: str) -> tuple[str, str, str]:
    """Return platform, source group and department for a purchase warehouse."""
    normalized = normalize_text(warehouse).upper().replace(" ", "")
    if not normalized:
        raise ValueError("采购仓库为空")
    if "EBAY" in normalized:
        return "EBAY", "EBAY-1", "EBAY-1"
    if "AMZ" not in normalized:
        raise ValueError(f"无法识别采购仓库平台: {warehouse}")
    if "US3" in normalized:
        # 页面将 AMZ-US2-MJ 与 AMZ-US1-ZXY 的本地在途单元格合并，
        # US3 金额只落在首行，防止汽配小计重复累计。
        return "AMZ", "US3", "AMZ-US2-MJ"
    if "US2" in normalized:
        return "AMZ", "US2", "AMZ-US2"
    if "US1" in normalized:
        return "AMZ", "US1", "AMZ-US1"
    if "EU" in normalized or "UK" in normalized:
        return "AMZ", "EU", "AMZ-EU"
    raise ValueError(f"无法识别Amazon采购仓库组别: {warehouse}")


def parse_inventory_report_purchase_order_excel(
    content: bytes,
    file_name: str,
    stat_month: str,
    operator: str | None = None,
) -> dict[str, Any]:
    month = normalize_text(stat_month)
    if not MONTH_RE.fullmatch(month):
        raise ValueError("归属年月格式必须为YYYY-MM")
    if not content:
        raise ValueError("上传文件为空")

    workbook = pd.ExcelFile(BytesIO(content))
    if SHEET_NAME not in workbook.sheet_names:
        raise ValueError(f"采购单文件缺少“{SHEET_NAME}”工作表")
    frame = pd.read_excel(workbook, sheet_name=SHEET_NAME, dtype=object)
    frame.columns = [normalize_text(column) for column in frame.columns]
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError("采购单文件缺少列: " + "、".join(sorted(missing)))

    # Excel 的采购单号、采购仓库纵向合并后，pandas 只会读取首行值。
    for column in ("采购单号", "采购仓库", "采购仓库（明细）"):
        if column in frame.columns:
            frame[column] = frame[column].ffill()

    batch_id = str(uuid4())
    rows: list[dict[str, Any]] = []
    skipped_rows = 0
    for index, record in frame.iterrows():
        source_row = int(index) + 2
        sku = _cell_text(record.get("SKU"))
        warehouse = _cell_text(record.get("采购仓库"))
        warehouse_detail = _cell_text(record.get("采购仓库（明细）")) or warehouse
        if not sku and not warehouse_detail:
            skipped_rows += 1
            continue
        if not sku:
            raise ValueError(f"第{source_row}行SKU为空")
        if not warehouse_detail:
            raise ValueError(f"第{source_row}行采购仓库为空")

        unit_price = _cell_number(record.get("单价"), source_row, "单价")
        pending_qty = _cell_number(record.get("待到货量"), source_row, "待到货量")
        try:
            platform, group_code, department = purchase_warehouse_assignment(
                warehouse_detail
            )
        except ValueError as exc:
            raise ValueError(f"第{source_row}行{exc}") from exc

        rows.append(
            {
                "stat_month": month,
                "purchase_order_no": _cell_text(record.get("采购单号"))[:100],
                "purchase_warehouse": warehouse[:255],
                "purchase_warehouse_detail": warehouse_detail[:255],
                "sku": sku[:255],
                "store_name": _cell_text(record.get("店铺"))[:255] or None,
                "unit_price": unit_price,
                "pending_arrival_qty": pending_qty,
                "sku_pending_total_cost": money(unit_price * pending_qty),
                "product_dimension": _cell_text(record.get("产品维度"))[:255] or None,
                "platform_code": platform,
                "group_code": group_code,
                "department_code": department,
                "source_file_name": normalize_text(file_name)[:255],
                "source_sheet": SHEET_NAME,
                "source_row": source_row,
                "import_batch_id": batch_id,
                "imported_by": normalize_text(operator)[:64] or None,
            }
        )
    if not rows:
        raise ValueError("采购单文件没有可导入的数据")

    return {
        "stat_month": month,
        "batch_id": batch_id,
        "file_hash": hashlib.sha256(content).hexdigest(),
        "rows": rows,
        "source_rows": len(frame.index),
        "skipped_rows": skipped_rows,
        "total_pending_arrival_qty": sum(
            (row["pending_arrival_qty"] for row in rows), Decimal("0")
        ),
        "total_pending_cost": sum(
            (row["sku_pending_total_cost"] for row in rows), Decimal("0")
        ),
    }
