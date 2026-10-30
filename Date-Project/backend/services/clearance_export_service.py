from __future__ import annotations

import tempfile
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from backend.config import settings
from backend.repositories import clearance_repository as repo
from backend.services.clearance_drilldown_service import list_dimensions
from backend.services.clearance_metrics import BUCKETS, AGE_LABELS, total_metrics


SUMMARY_METRICS = [column for bucket, label in zip(BUCKETS, AGE_LABELS) for column in [
    (label.split('（')[0] + '去重SKU数', f'inventory_{bucket}_sku_count', 'qty'),
    (label.split('（')[0] + '库存数量', f'inventory_{bucket}_qty', 'qty'),
    (label.split('（')[0] + '库龄成本', f'inventory_{bucket}_cost', 'money'),
    (label.split('（')[0] + '上月库龄成本', f'previous_month_{bucket}_cost', 'money'),
    (label.split('（')[0] + '差值（上月－本月）', f'inventory_{bucket}_variance', 'money'),
]] + [
    ("海外仓/FBA合计去重SKU数", "total_inventory_sku_count", "qty"),
    ("海外仓/FBA合计库存数量", "total_inventory_qty", "qty"),
    ("海外仓/FBA合计库龄成本", "total_inventory_cost", "money"),
]


def export_monthly_summary(pull_month: str) -> tuple[str, str]:
    """Export the selected snapshot using the same group/drilldown readers as UI.

    No refresh or repricing. Owners aggregate ALL sites by their month's brand
    rules. CTU cannot be allocated to shops/people and is group-only.
    """
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", pull_month or ""):
        raise ValueError("请选择有效的快照月份（YYYY-MM）")
    group_data = repo.list_groups(pull_month)
    groups = [dict(row) for row in group_data['items']]
    if not groups:
        raise ValueError(f"{pull_month} 没有可导出的滞销清货数据")
    source = repo.metric_source_rows(pull_month)
    stores, people, sites = [], [], []
    seen_ctu_us3 = False
    for row in groups:
        code = row["group_code"]
        row["pull_month"] = pull_month
        if code in {"US2-MJ", "US1-ZXY"}:
            # The UI merges these CTU cells. In a flat Excel sheet keep the
            # shared US3 value once, regardless of group ordering/missing row.
            if seen_ctu_us3:
                row["ctu_over_30_qty"] = row["ctu_over_30_cost"] = None
                row["note"] = "成都仓为共享US3，已计入另一拆分组行，不重复计数"
            else:
                row["note"] = "成都仓为US2-MJ与US1-ZXY共享US3，仅在本行计一次"
                seen_ctu_us3 = True
        if code == "EBAY-1":
            sites = list_dimensions(pull_month, code)["items"]
        else:
            stores.extend({**item, "group_code": code} for item in
                          list_dimensions(pull_month, code)["items"])
        people.extend({**item, 'group_code': code} for item in
                      list_dimensions(pull_month, code, dimension='OWNER')['items'])

    month_header = [("快照月份", "pull_month", "text")]
    group_headers = month_header + [
        ("区域", "region_name", "text"), ("组别", "group_code", "text"),
        ("店铺/仓库数", "shop_count", "qty"),
        ("成都仓30天以上库存数量", "ctu_over_30_qty", "qty"),
        ("成都仓30天以上库龄成本", "ctu_over_30_cost", "money"),
    ] + SUMMARY_METRICS + [("备注", "note", "text")]
    workbook = Workbook(write_only=True)
    group_total = {**group_data['summary'], 'pull_month':pull_month, 'group_code':'合计', 'is_total':1}
    _append_sheet(workbook, f"组别-{pull_month}", group_headers, groups + [group_total],
                  [24] * (len(group_headers) - 1) + [62], "2563EB")
    for label, identity, items in [("店铺", "中文店铺名称", stores),
                                    ("个人", "负责人", people),
                                    ("站点", "eBay站点", sites)]:
        headers = month_header + [("组别", "group_code", "text"),
                                  (identity, "dimension_name", "text"),
                                  ("本月明细行数", "source_row_count", "qty")] + SUMMARY_METRICS
        output = [{**item, "pull_month": pull_month,
                   "group_code": item.get("group_code", "EBAY-1")} for item in items]
        selected = [row for row in source if label == '个人' or
                    row['platform_code'] == ('AMZ' if label == '店铺' else 'EBAY')]
        if items:
            output.append({**total_metrics(selected, pull_month), 'pull_month':pull_month,
                           'dimension_name':'合计', 'is_total':1})
        _append_sheet(workbook, f"{label}-{pull_month}", headers, output,
                      [24] * len(headers), "2563EB")
    export_dir = Path(settings.export_output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", prefix=f"clearance_summary_{pull_month}_",
                                     dir=str(export_dir), delete=False) as temp:
        path = temp.name
    try:
        workbook.save(path)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return path, f"{pull_month}-滞销清货当月汇总-{timestamp}.xlsx"


FBA_HEADERS = [
    ("快照月份", "pull_month", "text"),
    ("区域", "region_name", "text"),
    ("组别", "group_code", "text"),
    ("店铺名称", "store_name", "text"),
    ("共享店铺列表", "shared_store_names", "text"),
    ("MSKU", "seller_sku", "text"),
    ("SKU", "sku", "text"),
    ("0-30天数量", "inv_age_0_to_30_days", "qty"),
    ("0-30天成本", "inv_age_0_to_30_price", "money"),
    ("31-60天数量", "inv_age_31_to_60_days", "qty"),
    ("31-60天成本", "inv_age_31_to_60_price", "money"),
    ("61-90天数量", "inv_age_61_to_90_days", "qty"),
    ("61-90天成本", "inv_age_61_to_90_price", "money"),
    ("0-90天数量", "inv_age_0_to_90_days", "qty"),
    ("0-90天成本", "inv_age_0_to_90_price", "money"),
    ("91-180天数量", "inv_age_91_to_180_days", "qty"),
    ("91-180天成本", "inv_age_91_to_180_price", "money"),
    ("181-270天数量", "inv_age_181_to_270_days", "qty"),
    ("181-270天成本", "inv_age_181_to_270_price", "money"),
    ("271-330天数量", "inv_age_271_to_330_days", "qty"),
    ("271-330天成本", "inv_age_271_to_330_price", "money"),
    ("271-365天数量", "inv_age_271_to_365_days", "qty"),
    ("271-365天成本", "inv_age_271_to_365_price", "money"),
    ("331-365天数量", "inv_age_331_to_365_days", "qty"),
    ("331-365天成本", "inv_age_331_to_365_price", "money"),
    ("365天以上数量", "inv_age_365_plus_days", "qty"),
    ("365天以上成本", "inv_age_365_plus_price", "money"),
    ("拉取时间", "pulled_at", "datetime"),
    ("同步批次ID", "sync_batch_id", "text"),
]

CTU_HEADERS = [
    ("快照月份", "pull_month", "text"),
    ("组别", "group_code", "text"),
    ("仓库ID", "wid", "text"),
    ("仓库名称", "warehouse_name", "text"),
    ("SKU", "sku", "text"),
    ("本地产品ID", "product_id", "text"),
    ("实际库存总量", "product_total", "qty"),
    ("单位库存成本", "stock_price", "money"),
    ("平均库龄天数", "average_age", "qty"),
    ("30天以上库存数量", "over_30_qty", "qty"),
    ("30天以上库龄成本", "over_30_cost", "money"),
    ("库龄分档原值", "stock_age_list", "text"),
    ("拉取时间", "pulled_at", "datetime"),
    ("同步批次ID", "sync_batch_id", "text"),
]


def export_inventory_age_details(pull_month: str | None) -> tuple[str, str]:
    fba_data = repo.inventory_age_details(pull_month)
    ctu_data = repo.ctu_inventory_age_details(pull_month)
    month = fba_data["pull_month"] or ctu_data["pull_month"]
    fba_rows = fba_data["items"]
    ctu_rows = ctu_data["items"]
    if not month or (not fba_rows and not ctu_rows):
        raise ValueError(f"{pull_month or '当前月份'} 没有可导出的库龄明细")

    workbook = Workbook(write_only=True)
    if fba_rows:
        _append_sheet(
            workbook,
            "库龄明细",
            FBA_HEADERS,
            fba_rows,
            [12, 12, 12, 28, 62, 28, 24] + [20] * 20 + [20, 38],
            "2563EB",
        )
    if ctu_rows:
        _append_sheet(
            workbook,
            "成都仓30天以上明细",
            CTU_HEADERS,
            ctu_rows,
            [12, 12, 14, 25, 28, 18, 18, 18, 18, 21, 21, 45, 20, 38],
            "D97706",
        )

    export_dir = Path(settings.export_output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    download_name = f"{month}-库龄明细-{timestamp}.xlsx"
    temp = tempfile.NamedTemporaryFile(
        suffix=".xlsx",
        prefix=f"inventory_age_detail_{month}_",
        dir=str(export_dir),
        delete=False,
    )
    temp.close()
    workbook.save(temp.name)
    return temp.name, download_name


def _append_sheet(
    workbook: Workbook,
    title: str,
    headers: list[tuple[str, str, str]],
    rows: list[dict[str, Any]],
    widths: list[int],
    header_color: str,
) -> None:
    sheet = workbook.create_sheet(title=title)
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    header_fill = PatternFill("solid", fgColor=header_color)
    header_font = Font(color="FFFFFF", bold=True)
    header_cells = []
    for column_title, _, _ in headers:
        cell = WriteOnlyCell(sheet, value=column_title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        header_cells.append(cell)
    sheet.append(header_cells)

    for row in rows:
        cells = []
        for _, key, value_type in headers:
            value = row.get(key)
            if key == "store_name" and not str(value or "").strip():
                value = "0"
            cell = WriteOnlyCell(sheet, value=_excel_value(value))
            if value_type == "text" and isinstance(value, str):
                cell.data_type = "s"  # Store names are data, never Excel formulas.
            if value_type == "qty":
                cell.number_format = "#,##0.######"
            elif value_type == "money":
                cell.number_format = "#,##0.00"
            elif value_type == "datetime":
                cell.number_format = "yyyy-mm-dd hh:mm:ss"
            if row.get('is_total'):
                cell.font = Font(bold=True, color='172033')
                cell.fill = PatternFill('solid', fgColor='EAF2FF')
            cells.append(cell)
        sheet.append(cells)
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(headers))}{len(rows) + 1 - int(bool(rows and rows[-1].get('is_total')))}"
    )


def _excel_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value
    return value
