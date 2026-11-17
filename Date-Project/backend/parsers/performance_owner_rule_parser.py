from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from backend.parsers.performance_common import (
    normalize_principal,
    normalize_text,
    parse_month_header,
)


# 负责人映射表的 6 张表（飞书多维表格的数据表，与原「负责人划分.xlsx」的 Sheet 同名同结构）。
# 只有第一列匹配键和 YYYYMM 月份列参与生成规则，``备注`` 列不参与。
UNIFIED_OWNER_SHEETS = {
    "EU-店铺": ("amazon", "EU", "STORE", "店铺", False),
    "EU-品牌": ("amazon", "EU", "BRAND", "品牌", True),
    "EU-OTH": ("amazon", "EU", "OTH_CODE", "中间码-OTH", True),
    "US1": ("amazon", "US1", "STORE", "店铺名", False),
    "US2": ("amazon", "US2", "STORE", "店铺名", False),
    # The EBAY sheet intentionally does not name its first column. ``None``
    # means that whatever the first header contains is the brand column.
    "EBAY": ("ebay", "", "EBAY_BRAND", None, True),
}


def parse_unified_owner_rule_frames(
    frames: dict[str, pd.DataFrame],
    file_name: str,
    content: bytes,
    import_batch_id: str,
) -> dict[str, Any]:
    """按负责人映射表模板解析 6 张表（飞书多维表格同步时还原成的二维表）。

    content 只用于计算来源指纹（规范化后的表内容），用于判断与上次同步是否相同。
    """
    missing = set(UNIFIED_OWNER_SHEETS) - set(frames)
    if missing:
        raise ValueError(f"负责人映射表缺少: {', '.join(sorted(missing))}")
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
        df = frames[sheet_name]
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

                # US store-name matching deliberately ignores the US1/US2
                # prefix (legacy US3 stores are now maintained in US2).
                # EU store rules are a separate dimension and must not collide
                # with US store rules that happen to share a display name.
                if (
                    rule_type == "STORE"
                    and group_code != "EU"
                    and principal_name
                ):
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
    result["platform_stats"] = platform_stats
    return result


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
