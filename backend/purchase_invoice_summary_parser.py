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
    "序号": "source_sequence",
    "发票代码": "invoice_code",
    "发票号码": "invoice_no",
    "数电发票号码": "digital_invoice_no",
    "销方识别号": "seller_tax_id",
    "销方名称": "seller_name",
    "购方识别号": "buyer_tax_id",
    "购买方名称": "buyer_name",
    "开票日期": "invoice_datetime",
    "税收分类编码": "tax_classification_code",
    "特定业务类型": "special_business_type",
    "货物或应税劳务名称": "goods_or_service_name",
    "规格型号": "specification",
    "单位": "unit",
    "数量": "quantity",
    "单价": "unit_price",
    "金额": "amount",
    "税率": "tax_rate",
    "税额": "tax_amount",
    "价税合计": "total_with_tax",
    "发票来源": "invoice_source",
    "发票票种": "invoice_type",
    "发票状态": "invoice_status",
    "是否正数发票": "is_positive_invoice",
    "发票风险等级": "invoice_risk_level",
    "开票人": "issuer",
    "备注": "remark",
}

TEXT_FIELDS = {
    "invoice_code",
    "invoice_no",
    "digital_invoice_no",
    "seller_tax_id",
    "seller_name",
    "buyer_tax_id",
    "buyer_name",
    "tax_classification_code",
    "special_business_type",
    "goods_or_service_name",
    "specification",
    "unit",
    "tax_rate",
    "invoice_source",
    "invoice_type",
    "invoice_status",
    "is_positive_invoice",
    "invoice_risk_level",
    "issuer",
    "remark",
}
DECIMAL_FIELDS = {"quantity", "unit_price", "amount", "tax_amount", "total_with_tax"}
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2}|\d{2})\s*年")
REMARK_SKU_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"(?:JMH[A-Z0-9]+-[A-Z0-9]+|[A-Z0-9]{5}-[A-Z0-9]{4})"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
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
        value = value.strip()
        return value or None
    return value


def text(value: Any) -> str | None:
    value = clean(value)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def product_name(value: Any) -> str | None:
    """去掉发票项目前置大类，例如“*发动机*涡轮增压器”只保留“涡轮增压器”."""
    value = text(value)
    if value is None:
        return None
    normalized = value.replace("＊", "*")
    if "*" in normalized:
        normalized = normalized.rsplit("*", 1)[-1]
    normalized = normalized.strip()
    return normalized or None


def integer(value: Any, sheet_name: str, row_number: int) -> int:
    value = clean(value)
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        raise ValueError(
            f"{sheet_name}第{row_number}行“序号”不是有效整数"
        ) from None
    if parsed != parsed.to_integral_value():
        raise ValueError(f"{sheet_name}第{row_number}行“序号”不是有效整数")
    return int(parsed)


def decimal_value(
    value: Any, field_name: str, sheet_name: str, row_number: int
) -> Decimal | None:
    value = clean(value)
    if value is None:
        return None
    normalized = str(value).replace(",", "").replace("￥", "").strip()
    if normalized in {"-", "--"}:
        return None
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        raise ValueError(
            f"{sheet_name}第{row_number}行“{field_name}”不是有效数字：{value}"
        ) from None


def datetime_value(
    value: Any, sheet_name: str, row_number: int
) -> datetime | None:
    value = clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(
            f"{sheet_name}第{row_number}行“开票日期”无法识别：{value}"
        )
    return parsed.to_pydatetime().replace(tzinfo=None)


def invoice_identity(
    record: dict[str, Any], sheet_name: str, row_number: int
) -> str:
    digital_invoice_no = record.get("digital_invoice_no")
    if digital_invoice_no:
        return str(digital_invoice_no)
    invoice_no = record.get("invoice_no")
    invoice_code = record.get("invoice_code")
    if invoice_no:
        return f"{invoice_code or ''}:{invoice_no}"
    raise ValueError(
        f"{sheet_name}第{row_number}行缺少“数电发票号码”和“发票号码”，无法确定发票"
    )


def sheet_year(sheet_name: str, frame: pd.DataFrame) -> int:
    match = YEAR_PATTERN.search(sheet_name)
    if match:
        raw_year = int(match.group(1))
        return raw_year if raw_year >= 2000 else 2000 + raw_year

    parsed_dates = pd.to_datetime(frame["开票日期"], errors="coerce").dropna()
    years = sorted({int(value.year) for value in parsed_dates})
    if len(years) == 1:
        return years[0]
    raise ValueError(
        f"工作表“{sheet_name}”名称中没有年份，且无法从开票日期确定唯一年份"
    )


def remark_skus(records: list[dict[str, Any]]) -> list[str]:
    """按备注首次出现顺序提取SKU，忽略同一发票各行重复的整段备注。"""
    unique_remarks: list[str] = []
    seen_remarks: set[str] = set()
    for record in records:
        remark = str(record.get("remark") or "").strip()
        if not remark or remark in seen_remarks:
            continue
        seen_remarks.add(remark)
        unique_remarks.append(remark)

    return [
        match.group(0).upper()
        for remark in unique_remarks
        for match in REMARK_SKU_PATTERN.finditer(remark)
    ]


def resolve_complete_skus(records: list[dict[str, Any]]) -> dict[str, int]:
    """
    生成完整SKU：
    1. 原规格型号非空时直接使用；
    2. 仅对原规格为空的行，从备注提取SKU候选；
    3. 同一发票内，空规格商品行与备注SKU分别按出现顺序逐条对应；
    4. 备注SKU不足时剩余商品行保持未识别，多余候选不写入。
    """
    records_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        records_by_invoice.setdefault(str(record["invoice_identity"]), []).append(record)

    totals = {
        "specification_sku_rows": 0,
        "remark_sku_rows": 0,
        "remark_ordered_sku_rows": 0,
        # 保留旧返回字段，避免既有ERP调用方解析失败；数值等同于顺序补全行数。
        "remark_validated_sku_rows": 0,
        "unresolved_sku_rows": 0,
        "remark_unused_sku_candidates": 0,
    }
    for invoice_records in records_by_invoice.values():
        invoice_records.sort(key=lambda row: int(row["invoice_line_no"]))
        blank_records = [
            record
            for record in invoice_records
            if not str(record.get("specification") or "").strip()
        ]
        for record in invoice_records:
            specification = str(record.get("specification") or "").strip()
            if specification:
                record["resolved_sku"] = specification
                record["resolved_sku_source"] = "SPECIFICATION"
                totals["specification_sku_rows"] += 1
            else:
                record["resolved_sku"] = None
                record["resolved_sku_source"] = "UNRESOLVED"

        if not blank_records:
            continue

        candidates = remark_skus(invoice_records)
        assigned_count = min(len(blank_records), len(candidates))
        for record, sku in zip(blank_records, candidates):
            record["resolved_sku"] = sku
            record["resolved_sku_source"] = "REMARK_ORDERED"
            totals["remark_sku_rows"] += 1
            totals["remark_ordered_sku_rows"] += 1
            totals["remark_validated_sku_rows"] += 1
        totals["unresolved_sku_rows"] += len(blank_records) - assigned_count
        totals["remark_unused_sku_candidates"] += max(
            0, len(candidates) - len(blank_records)
        )

    return totals


def parse_purchase_invoice_summary_workbook(
    content: bytes,
    file_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not file_name.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("采购发票汇总文件必须是 .xlsx 或 .xlsm")

    try:
        sheets = pd.read_excel(
            BytesIO(content),
            sheet_name=None,
            header=0,
            dtype=object,
            engine="openpyxl",
        )
    except Exception as exc:
        raise ValueError(f"采购发票汇总Excel读取失败：{exc}") from exc

    source_hash = hashlib.sha256(content).hexdigest()
    upload_batch_id = str(uuid4())
    invoice_line_counts: dict[str, int] = {}
    sheet_rows: dict[str, int] = {}
    years: set[int] = set()
    records: list[dict[str, Any]] = []

    for current_sheet_name, source_frame in sheets.items():
        source_frame.columns = [
            str(column).strip() for column in source_frame.columns
        ]
        frame = source_frame.dropna(how="all")
        if frame.empty:
            continue
        missing = set(COLUMNS) - set(frame.columns)
        if missing:
            raise ValueError(
                f"工作表“{current_sheet_name}”缺少必要字段："
                f"{', '.join(sorted(missing))}"
            )
        frame = frame[list(COLUMNS)]
        current_year = sheet_year(current_sheet_name, frame)
        years.add(current_year)
        sheet_rows[current_sheet_name] = len(frame)

        for frame_index, row in frame.iterrows():
            row_number = int(frame_index) + 2
            source_sequence = integer(
                row.get("序号"), current_sheet_name, row_number
            )
            record: dict[str, Any] = {
                "invoice_year": current_year,
                "source_sequence": source_sequence,
            }
            for chinese_name, field_name in COLUMNS.items():
                if field_name == "source_sequence":
                    continue
                value = row.get(chinese_name)
                if field_name in TEXT_FIELDS:
                    record[field_name] = text(value)
                elif field_name in DECIMAL_FIELDS:
                    record[field_name] = decimal_value(
                        value, chinese_name, current_sheet_name, row_number
                    )
                elif field_name == "invoice_datetime":
                    record[field_name] = datetime_value(
                        value, current_sheet_name, row_number
                    )

            identity = invoice_identity(
                record, current_sheet_name, row_number
            )
            record["goods_or_service_name"] = product_name(
                record.get("goods_or_service_name")
            )
            invoice_line_counts[identity] = invoice_line_counts.get(identity, 0) + 1
            record.update(
                {
                    "invoice_identity": identity,
                    "invoice_line_no": invoice_line_counts[identity],
                    "upload_batch_id": upload_batch_id,
                    "uploaded_file_name": file_name,
                    "source_hash": source_hash,
                    "source_sheet": current_sheet_name,
                    "source_row": row_number,
                }
            )
            records.append(record)

    if not records:
        raise ValueError("采购发票汇总工作簿未解析到有效数据")

    year_sequences = [
        (record["invoice_year"], record["source_sequence"]) for record in records
    ]
    if len(set(year_sequences)) != len(year_sequences):
        raise ValueError("同一年度内存在重复“序号”，请先修正源文件")

    sku_resolution = resolve_complete_skus(records)

    return records, {
        "kind": "purchase_invoice_summary",
        "file_name": file_name,
        "source_hash": source_hash,
        "upload_batch_id": upload_batch_id,
        "source_sheets": list(sheet_rows),
        "sheet_rows": sheet_rows,
        "sheet_count": len(sheet_rows),
        "years": sorted(years),
        "invoice_count": len(invoice_line_counts),
        "rows": len(records),
        **sku_resolution,
    }
