"""Amazon / eBay 售后汇总共用的导出格式。两边的汇总列完全一致，改格式只改这里。"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from openpyxl.styles import Alignment, Font, PatternFill


SUMMARY_HEADERS = (
    "售后原因（大）", "售后原因（小）", "SKU", "售后数量", "订单数量",
    "订单号", "数据来源及售后数量", "数据来源及销量", "销量", "售后率",
)
SUMMARY_WIDTHS = (18, 22, 24, 12, 12, 48, 28, 28, 12, 12)


def write_summary_sheet(sheet, rows: list[dict[str, Any]]) -> None:
    sheet.append(SUMMARY_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4F81BD")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in rows:
        sheet.append((
            row["big_category"], row["small_category"], row["business_sku"],
            float(row["after_quantity"] or 0), int(row["order_count"] or 0),
            row.get("order_numbers") or "", row.get("source_after_quantity_text") or "",
            row.get("source_sales_volume_text") or "", float(row["sales_volume"] or 0),
            float(row["after_sales_rate"] or 0),
        ))
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, width in enumerate(SUMMARY_WIDTHS, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    for cell in sheet["J"][1:]:
        cell.number_format = "0.00%"


def decimal_text(value: Decimal) -> str:
    """Decimal 转去掉多余尾零的文本：Decimal('1.50') -> '1.5'，Decimal('2.000') -> '2'。"""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
