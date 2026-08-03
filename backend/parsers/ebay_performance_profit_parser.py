from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Any

import pandas as pd

from backend.parsers.performance_common import (
    extract_month_from_filename,
    money,
    normalize_text,
    parse_brand_code_from_sku,
)


REQUIRED_COLUMNS = {
    "SKU",
    "图片",
    "是否多属性",
    "利润",
    "商品销售额",
    "应收运费",
    "退款金额",
}


def parse_ebay_profit_excel(
    content: bytes,
    file_name: str,
    import_batch_id: str,
) -> dict[str, Any]:
    stat_month = extract_month_from_filename(file_name)
    workbook = pd.ExcelFile(BytesIO(content))
    sheet_name = _find_sheet(workbook.sheet_names, "sheet1")
    if not sheet_name:
        raise ValueError("eBay利润文件必须包含 Sheet1")
    df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    missing = REQUIRED_COLUMNS - set(str(col).strip() for col in df.columns)
    if missing:
        raise ValueError(f"eBay利润文件缺少列: {', '.join(sorted(missing))}")

    rows = []
    raw_rows = []
    totals = {
        "gross_profit": money(0),
        "sales_amount": money(0),
        "refund_amount": money(0),
        "net_sales_amount": money(0),
    }
    for index, record in df.iterrows():
        source_row = int(index) + 2
        raw = {str(key): _json_value(value) for key, value in record.to_dict().items()}
        sku = normalize_text(record.get("SKU"))
        gross_profit = money(record.get("利润"))
        product_sales_amount = money(record.get("商品销售额"))
        receivable_shipping_amount = money(record.get("应收运费"))
        refund_amount = money(record.get("退款金额"))
        if not sku and all(
            value == money(0)
            for value in [
                gross_profit,
                product_sales_amount,
                receivable_shipping_amount,
                refund_amount,
            ]
        ):
            continue
        if not sku:
            sku = "[SKU 未填写]"
        sales_amount = product_sales_amount + receivable_shipping_amount
        net_sales_amount = sales_amount - refund_amount
        row = {
            "stat_month": stat_month,
            "sku": sku,
            "brand_code": parse_brand_code_from_sku(sku),
            "image_url": normalize_text(record.get("图片")) or None,
            "multi_variant": normalize_text(record.get("是否多属性")) or None,
            "gross_profit": gross_profit,
            "product_sales_amount": product_sales_amount,
            "receivable_shipping_amount": receivable_shipping_amount,
            "sales_amount": sales_amount,
            "refund_amount": refund_amount,
            "net_sales_amount": net_sales_amount,
            "source_file_name": file_name,
            "source_sheet": sheet_name,
            "source_row": source_row,
            "import_batch_id": import_batch_id,
        }
        rows.append(row)
        raw_rows.append(
            {
                "stat_month": stat_month,
                "source_file_name": file_name,
                "source_sheet": sheet_name,
                "source_row": source_row,
                "raw_json": json.dumps(raw, ensure_ascii=False, default=str),
                "import_batch_id": import_batch_id,
            }
        )
        for key in totals:
            totals[key] += row[key]

    return {
        "stat_month": stat_month,
        "file_hash": hashlib.sha256(content).hexdigest(),
        "rows": rows,
        "raw_rows": raw_rows,
        "totals": {key: str(value) for key, value in totals.items()},
    }


def _find_sheet(sheet_names: list[str], expected_lower: str) -> str | None:
    for sheet_name in sheet_names:
        if sheet_name.lower() == expected_lower:
            return sheet_name
    return None


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value
