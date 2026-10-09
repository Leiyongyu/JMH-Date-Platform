from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Callable

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from backend.services.inventory_report_etl_service import (
    get_department_summary,
    get_dimension_summary,
)


EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
DIMENSION_LABELS = {"GROUP": "组别", "STORE": "店铺", "OWNER": "负责人"}
Header = tuple[str, Callable[[dict[str, Any]], Any], str]


def export_monthly_inventory_report(
    stat_month: str | None,
    dimension_type: str,
) -> tuple[str, bytes]:
    """导出指定维度；维度列表由 ERP 按当前用户权限生成。"""
    dimension = str(dimension_type or "").strip().upper()
    permission_filtered = dimension.startswith("VISIBLE:")
    requested = (dimension.removeprefix("VISIBLE:") if permission_filtered else dimension).split(",")
    if dimension == "ALL":
        dimensions = tuple(DIMENSION_LABELS)
    elif (not requested or len(requested) != len(set(requested))
          or any(item not in DIMENSION_LABELS for item in requested)):
        raise ValueError("dimension_type必须是ALL或GROUP、STORE、OWNER的非重复组合")
    else:
        dimensions = tuple(item for item in DIMENSION_LABELS if item in requested)

    workbook = Workbook(write_only=True)
    combined = permission_filtered or len(dimensions) > 1 or dimension == "ALL"
    report_month = None
    has_rows = False
    for current in dimensions:
        if current == "GROUP":
            data = get_department_summary(stat_month)
            rows = list(data.get("items") or [])
            headers = _group_headers(data.get("report_month"))
        else:
            data = get_dimension_summary(current, stat_month)
            detail_rows = list(data.get("items") or [])
            total = data.get("total")
            rows = ([total] if total else []) + detail_rows
            headers = _dimension_headers(current)
        current_month = data.get("report_month") or stat_month or "当前月份"
        if report_month is not None and current_month != report_month:
            raise ValueError("三个维度的月度库存统计月份不一致，请重新选择月份")
        report_month = current_month
        if not combined and not rows:
            raise ValueError(f"{report_month} 没有可导出的月度库存数据")
        has_rows = has_rows or bool(rows)
        sheet_title = (
            {"GROUP": "组别", "STORE": "店铺", "OWNER": "个人"}[current]
            if combined else f"月度库存-{DIMENSION_LABELS[current]}"
        )
        _append_sheet(workbook, sheet_title, headers, rows)
    if not has_rows:
        raise ValueError(f"{report_month} 没有可导出的月度库存数据")

    output = BytesIO()
    workbook.save(output)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename_label = "汇总" if combined else DIMENSION_LABELS[dimensions[0]]
    filename = f"{report_month}-月度库存-{filename_label}-{timestamp}.xlsx"
    return filename, output.getvalue()


def _group_headers(report_month: str | None) -> list[Header]:
    business_label = _month_label(report_month, "当月")
    next_label = _month_label(_next_month(report_month), "次月")
    return [
        ("组别", _department_name, "text"),
        ("总货值", _field("total_goods_value"), "money"),
        ("本地仓-期末在途数量", _field("local_end_in_transit_qty"), "qty"),
        ("本地仓-期末在途总成本", _field("local_end_in_transit_total_cost"), "money"),
        ("本地仓-期末库存数量", _field("local_end_inventory_qty"), "qty"),
        ("本地仓-期末库存总成本", _field("local_end_inventory_total_cost"), "money"),
        ("海外仓/FBA仓-期末在途数量", _combined("overseas_end_in_transit_qty", "fba_end_in_transit_qty"), "qty"),
        ("海外仓/FBA仓-期末在途总成本", _combined("overseas_end_in_transit_total_cost", "fba_end_in_transit_total_cost"), "money"),
        ("海外仓/FBA仓-期末库存数量", _combined("overseas_end_inventory_qty", "fba_end_inventory_qty"), "qty"),
        ("海外仓/FBA仓-期末库存总成本", _combined("overseas_end_inventory_total_cost", "fba_end_inventory_total_cost"), "money"),
        ("FBA在途金额+FBA在库金额", _field("fba_transit_inventory_amount"), "money"),
        ("库存健康度", _field("inventory_health_rate"), "percent"),
        ("销售目标（USD）", _field("sales_target_usd"), "money"),
        ("实际达成（USD）", _field("actual_achievement_amount_usd"), "money"),
        ("目标达成率", _field("target_achievement_rate"), "percent"),
        (f"{next_label}周转天数（货值）", _field("turnover_days_by_value"), "decimal"),
        (f"{business_label}初库存数量", _field("next_month_opening_inventory_qty"), "qty"),
        (f"{business_label}销量", _field("monthly_sales_qty"), "qty"),
        (f"{next_label}初库销比", _field("opening_inventory_sales_ratio"), "decimal"),
        (f"{business_label}周转天数（SKU）", _field("turnover_days_by_sku"), "decimal"),
        ("成都仓30天以上货值", _field("ctu_over_30_cost"), "money"),
        ("90-180库龄成本", _field("inventory_age_90_180_cost"), "money"),
        ("180+库龄成本", _field("inventory_age_180_plus_cost"), "money"),
    ]


def _dimension_headers(dimension: str) -> list[Header]:
    first_title = "店铺" if dimension == "STORE" else "负责人"
    headers = [
        (first_title, _dimension_name(dimension), "text"),
        ("平台", _platform_name, "text"),
        ("组别", _department_name, "text"),
        ("总货值", _field("total_goods_value"), "money"),
        ("海外仓/FBA仓-期末在途数量", _combined("overseas_end_in_transit_qty", "fba_end_in_transit_qty"), "qty"),
        ("海外仓/FBA仓-期末在途总成本", _combined("overseas_end_in_transit_total_cost", "fba_end_in_transit_total_cost"), "money"),
        ("海外仓/FBA仓-期末库存数量", _combined("overseas_end_inventory_qty", "fba_end_inventory_qty"), "qty"),
        ("海外仓/FBA仓-期末库存总成本", _combined("overseas_end_inventory_total_cost", "fba_end_inventory_total_cost"), "money"),
        ("FBA在途金额+FBA在库金额", _field("fba_transit_inventory_amount"), "money"),
        ("库存健康度", _field("inventory_health_rate"), "percent"),
        ("销售目标（USD）", _field("sales_target_usd"), "money"),
        ("实际达成（USD）", _field("actual_achievement_amount_usd"), "money"),
        ("目标达成率", _field("target_achievement_rate"), "percent"),
    ]
    if dimension == "OWNER":
        headers.extend([
            ("成都仓30天以上货值（仅eBay）", _field("ctu_over_30_cost"), "money"),
            ("90-180库龄成本", _field("inventory_age_90_180_cost"), "money"),
            ("180+库龄成本", _field("inventory_age_180_plus_cost"), "money"),
            ("所属组别销售目标（USD）", _field("group_sales_target_usd"), "money"),
        ])
    return headers


def _append_sheet(
    workbook: Workbook,
    title: str,
    headers: list[Header],
    rows: list[dict[str, Any]],
) -> None:
    sheet = workbook.create_sheet(title=title)
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    header_fill = PatternFill("solid", fgColor="2563EB")
    header_font = Font(color="FFFFFF", bold=True)
    header_cells = []
    for column_index, (column_title, _accessor, _value_type) in enumerate(
        headers, start=1
    ):
        sheet.column_dimensions[get_column_letter(column_index)].width = max(
            14, min(32, len(column_title) * 2 + 4)
        )
        cell = WriteOnlyCell(sheet, value=column_title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        header_cells.append(cell)
    sheet.append(header_cells)

    for row in rows:
        cells = []
        for _column_title, accessor, value_type in headers:
            value = accessor(row)
            cell = WriteOnlyCell(
                sheet,
                value=_excel_value(value, value_type),
            )
            if value_type == "qty":
                cell.number_format = "#,##0.######"
            elif value_type == "money":
                cell.number_format = "#,##0.00"
            elif value_type == "percent":
                cell.number_format = "0.00%"
            elif value_type == "decimal":
                cell.number_format = "#,##0.00"
            cells.append(cell)
        sheet.append(cells)
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    )


def _field(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda row: row.get(key)


def _department_name(row: dict[str, Any]) -> str:
    value = row.get("department_name") or row.get("department_code") or ""
    return "eBay" if value == "EBAY-1" else str(value)


def _combined(
    left_key: str,
    right_key: str,
) -> Callable[[dict[str, Any]], Any]:
    return lambda row: (
        None if row.get("is_age_cost_only") or (
            row.get("historical_import")
            and row.get(left_key) is None and row.get(right_key) is None
        ) else _decimal(row.get(left_key)) + _decimal(row.get(right_key))
    )


def _dimension_name(
    dimension: str,
) -> Callable[[dict[str, Any]], str]:
    def value(row: dict[str, Any]) -> str:
        if int(row.get("is_dimension_total") or 0) == 1:
            return "合计（仅Amazon FBA）" if dimension == "STORE" else "合计"
        name = str(row.get("dimension_value") or "")
        return name + "（仅库龄成本）" if row.get("is_age_cost_only") else name

    return value


def _platform_name(row: dict[str, Any]) -> str:
    platform = str(row.get("platform_code") or "").upper()
    if platform == "EBAY":
        return "eBay"
    return "Amazon" if platform == "AMZ" else ""


def _excel_value(value: Any, value_type: str) -> Any:
    if value is None or value == "":
        return None
    if value_type == "text":
        return str(value)
    return float(_decimal(value))


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _next_month(month: str | None) -> str | None:
    if not month or len(month) != 7:
        return None
    year, month_number = (int(part) for part in month.split("-", 1))
    if month_number == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month_number + 1:02d}"


def _month_label(month: str | None, fallback: str) -> str:
    if not month or len(month) != 7:
        return fallback
    return f"{int(month[5:7])}月"
