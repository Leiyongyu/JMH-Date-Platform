from __future__ import annotations

import hashlib
import re
from io import BytesIO
from typing import Any
from uuid import uuid4

import pandas as pd

from backend.parsers.performance_common import (
    money,
    normalize_text,
    parse_brand_code_from_sku,
)


MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
REQUIRED_COLUMNS = {"SKU", "商品销售额", "应收运费"}


def _cell_text(value: Any) -> str:
    """Normalize an Excel scalar without turning an empty cell into the text 'nan'."""
    if value is None or pd.isna(value):
        return ""
    return normalize_text(value)


def _cell_money(value: Any):
    if value is None or pd.isna(value):
        return money(0)
    return money(value)


def parse_inventory_report_ebay_sales_excel(
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
    sheet_name = next(
        (name for name in workbook.sheet_names if name.lower() == "sheet1"),
        workbook.sheet_names[0] if workbook.sheet_names else None,
    )
    if not sheet_name:
        raise ValueError("eBay SKU利润文件没有可读取的工作表")
    frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    frame.columns = [normalize_text(column) for column in frame.columns]
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(
            "eBay SKU利润文件缺少列: " + "、".join(sorted(missing))
        )

    batch_id = str(uuid4())
    rows: list[dict[str, Any]] = []
    skipped_rows = 0
    for index, record in frame.iterrows():
        source_row = int(index) + 2
        sku = _cell_text(record.get("SKU"))
        product_sales = _cell_money(record.get("商品销售额"))
        shipping = _cell_money(record.get("应收运费"))
        if not sku and product_sales == 0 and shipping == 0:
            skipped_rows += 1
            continue
        if not sku:
            raise ValueError(f"第{source_row}行SKU为空，无法匹配负责人")
        rows.append(
            {
                "stat_month": month,
                "sku": sku[:255],
                "brand_code": parse_brand_code_from_sku(sku)[:32],
                "image_url": _cell_text(record.get("图片")) or None,
                "multi_variant": _cell_text(record.get("是否多属性"))[:16] or None,
                "product_sales_amount": product_sales,
                "receivable_shipping_amount": shipping,
                "amount": product_sales + shipping,
                "source_file_name": normalize_text(file_name)[:255],
                "source_sheet": normalize_text(sheet_name)[:128],
                "source_row": source_row,
                "import_batch_id": batch_id,
                "imported_by": normalize_text(operator)[:64] or None,
            }
        )
    if not rows:
        raise ValueError("eBay SKU利润文件没有可导入的数据")

    return {
        "stat_month": month,
        "batch_id": batch_id,
        "file_hash": hashlib.sha256(content).hexdigest(),
        "rows": rows,
        "source_rows": len(frame.index),
        "skipped_rows": skipped_rows,
        "total_amount": sum((row["amount"] for row in rows), money(0)),
    }
