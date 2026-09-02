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


# The performance importer consumes the six AMZ/eBay sheets from the shared
# company mapping workbook. The three women's-shoes sheets are intentionally
# allowed but ignored by this module.
UNIFIED_OWNER_SHEETS = {
    "EU组-sku品牌负责人": ("amazon", "EU", "BRAND", "品牌", True),
    "EU-OTH负责人": ("amazon", "EU", "OTH_CODE", "中间码-OTH", True),
    "US1组店铺负责人": ("amazon", "US1", "STORE", "店铺名", False),
    "US2组店铺负责人": ("amazon", "US2", "STORE", "店铺名", False),
    "US3组店铺负责人": ("amazon", "US3", "STORE", "店铺名", False),
    # A1 is intentionally blank in the supplied template. Pandas exposes it as
    # ``Unnamed: 0``; ``None`` means that the first column contains the brand.
    "EBAYsku负责人": ("ebay", "", "EBAY_BRAND", None, True),
}
UNIFIED_OWNER_IGNORED_SHEETS = {"女鞋一部", "女鞋二部", "女鞋三部"}


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


def parse_unified_owner_rule_excel(
    content: bytes,
    file_name: str,
    import_batch_id: str,
) -> dict[str, Any]:
    """Parse every YYYYMM负责人 column from the shared owner workbook."""
    workbook = pd.ExcelFile(BytesIO(content))
    expected = set(UNIFIED_OWNER_SHEETS)
    allowed = expected | UNIFIED_OWNER_IGNORED_SHEETS
    actual = set(workbook.sheet_names)
    missing = expected - actual
    unexpected = actual - allowed
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"缺少Sheet: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"存在非模板Sheet: {', '.join(sorted(unexpected))}")
        raise ValueError(
            "负责人映射表Sheet结构不正确；" + "；".join(details)
        )

    rules: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    sheet_stats: list[dict[str, Any]] = []
    duplicates: dict[tuple[str, str, str, str, str], tuple[str, int]] = {}
    store_owners: dict[tuple[str, str], tuple[str, str, int]] = {}
    months: set[str] = set()

    for sheet_name, (
        platform,
        group_code,
        rule_type,
        key_column,
        uppercase_key,
    ) in UNIFIED_OWNER_SHEETS.items():
        df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
        resolved_key_column = (
            df.columns[0]
            if key_column is None and len(df.columns) > 0
            else key_column
        )
        if resolved_key_column not in df.columns:
            raise ValueError(
                f"{sheet_name} 缺少列: {resolved_key_column}"
            )
        month_columns = [
            (column, month)
            for column in df.columns
            if (month := parse_month_header(column))
        ]
        if not month_columns:
            raise ValueError(f"{sheet_name} 未找到 YYYYMM负责人 月份列")
        sheet_months = {month for _, month in month_columns}
        months.update(sheet_months)

        stat = {
            "sheet_name": sheet_name,
            "platform": platform,
            "group_code": group_code,
            "rule_type": rule_type,
            "key_column": "第1列（品牌）" if key_column is None else key_column,
            "month_columns": [normalize_text(column) for column, _ in month_columns],
            "months": sorted(sheet_months),
            "month_count": len(sheet_months),
            "source_rows": int(len(df.index)),
            "imported_rows": 0,
            "unassigned_rows": 0,
            "skipped_blank_key_rows": 0,
            "skipped_blank_principal_rows": 0,
        }
        for index, record in df.iterrows():
            source_row = int(index) + 2
            match_key = normalize_text(record.get(resolved_key_column))
            if uppercase_key:
                match_key = match_key.upper()
            if not match_key:
                stat["skipped_blank_key_rows"] += 1
                continue

            for month_column, month in month_columns:
                principal_source = record.get(month_column)
                principal_text = normalize_text(principal_source)
                # Blank/pending cells explicitly clear an existing assignment.
                # Persist an empty string; downstream readers expose it as 未分配.
                principal_name = (
                    ""
                    if principal_text in {"", "待定", "待到"}
                    else normalize_principal(principal_source)
                )
                if not principal_name or principal_name == "未分配":
                    stat["unassigned_rows"] += 1

                key = (platform, month, group_code, rule_type, match_key)
                if key in duplicates:
                    duplicate_sheet, duplicate_row = duplicates[key]
                    raise ValueError(
                        "统一负责人配置重复: "
                        f"{duplicate_sheet} 第{duplicate_row}行和"
                        f"{sheet_name} 第{source_row}行 {key}"
                    )
                duplicates[key] = (sheet_name, source_row)

                # Store-name matching ignores the US group prefix. Conflicts
                # therefore need to be checked within the same month.
                if rule_type == "STORE" and principal_name:
                    store_owner_key = (month, match_key)
                    previous = store_owners.get(store_owner_key)
                    if previous and previous[0] != principal_name:
                        raise ValueError(
                            "Amazon店铺负责人配置冲突："
                            f"{month} 店铺“{match_key}”在"
                            f"{previous[1]}第{previous[2]}行配置给"
                            f"“{previous[0]}”，又在{sheet_name}第{source_row}行"
                            f"配置给“{principal_name}”"
                        )
                    store_owners[store_owner_key] = (
                        principal_name,
                        sheet_name,
                        source_row,
                    )

                rule = _rule(
                    platform,
                    month,
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
                stat["imported_rows"] += 1

        if stat["imported_rows"] == 0:
            raise ValueError(
                f"{sheet_name} 没有有效匹配键记录，拒绝覆盖"
            )
        sheet_stats.append(stat)

    platform_stats = {
        platform: sum(
            int(item["imported_rows"])
            for item in sheet_stats
            if item["platform"] == platform
        )
        for platform in ("amazon", "ebay")
    }

    result = _result(content, rules, raw_rows, months)
    result["month_count"] = len(months)
    result["sheet_stats"] = sheet_stats
    result["ignored_sheets"] = sorted(actual & UNIFIED_OWNER_IGNORED_SHEETS)
    result["platform_stats"] = platform_stats
    return result


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
