from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

import pandas as pd

from backend.parsers.performance_common import (
    normalize_principal,
    normalize_text,
    parse_month_header,
)


AMAZON_SHEETS = {
    "EU-品牌": ("EU", "BRAND", "品牌", True),
    "EU-OTH": ("EU", "OTH_CODE", "中间码-OTH", True),
    "US1": ("US1", "STORE", "店铺名", False),
    "US2": ("US2", "STORE", "店铺名", False),
}


def parse_owner_rule_excel(
    content: bytes,
    file_name: str,
    platform: str,
    import_batch_id: str,
) -> dict[str, Any]:
    platform = platform.lower()
    workbook = pd.ExcelFile(BytesIO(content))
    if platform == "amazon":
        return _parse_amazon_rules(workbook, file_name, content, import_batch_id)
    if platform == "ebay":
        return _parse_ebay_rules(workbook, file_name, content, import_batch_id)
    raise ValueError("platform 只能是 amazon 或 ebay")


def _parse_amazon_rules(workbook, file_name: str, content: bytes, import_batch_id: str) -> dict[str, Any]:
    missing_sheets = set(AMAZON_SHEETS) - set(workbook.sheet_names)
    if missing_sheets:
        raise ValueError(f"Amazon负责人配置缺少Sheet: {', '.join(sorted(missing_sheets))}")
    rules = []
    raw_rows = []
    duplicates: dict[tuple, int] = {}
    months: set[str] = set()
    for sheet_name, (group_code, rule_type, key_column, uppercase_key) in AMAZON_SHEETS.items():
        df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
        if key_column not in df.columns:
            raise ValueError(f"{sheet_name} 缺少列: {key_column}")
        month_columns = [(column, parse_month_header(column)) for column in df.columns]
        month_columns = [(column, month) for column, month in month_columns if month]
        if not month_columns:
            raise ValueError(f"{sheet_name} 未找到 YYYYMM负责人 月份列")
        for index, record in df.iterrows():
            source_row = int(index) + 2
            match_key = normalize_text(record.get(key_column))
            if uppercase_key:
                match_key = match_key.upper()
            if not match_key:
                continue
            for column, stat_month in month_columns:
                principal_name = normalize_principal(record.get(column))
                if principal_name == "未分配" and not normalize_text(record.get(column)):
                    continue
                key = ("amazon", stat_month, group_code, rule_type, match_key)
                if key in duplicates:
                    raise ValueError(
                        f"Amazon负责人配置重复: {sheet_name} 第{duplicates[key]}行和第{source_row}行 {key}"
                    )
                duplicates[key] = source_row
                months.add(stat_month)
                rule = _rule(
                    "amazon",
                    stat_month,
                    group_code,
                    rule_type,
                    match_key,
                    principal_name,
                    file_name,
                    sheet_name,
                    source_row,
                    import_batch_id,
                )
                rules.append(rule)
                raw_rows.append(_raw(rule))
    return _result(content, rules, raw_rows, months)


def _parse_ebay_rules(workbook, file_name: str, content: bytes, import_batch_id: str) -> dict[str, Any]:
    sheet_name = next((name for name in workbook.sheet_names if name.lower() == "sheet1"), None)
    if not sheet_name:
        raise ValueError("eBay负责人配置必须包含 Sheet1")
    df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    if "品牌" not in df.columns:
        raise ValueError("eBay负责人配置缺少列: 品牌")
    month_columns = [(column, parse_month_header(column)) for column in df.columns]
    month_columns = [(column, month) for column, month in month_columns if month]
    if not month_columns:
        raise ValueError("eBay负责人配置未找到 YYYYMM负责人 月份列")
    rules = []
    raw_rows = []
    duplicates: dict[tuple, int] = {}
    months: set[str] = set()
    for index, record in df.iterrows():
        source_row = int(index) + 2
        brand_code = normalize_text(record.get("品牌")).upper()
        if not brand_code:
            continue
        for column, stat_month in month_columns:
            principal_name = normalize_principal(record.get(column))
            if principal_name == "未分配" and not normalize_text(record.get(column)):
                continue
            key = ("ebay", stat_month, "", "EBAY_BRAND", brand_code)
            if key in duplicates:
                raise ValueError(
                    f"eBay负责人配置重复: {sheet_name} 第{duplicates[key]}行和第{source_row}行 {brand_code}"
                )
            duplicates[key] = source_row
            months.add(stat_month)
            rule = _rule(
                "ebay",
                stat_month,
                "",
                "EBAY_BRAND",
                brand_code,
                principal_name,
                file_name,
                sheet_name,
                source_row,
                import_batch_id,
            )
            rules.append(rule)
            raw_rows.append(_raw(rule))
    return _result(content, rules, raw_rows, months)


def _rule(platform, stat_month, group_code, rule_type, match_key, principal_name, file_name, sheet_name, source_row, import_batch_id):
    return {
        "platform": platform,
        "stat_month": stat_month,
        "group_code": group_code,
        "rule_type": rule_type,
        "match_key": match_key,
        "principal_name": principal_name,
        "source_file_name": file_name,
        "source_sheet": sheet_name,
        "source_row": source_row,
        "import_batch_id": import_batch_id,
    }


def _raw(rule: dict[str, Any]) -> dict[str, Any]:
    return dict(rule)


def _result(content: bytes, rules: list[dict], raw_rows: list[dict], months: set[str]) -> dict[str, Any]:
    return {
        "file_hash": hashlib.sha256(content).hexdigest(),
        "rules": rules,
        "raw_rows": raw_rows,
        "months": sorted(months),
    }
