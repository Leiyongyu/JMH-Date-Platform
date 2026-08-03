from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from uuid import uuid4

import pandas as pd


COLUMNS = {
    "合同编号": "contract_no",
    "报关单号": "customs_declaration_no",
    "出口日期": "export_date",
    "出口口岸": "export_port",
    "报关合同金额（USD)": "declared_contract_amount_usd",
    "出口金额（USD)": "export_amount_usd",
    "月度汇率": "monthly_exchange_rate",
    "回款金额（USD)": "payment_amount_usd",
    "收汇金额（USD）": "foreign_exchange_received_usd",
    "核心流水号": "bank_transaction_no",
    "实际汇率": "actual_exchange_rate",
    "回单结汇金额（RMB）": "settlement_receipt_amount_rmb",
    "收汇时间": "receipt_date",
    "差额（USD)": "difference_usd",
}

NUMERIC_FIELDS = {
    "declared_contract_amount_usd", "export_amount_usd", "monthly_exchange_rate",
    "payment_amount_usd", "foreign_exchange_received_usd", "actual_exchange_rate",
    "settlement_receipt_amount_rmb", "difference_usd",
}
DATE_FIELDS = {"export_date", "receipt_date"}


def normalize_header(value: Any) -> str:
    """统一全半角括号、换行和空格，兼容不同月份回款模板的表头写法。"""
    return (
        re.sub(r"\s+", "", str(value or ""))
        .replace("（", "(")
        .replace("）", ")")
    )


def clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip() or None
    return value


def text(value: Any) -> str | None:
    value = clean(value)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def number(value: Any) -> Decimal | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def date_value(value: Any) -> date | None:
    value = clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def parse_receipts_workbook(
    content: bytes,
    file_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # 只读Sheet1的前15列，明确忽略第16列“结汇时间”。
    frame = pd.read_excel(
        BytesIO(content), sheet_name="Sheet1", header=0, usecols=range(15), dtype=object
    )
    frame.columns = [normalize_header(column) for column in frame.columns]
    normalized_columns = {
        normalize_header(chinese_name): field_name
        for chinese_name, field_name in COLUMNS.items()
    }
    missing = set(normalized_columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Sheet1缺少必要字段: {', '.join(sorted(missing))}")

    source_hash = hashlib.sha256(content).hexdigest()
    upload_batch_id = str(uuid4())
    records: list[dict[str, Any]] = []
    for frame_index, row in frame.iterrows():
        contract_no = text(row.get("合同编号"))
        declaration_no = text(row.get("报关单号"))
        if not contract_no or not declaration_no:
            raise ValueError(f"Sheet1第{int(frame_index) + 2}行缺少合同编号或报关单号")
        sequence = number(row.get("序号"))
        record: dict[str, Any] = {
            "record_sequence": int(sequence) if sequence is not None else int(frame_index) + 1,
        }
        for chinese_name, field_name in normalized_columns.items():
            value = row.get(chinese_name)
            if field_name in NUMERIC_FIELDS:
                record[field_name] = number(value)
            elif field_name in DATE_FIELDS:
                record[field_name] = date_value(value)
            else:
                record[field_name] = text(value)
        record.update(
            {
                "upload_batch_id": upload_batch_id,
                "uploaded_file_name": file_name,
                "source_hash": source_hash,
                "source_sheet": "Sheet1",
                "source_row": int(frame_index) + 2,
            }
        )
        records.append(record)

    if not records:
        raise ValueError("Sheet1未解析到有效数据")
    return records, {
        "kind": "receipt",
        "file_name": file_name,
        "source_hash": source_hash,
        "upload_batch_id": upload_batch_id,
        "rows": len(records),
        "ignored_column": "结汇时间",
    }
