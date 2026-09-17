"""Import frozen Excel history, never join sources or evaluate formulas."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

from openpyxl import load_workbook

from backend.repositories import ebay_inventory_pivot_repository as repository
from backend.repositories.performance_repository import named_lock
from backend.services.ebay_inventory_grade_parser import ERROR_VALUES, WORKBOOK_ERRORS

MAX_FILE_BYTES = 50 * 1024 * 1024
SHEETS = {"库存明细持续更新-US": "美国", "库存明细持续更新-DE": "德国", "库存明细持续更新-UK": "英国"}
# Original workbook headers, not newly calculated fields. Extra source columns
# remain in item_json too, even though the current page has no matching column.
COLUMNS = {
    "中间码+站点": "sku_middle_site_code", "核心码": "sku_middle_code",
    "产品代码": "sku", "品牌": "brand", "产品名称": "product_name", "等级": "grade",
    "海外在途": "overseas_in_transit_quantity", "海外可售": "overseas_sellable_quantity",
    "海外总库存": "overseas_total_quantity", "成都在途": "chengdu_in_transit_quantity",
    "成都可售": "chengdu_sellable_quantity", "采购计划": "procurement_plan_quantity",
    "待出库": "pending_outbound_quantity", "整个周期总库存": "cycle_total_quantity",
    "海外最高库龄": "overseas_max_age_days", "对应仓库": "source_warehouse",
    "近30天销量": "sales_qty_30d", "近3月均销量/预估销量": "average_monthly_sales_3m",
    "在库库销比": "in_stock_sales_ratio", "总库销比": "total_stock_sales_ratio",
    "单价(含税)": "unit_price_tax", "海外可售货值": "overseas_sellable_value",
    "海外总货值": "overseas_total_value", "负责人": "owner",
    "30天谷仓仓租": "warehouse_rent_30d_cny", "总时长（月）": "total_duration_months",
    "总库销比（月）": "total_stock_sales_ratio_months", "按公式申购": "purchase_quantity",
    "实际申购数": "source_actual_purchase_quantity", "最后售出时间": "last_sold_at",
}
TEXT_FIELDS = {"sku_middle_site_code", "sku_middle_code", "sku", "brand", "product_name",
               "grade", "source_warehouse", "owner", "last_sold_at"}
PERCENT_FIELDS = {"in_stock_sales_ratio", "total_stock_sales_ratio", "total_stock_sales_ratio_months"}


def _text(value):
    return "" if value is None else str(value).strip()


def _value(cell, field):
    value = cell.value
    text = _text(value)
    if (cell.data_type in {"e", "f"} or not text or text.upper() in ERROR_VALUES or text.startswith("#")
            or text in {"--", "-"} or isinstance(value, bool)):
        return None
    # Missing caches arrive as None in data_only mode. Never evaluate formulas.
    if field not in TEXT_FIELDS and len(text) > 128:
        return None
    try:
        numeric = Decimal(text)
        if not numeric.is_finite() or numeric == 0:
            return None
    except InvalidOperation:
        numeric = None
    if field in TEXT_FIELDS:
        if isinstance(value, (datetime, date)):
            # Explicit dates may remain dates as text, but month.day numbers
            # (e.g. 7.3) MUST NOT be interpreted as Excel serials or current year.
            return value.isoformat()
        if isinstance(value, (int, float, Decimal)) and field != "last_sold_at":
            return format(numeric, "f").rstrip("0").rstrip(".") if numeric and numeric.as_tuple().exponent < 0 else text
        return text
    if isinstance(value, (date, datetime)):
        return None
    if numeric is None and field in PERCENT_FIELDS and text.endswith("%"):
        try:
            numeric = Decimal(text[:-1].strip()) / 100
        except InvalidOperation:
            pass
    if (numeric is None or not numeric.is_finite() or numeric == 0
            or numeric.as_tuple().exponent < -100 or abs(numeric) >= Decimal("1e20")):
        return None
    return numeric


def parse_history(content: bytes, filename: str) -> dict:
    if PurePosixPath(filename.replace("\\", "/")).suffix.lower() != ".xlsx":
        raise ValueError("历史文件只支持.xlsx")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("历史文件不能为空，且不能超过50MB")
    workbook = None
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 300 * 1024 * 1024:
                raise ValueError("历史文件解压后过大，最大支持300MB")
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
        missing = set(SHEETS) - set(workbook.sheetnames)
        if missing:
            raise ValueError("历史文件缺少工作表：" + "、".join(sorted(missing)))
        days, counts, seen = defaultdict(list), Counter(), set()
        duplicate_rows = missing_sku_rows = empty_cells = source_rows = 0
        for sheet_name, site in SHEETS.items():
            sheet = workbook[sheet_name]
            sheet.reset_dimensions()
            iterator = sheet.iter_rows(max_col=65)
            header = next(iterator, ())
            headers = [_text(cell.value).replace("11月负责人", "负责人") for cell in header]
            required = {"统计时间", "站点", *COLUMNS}
            if not required.issubset(headers) or any(headers.count(key) != 1 for key in required):
                raise ValueError(f"{sheet_name}表头缺失或重复，请使用原始32列表头")
            indices = {key: headers.index(key) for key in required}
            for row_no, cells in enumerate(iterator, 2):
                if row_no > 100001:
                    raise ValueError("单张历史工作表最多支持100000行")
                if not any(_text(cell.value) for cell in cells):
                    continue
                source_rows += 1
                if source_rows > 100000 or any(_text(cell.value) for cell in cells[64:]):
                    raise ValueError("历史文件最多支持100000行、64列")
                raw_date = cells[indices["统计时间"]].value
                if isinstance(raw_date, datetime):
                    stat_date = raw_date.date()
                elif isinstance(raw_date, date):
                    stat_date = raw_date
                else:
                    try:
                        stat_date = date.fromisoformat(_text(raw_date))
                    except ValueError as exc:
                        raise ValueError(f"{sheet_name}第{row_no}行统计时间无效，整份未导入") from exc
                source_site = _text(cells[indices["站点"]].value).upper()
                if source_site and source_site not in {site, sheet_name.rsplit("-", 1)[1]}:
                    raise ValueError(f"{sheet_name}第{row_no}行站点与工作表不一致，整份未导入")
                item = {field: _value(cells[indices[label]], field) for label, field in COLUMNS.items()}
                if item["sku"] is not None and len(item["sku"]) > 255:
                    raise ValueError(f"{sheet_name}第{row_no}行SKU超过255字符")
                empty_cells += sum(value is None for value in item.values())
                missing_sku_rows += int(item["sku"] is None)
                key = (stat_date, site, item["sku"])
                duplicate_rows += int(key in seen)
                seen.add(key)
                item.update(site=site, stat_date=stat_date.isoformat(), history_origin="EXCEL_IMPORT",
                            record_key=f"{sheet_name.rsplit('-', 1)[1]}:{row_no}",
                            source_sheet=sheet_name, source_row=row_no)
                days[stat_date].append(item)
                counts[sheet_name] += 1
        if not days:
            raise ValueError("三个历史工作表中没有数据")
        return {"days": dict(days), "source_rows": source_rows, "sheet_rows": dict(counts),
                "duplicate_rows_preserved": duplicate_rows, "missing_sku_rows": missing_sku_rows,
                "empty_cells": empty_cells, "date_count": len(days),
                "first_import_date": min(days).isoformat(), "latest_import_date": max(days).isoformat()}
    except WORKBOOK_ERRORS as exc:
        raise ValueError("历史文件不是有效Excel或XML已损坏，整份未导入") from exc
    finally:
        if workbook is not None:
            workbook.close()


def import_history(content: bytes, filename: str, operator: str | None = None) -> dict:
    result = parse_history(content, filename)
    days = result.pop("days")
    filename = PurePosixPath(filename.replace("\\", "/")).name[:255]
    with named_lock("inventory:ebay-pivot") as acquired:
        if not acquired:
            raise ValueError("历史数据正在保存，请稍后重试")
        stored = repository.insert_import_days(days, sha256(content).hexdigest(), filename,
                                                _text(operator)[:64] or "SYSTEM")
    return {**result, **stored, "message": "原始行已保存，不合并、不重算、不生成透视；空值、0及错误值显示--。"}
