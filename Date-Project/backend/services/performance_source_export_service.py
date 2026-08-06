from __future__ import annotations

import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from backend.config import settings
from backend.database import db_connection
from backend.repositories.performance_repository import get_amz_profit_rows


AMZ_SOURCE_HEADERS = [
    ("统计月份", "stat_month"),
    ("领星店铺SID", "sid"),
    ("店铺名称", "store_name"),
    ("MSKU", "seller_sku"),
    ("本地SKU", "local_sku"),
    ("ASIN", "asin"),
    ("国家", "country"),
    ("币种", "currency_code"),
    ("毛利润", "gross_profit"),
    ("销售额", "amount"),
    ("退款金额", "refund_amount"),
    ("净销售额", "net_sales_amount"),
    ("领星原始Listing负责人", "principal_names"),
    ("同步批次ID", "sync_batch_id"),
    ("同步时间", "sync_time"),
]


def export_amz_performance_source(
    stat_month: str,
) -> tuple[str, str]:
    with db_connection() as connection:
        rows = get_amz_profit_rows(connection, stat_month)

    if not rows:
        raise ValueError(f"{stat_month} 没有可导出的 AMZ 绩效源数据")

    headers = list(AMZ_SOURCE_HEADERS)

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title="AMZ Source")
    sheet.append([title for title, _ in headers])
    for row in rows:
        sheet.append([_excel_value(row.get(key)) for _, key in headers])

    export_dir = Path(settings.export_output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(
        suffix=".xlsx",
        prefix=f"amz_performance_source_{stat_month}_",
        dir=str(export_dir),
        delete=False,
    )
    temp.close()
    workbook.save(temp.name)
    return temp.name, f"amz_performance_source_{stat_month}.xlsx"


def _excel_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ", timespec="seconds") if isinstance(value, datetime) else value.isoformat()
    return value
