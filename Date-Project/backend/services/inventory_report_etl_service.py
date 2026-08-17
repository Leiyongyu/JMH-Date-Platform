from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.parsers.performance_common import (
    normalize_text,
    parse_brand_code_from_sku,
)
from backend.repositories import inventory_report_etl_repository as repo


UNASSIGNED = "未分配"
DEPARTMENTS = (
    ("EBAY-1", "EBAY-1", 1),
    ("AMZ-EU", "AMZ-EU", 2),
    ("AMZ-US1", "AMZ-US1", 3),
    ("AMZ-US2", "AMZ-US2", 4),
    ("AMZ-US2-MJ", "AMZ-US2-MJ", 5),
    ("AMZ-US1-ZXY", "AMZ-US1-ZXY", 6),
)
VALID_DEPARTMENTS = {code for code, _name, _order in DEPARTMENTS}

LOCAL_EXCLUDED_WIDS = {"19056", "1194"}
LOCAL_AMZ_WIDS = {
    "18677": "EU",
    "19561": "EU",
    "18678": "US1",
    "18679": "US2",
    "18680": "US3",
}
LOCAL_EBAY_WIDS = {"18676", "18675", "18674"}
SPECIAL_STORE_NAMES = ("智贸云", "优贝诺")
SPECIAL_MSKU_MARKERS = ("zmy", "dsq")

ZERO = Decimal("0")
METRIC_KEYS = (
    "end_in_transit_qty",
    "end_in_transit_total_cost",
    "end_inventory_qty",
    "end_inventory_total_cost",
)


def rebuild_monthly_inventory_report(stat_month: str | None = None) -> dict[str, Any]:
    month = _month(stat_month)
    sources = repo.source_rows(month)
    shops = repo.amazon_shop_map()
    amazon_rules = _amazon_rule_maps(repo.owner_rules(month, "amazon"))
    ebay_rules = _ebay_rule_map(repo.owner_rules(month, "ebay"))

    fba_rows, fba_stats = _clean_fba(
        month, sources["fba"], shops, amazon_rules
    )
    overseas_rows = _clean_overseas(
        month, sources["overseas"], amazon_rules, ebay_rules
    )
    local_rows, local_stats = _clean_local(
        month, sources["local"], amazon_rules, ebay_rules
    )
    dimension_rows = _dimension_summaries(
        month, fba_rows, overseas_rows, local_rows
    )
    department_rows = _department_summaries(
        month, fba_rows, overseas_rows, local_rows
    )
    persisted = repo.replace_clean_month(
        month,
        fba_rows,
        overseas_rows,
        local_rows,
        dimension_rows,
        department_rows,
    )
    return {
        "stat_month": month,
        "source_rows": sum(len(items) for items in sources.values()),
        "source_fba_rows": len(sources["fba"]),
        "source_overseas_rows": len(sources["overseas"]),
        "source_local_rows": len(sources["local"]),
        **fba_stats,
        **local_stats,
        **persisted,
        "status": "completed",
    }


def list_months(limit: int = 24) -> list[dict[str, Any]]:
    return [_json_ready(item) for item in repo.months(limit)]


def get_department_summary(stat_month: str | None = None) -> dict[str, Any]:
    data = repo.department_summary(stat_month)
    return {
        "stat_month": data["stat_month"],
        "items": [_json_ready(item) for item in data["items"]],
    }


def list_details(
    source_type: str,
    stat_month: str | None = None,
    department_code: str | None = None,
    principal_name: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    data = repo.detail_rows(
        source_type,
        stat_month,
        department_code,
        principal_name,
        keyword,
        page,
        page_size,
    )
    data["items"] = [_json_ready(item) for item in data["items"]]
    return data


def _clean_fba(month, source_rows, shops, rules):
    rows: list[dict[str, Any]] = []
    excluded_special_msku_rows = 0
    unmatched_department_rows = 0
    for source in source_rows:
        for child_index, item in _expanded_rows(source, "child_data"):
            sid = str(item.get("sid") or source.get("sid") or "").strip()
            store_name = shops.get(sid, "")
            msku = normalize_text(item.get("msku") or source.get("msku"))
            if _exclude_special_store_msku(store_name, msku):
                excluded_special_msku_rows += 1
                continue
            local_sku = normalize_text(
                item.get("local_sku") or source.get("local_sku")
            )
            group_code = _amazon_group(store_name)
            principal, match_source, matched_group = _amazon_assignment(
                store_name, local_sku or msku, rules
            )
            group_code = group_code or matched_group
            department_code = _department(group_code)
            if not department_code:
                unmatched_department_rows += 1
            rows.append(
                {
                    "stat_month": month,
                    "source_id": source["id"],
                    "source_child_index": child_index,
                    "sync_batch_id": source["sync_batch_id"],
                    "sid": sid or None,
                    "store_name": store_name or None,
                    "group_code": group_code,
                    "department_code": department_code,
                    "principal_name": principal,
                    "principal_match_source": match_source,
                    "ware_house_name": _text(item, source, "ware_house_name"),
                    "msku": msku or None,
                    "asin": _text(item, source, "asin"),
                    "fnsku": _text(item, source, "fnsku"),
                    "local_sku": local_sku or None,
                    "local_name": _text(item, source, "local_name"),
                    "country_code": _text(item, source, "country_code"),
                    "end_inventory_qty": _num(_value(item, source, "end_count"))
                    + _num(_value(item, source, "transferring_out_count")),
                    "end_inventory_total_cost": _num(
                        _value(item, source, "end_total_amount")
                    )
                    + _num(_value(item, source, "transferring_out_total_amount")),
                    "end_in_transit_qty": _num(
                        _value(item, source, "end_on_way_count")
                    ),
                    "end_in_transit_total_cost": _num(
                        _value(item, source, "end_on_way_total_amount")
                    ),
                }
            )
    return rows, {
        "fba_excluded_special_msku_rows": excluded_special_msku_rows,
        "fba_unmatched_department_rows": unmatched_department_rows,
    }


def _clean_overseas(month, source_rows, amazon_rules, ebay_rules):
    rows: list[dict[str, Any]] = []
    for source in source_rows:
        for child_index, item in _expanded_rows(source, "child_list"):
            seller_name = normalize_text(
                item.get("seller_name") or source.get("seller_name")
            )
            warehouse_name = normalize_text(
                item.get("ware_house_name") or source.get("ware_house_name")
            )
            sku = normalize_text(item.get("sku") or source.get("sku"))
            platform = _platform(seller_name, warehouse_name)
            if platform == "EBAY":
                principal, match_source = _ebay_assignment(sku, ebay_rules)
                group_code = "EBAY-1"
                department_code = "EBAY-1"
            else:
                principal, match_source, matched_group = _amazon_assignment(
                    seller_name, sku, amazon_rules
                )
                group_code = (
                    _amazon_group(seller_name)
                    or _amazon_group(warehouse_name)
                    or matched_group
                )
                department_code = _department(group_code)
            rows.append(
                _warehouse_detail(
                    month,
                    source,
                    child_index,
                    item,
                    platform,
                    group_code,
                    department_code,
                    principal,
                    match_source,
                    include_api_sku=True,
                )
            )
    return rows


def _clean_local(month, source_rows, amazon_rules, ebay_rules):
    rows: list[dict[str, Any]] = []
    excluded_wid_rows = 0
    unsupported_wid_rows = 0
    for source in source_rows:
        for child_index, item in _expanded_rows(source, "child_list"):
            sys_wid = str(item.get("sys_wid") or source.get("sys_wid") or "").strip()
            if sys_wid in LOCAL_EXCLUDED_WIDS:
                excluded_wid_rows += 1
                continue
            seller_name = normalize_text(
                item.get("seller_name") or source.get("seller_name")
            )
            warehouse_name = normalize_text(
                item.get("ware_house_name") or source.get("ware_house_name")
            )
            sku = normalize_text(item.get("sku") or source.get("sku"))
            if sys_wid in LOCAL_EBAY_WIDS:
                platform = "EBAY"
                group_code = "EBAY-1"
                department_code = "EBAY-1"
                principal, match_source = _ebay_assignment(sku, ebay_rules)
            elif sys_wid in LOCAL_AMZ_WIDS:
                platform = "AMZ"
                configured_group = LOCAL_AMZ_WIDS[sys_wid]
                principal, match_source, matched_group = _amazon_assignment(
                    seller_name, sku, amazon_rules
                )
                if configured_group == "US3":
                    group_code = (
                        _amazon_group(seller_name)
                        or (
                            "US2-MJ" if matched_group == "US2"
                            else "US1-ZXY" if matched_group == "US1"
                            else None
                        )
                        or "US1-ZXY"
                    )
                    if group_code not in {"US2-MJ", "US1-ZXY"}:
                        group_code = "US1-ZXY"
                else:
                    group_code = configured_group
                department_code = _department(group_code)
            else:
                unsupported_wid_rows += 1
                continue
            rows.append(
                _warehouse_detail(
                    month,
                    source,
                    child_index,
                    item,
                    platform,
                    group_code,
                    department_code,
                    principal,
                    match_source,
                    include_api_sku=False,
                )
            )
    return rows, {
        "local_excluded_wid_rows": excluded_wid_rows,
        "local_unsupported_wid_rows": unsupported_wid_rows,
    }


def _warehouse_detail(
    month,
    source,
    child_index,
    item,
    platform,
    group_code,
    department_code,
    principal,
    match_source,
    *,
    include_api_sku,
):
    row = {
        "stat_month": month,
        "source_id": source["id"],
        "source_child_index": child_index,
        "sync_batch_id": source["sync_batch_id"],
        "sys_wid": _text(item, source, "sys_wid"),
        "ware_house_name": _text(item, source, "ware_house_name"),
        "seller_name": _text(item, source, "seller_name"),
        "product_name": _text(item, source, "product_name"),
        "sku": _text(item, source, "sku"),
        "fnsku": _text(item, source, "fnsku"),
        "spu": _text(item, source, "spu"),
        "brand": _text(item, source, "brand"),
        "platform_code": platform,
        "group_code": group_code,
        "department_code": department_code,
        "principal_name": principal,
        "principal_match_source": match_source,
        "end_in_transit_qty": _num(
            _value(item, source, "allocation_in_transit_count")
        ),
        "end_in_transit_total_cost": _num(
            _value(item, source, "allocation_in_transit_cost")
        ),
        "end_inventory_qty": _num(_value(item, source, "day_end_count")),
        "end_inventory_total_cost": _num(
            _value(item, source, "day_end_cost")
        ),
    }
    if include_api_sku:
        row["api_sku"] = _text(item, source, "api_sku")
    return row


def _dimension_summaries(month, fba_rows, overseas_rows, local_rows):
    aggregates: dict[tuple[str, str, str, str, str | None], dict[str, Any]] = {}
    for source_type, rows in (
        ("FBA", fba_rows),
        ("OVERSEAS", overseas_rows),
        ("LOCAL", local_rows),
    ):
        for row in rows:
            if source_type == "FBA":
                platform, dimension_type = "AMZ", "GROUP"
                dimension_value = row.get("group_code") or "未分组"
            elif source_type == "OVERSEAS":
                platform, dimension_type = row["platform_code"], "OWNER"
                dimension_value = row.get("principal_name") or UNASSIGNED
            elif row["platform_code"] == "AMZ":
                platform, dimension_type = "AMZ", "WAREHOUSE"
                dimension_value = row.get("ware_house_name") or "未知仓库"
            else:
                platform, dimension_type = "EBAY", "OWNER"
                dimension_value = row.get("principal_name") or UNASSIGNED
            key = (
                source_type,
                platform,
                dimension_type,
                dimension_value,
                row.get("department_code"),
            )
            aggregate = aggregates.setdefault(
                key,
                {
                    "stat_month": month,
                    "source_type": source_type,
                    "platform_code": platform,
                    "dimension_type": dimension_type,
                    "dimension_value": dimension_value,
                    "department_code": row.get("department_code"),
                    "source_rows": 0,
                    **{metric: ZERO for metric in METRIC_KEYS},
                },
            )
            aggregate["source_rows"] += 1
            for metric in METRIC_KEYS:
                aggregate[metric] += row[metric]
    return list(aggregates.values())


def _department_summaries(month, fba_rows, overseas_rows, local_rows):
    fields = (
        "local_end_in_transit_qty",
        "local_end_in_transit_total_cost",
        "local_end_inventory_qty",
        "local_end_inventory_total_cost",
        "overseas_end_in_transit_qty",
        "overseas_end_in_transit_total_cost",
        "overseas_end_inventory_qty",
        "overseas_end_inventory_total_cost",
        "fba_end_inventory_qty",
        "fba_end_inventory_total_cost",
        "fba_end_in_transit_qty",
        "fba_end_in_transit_total_cost",
    )
    aggregates = {
        code: {
            "stat_month": month,
            "department_code": code,
            "department_name": name,
            "display_order": order,
            "is_total": 0,
            **{field: ZERO for field in fields},
        }
        for code, name, order in DEPARTMENTS
    }
    for source_type, rows in (
        ("local", local_rows),
        ("overseas", overseas_rows),
        ("fba", fba_rows),
    ):
        for row in rows:
            department = row.get("department_code")
            if department not in aggregates:
                continue
            target = aggregates[department]
            if source_type == "fba":
                target["fba_end_inventory_qty"] += row["end_inventory_qty"]
                target["fba_end_inventory_total_cost"] += row[
                    "end_inventory_total_cost"
                ]
                target["fba_end_in_transit_qty"] += row["end_in_transit_qty"]
                target["fba_end_in_transit_total_cost"] += row[
                    "end_in_transit_total_cost"
                ]
            else:
                for metric in METRIC_KEYS:
                    target[f"{source_type}_{metric}"] += row[metric]
    rows = list(aggregates.values())
    total = {
        "stat_month": month,
        "department_code": "AUTO-PARTS-TOTAL",
        "department_name": "汽配小计",
        "display_order": 99,
        "is_total": 1,
        **{
            field: sum((row[field] for row in rows), ZERO)
            for field in fields
        },
    }
    rows.append(total)
    return rows


def _amazon_rule_maps(rows):
    rules: dict[tuple[str, str, str], str] = {}
    store_rules: dict[str, tuple[str, str]] = {}
    for row in rows:
        group = normalize_text(row.get("group_code")).upper()
        rule_type = normalize_text(row.get("rule_type")).upper()
        key = normalize_text(row.get("match_key"))
        if rule_type in {"BRAND", "OTH_CODE"}:
            key = key.upper()
        principal = _principal(row.get("principal_name"))
        rules[(group, rule_type, key)] = principal
        if rule_type == "STORE" and key:
            store_rules[key] = (principal, group)
    return rules, store_rules


def _ebay_rule_map(rows):
    return {
        normalize_text(row.get("match_key")).upper(): _principal(
            row.get("principal_name")
        )
        for row in rows
        if normalize_text(row.get("rule_type")).upper() == "EBAY_BRAND"
    }


def _amazon_assignment(store_name, sku, rule_maps):
    rules, store_rules = rule_maps
    store = normalize_text(store_name)
    normalized_sku = normalize_text(sku).upper()
    group = _amazon_group(store)
    if not store:
        return UNASSIGNED, "MISSING_STORE", group
    if store.startswith("EU-") or group == "EU":
        if store.endswith("-UK"):
            return "吴清栩", "AMAZON_EU_UK_FIXED", "EU"
        if normalized_sku.startswith("OTH-"):
            key = _sku_segment(normalized_sku, 1)
            return (
                rules.get(("EU", "OTH_CODE", key), UNASSIGNED),
                "AMAZON_EU_OTH" if key else "UNMATCHED",
                "EU",
            )
        key = _sku_segment(normalized_sku, 0)
        return (
            rules.get(("EU", "BRAND", key), UNASSIGNED),
            "AMAZON_EU_BRAND" if key else "UNMATCHED",
            "EU",
        )
    store_key = _store_segment(store)
    if store_key == "重庆茁凯":
        store_key = "邱存帅"
    matched = store_rules.get(store_key)
    if matched:
        return matched[0], "AMAZON_STORE", group or matched[1]
    return UNASSIGNED, "UNMATCHED", group


def _ebay_assignment(sku, rules):
    brand_code = parse_brand_code_from_sku(normalize_text(sku))
    if brand_code in {"FLL", "LEJ"}:
        return "方黎力", "EBAY_FIXED_BRAND"
    if brand_code == "CL":
        return "陈丽", "EBAY_FIXED_BRAND"
    principal = rules.get(brand_code, UNASSIGNED)
    return principal, "EBAY_BRAND" if principal != UNASSIGNED else "UNMATCHED"


def _amazon_group(store_name: str) -> str | None:
    store = normalize_text(store_name)
    upper = store.upper()
    for code in ("EU", "US1", "US2"):
        if upper.startswith(code + "-") or f"AMZ-{code}" in upper:
            return code
    if upper.startswith("US3-") or "AMZ-US3" in upper:
        if any(name in store for name in ("新志楠", "富琳顿", "富林顿")):
            return "US2-MJ"
        return "US1-ZXY"
    return None


def _department(group_code: str | None) -> str | None:
    if not group_code:
        return None
    code = f"AMZ-{group_code}"
    return code if code in VALID_DEPARTMENTS else None


def _platform(seller_name: str, warehouse_name: str) -> str:
    text = f"{seller_name} {warehouse_name}".lower()
    return "EBAY" if "ebay" in text else "AMZ"


def _exclude_special_store_msku(store_name: str, msku: str) -> bool:
    if not any(name in normalize_text(store_name) for name in SPECIAL_STORE_NAMES):
        return False
    value = normalize_text(msku).lower()
    return not any(marker in value for marker in SPECIAL_MSKU_MARKERS)


def _expanded_rows(source: dict[str, Any], child_field: str):
    value = source.get(child_field)
    if isinstance(value, str) and value.strip():
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = None
    if isinstance(value, list):
        children = [item for item in value if isinstance(item, dict)]
        if children:
            for index, child in enumerate(children, start=1):
                yield index, child
            return
    yield 0, source


def _value(item, source, field):
    value = item.get(field)
    return source.get(field) if value is None else value


def _text(item, source, field):
    text = normalize_text(_value(item, source, field))
    return text or None


def _num(value) -> Decimal:
    text = (
        normalize_text(value)
        .replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("$", "")
    )
    if not text or text == "-":
        return ZERO
    try:
        return Decimal(text)
    except InvalidOperation:
        return ZERO


def _principal(value) -> str:
    text = normalize_text(value)
    return UNASSIGNED if text.lower() in {"", "nan", "none", "待定", "待到"} else text


def _sku_segment(sku: str, index: int) -> str:
    parts = [part for part in sku.split("-") if part]
    return parts[index].upper() if len(parts) > index else ""


def _store_segment(store_name: str) -> str:
    parts = [part for part in store_name.split("-") if part]
    return parts[1] if len(parts) > 1 else store_name


def _month(value: str | None) -> str:
    month = value or datetime.now().strftime("%Y-%m")
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month):
        raise ValueError("stat_month必须使用YYYY-MM格式")
    return month


def _json_ready(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in row.items()
    }
