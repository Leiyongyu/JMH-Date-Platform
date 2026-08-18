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
from backend.parsers.inventory_report_ebay_sales_parser import (
    parse_inventory_report_ebay_sales_excel,
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
SALES_TARGET_FACTORS = {
    "EBAY-1": Decimal("0.45"),
    "AMZ-EU": Decimal("0.3"),
    "AMZ-US1": Decimal("0.4"),
    "AMZ-US2": Decimal("0.4"),
    "AMZ-US2-MJ": Decimal("0.4"),
    "AMZ-US1-ZXY": Decimal("0.4"),
}

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

SOURCE_NAMES = {
    "fba": "FBA仓",
    "overseas": "海外仓",
    "local": "本地仓",
    "order_profit": "Amazon订单利润",
}


def rebuild_monthly_inventory_report(stat_month: str | None = None) -> dict[str, Any]:
    month = _month(stat_month)
    sources = repo.source_rows(month)
    _require_complete_sources(month, sources)
    shops = repo.amazon_shop_map()
    amazon_rules = _amazon_rule_maps(repo.owner_rules(month, "amazon"))
    ebay_rules = _ebay_rule_map(repo.owner_rules(month, "ebay"))
    manual_inputs = {
        row["department_code"]: row
        for row in repo.manual_inputs(month)
    }

    fba_rows, fba_stats = _clean_fba(
        month, sources["fba"], shops, amazon_rules
    )
    overseas_rows = _clean_overseas(month, sources["overseas"], ebay_rules)
    local_rows, local_stats = _clean_local(
        month, sources["local"], amazon_rules, ebay_rules
    )
    amz_sales_rows, amz_sales_stats = _clean_amz_sales(
        month, sources["order_profit"], shops, amazon_rules
    )
    ebay_sales_rows, ebay_sales_stats = _clean_ebay_sales(
        month, sources.get("ebay_sales", []), ebay_rules
    )
    dimension_rows = _dimension_summaries(
        month, fba_rows, overseas_rows, local_rows
    )
    department_rows = _department_summaries(
        month,
        fba_rows,
        overseas_rows,
        local_rows,
        manual_inputs=manual_inputs,
        amz_sales_rows=amz_sales_rows,
        ebay_sales_rows=ebay_sales_rows,
    )
    persisted = repo.replace_clean_month(
        month,
        fba_rows,
        overseas_rows,
        local_rows,
        amz_sales_rows,
        ebay_sales_rows,
        dimension_rows,
        department_rows,
    )
    return {
        "stat_month": month,
        "source_rows": sum(len(items) for items in sources.values()),
        "source_fba_rows": len(sources["fba"]),
        "source_overseas_rows": len(sources["overseas"]),
        "source_local_rows": len(sources["local"]),
        "source_order_profit_rows": len(sources["order_profit"]),
        "source_ebay_sales_rows": len(sources.get("ebay_sales", [])),
        **fba_stats,
        **local_stats,
        **amz_sales_stats,
        **ebay_sales_stats,
        **persisted,
        "status": "completed",
    }


def rebuild_monthly_inventory_amz_sales(
    stat_month: str,
) -> dict[str, Any]:
    """Rebuild only one month's AMZ sales DWD, safe for the month-end job."""
    month = _month(stat_month)
    sources = repo.order_profit_rows(month)
    if not sources:
        raise ValueError(f"{month} 缺少Amazon订单利润源数据")
    shops = repo.amazon_shop_map()
    rules = _amazon_rule_maps(repo.owner_rules(month, "amazon"))
    rows, stats = _clean_amz_sales(month, sources, shops, rules)
    persisted = repo.replace_amz_sales_detail_month(month, rows)
    return {
        "stat_month": month,
        "source_rows": len(sources),
        "dwd_rows": persisted["inserted_rows"],
        "deleted_rows": persisted["deleted_rows"],
        **stats,
        "status": "completed",
    }


def _require_complete_sources(
    stat_month: str,
    sources: dict[str, list[dict[str, Any]]],
) -> None:
    missing = [
        SOURCE_NAMES[source]
        for source in SOURCE_NAMES
        if not sources.get(source)
    ]
    if missing:
        raise ValueError(
            f"{stat_month} 缺少{'、'.join(missing)}源数据，未执行计算，"
            "已有清洗明细和汇总数据保持不变；请先执行月度库存源数据拉取任务"
        )


def list_months(limit: int = 24) -> list[dict[str, Any]]:
    return [_json_ready(item) for item in repo.months(limit)]


def get_department_summary(stat_month: str | None = None) -> dict[str, Any]:
    data = repo.department_summary(stat_month)
    month = data["stat_month"]
    age_cost_month = _next_month(month) if month else None
    sales_volume_month = _next_month(month) if month else None
    age_costs = (
        repo.inventory_age_group_costs(age_cost_month)
        if age_cost_month
        else {}
    )
    expected_groups = {
        code.removeprefix("AMZ-")
        for code in VALID_DEPARTMENTS
        if code.startswith("AMZ-")
    }
    complete_age_costs = expected_groups.issubset(age_costs)
    amz_volume_by_department: dict[str, Decimal] | None = None
    ebay_volume: Decimal | None = None
    if sales_volume_month:
        stored_amz_volumes = repo.amz_sales_volume_by_department(
            sales_volume_month
        )
        if stored_amz_volumes is not None:
            amz_volume_by_department = {
                code: _num(stored_amz_volumes.get(code))
                for code in VALID_DEPARTMENTS
                if code.startswith("AMZ-")
            }
        ebay_volume = repo.ebay_sales_volume(sales_volume_month)
    items = []
    for source in data["items"]:
        item = dict(source)
        department = normalize_text(item.get("department_code")).upper()
        if int(item.get("is_total") or 0) == 1:
            item["inventory_age_90_180_cost"] = (
                sum(
                    (
                        _num(age_costs[group]["inventory_91_180_cost"])
                        for group in expected_groups
                    ),
                    ZERO,
                )
                if complete_age_costs
                else None
            )
            item["inventory_age_180_plus_cost"] = (
                sum(
                    (
                        _num(age_costs[group]["inventory_181_plus_cost"])
                        for group in expected_groups
                    ),
                    ZERO,
                )
                if complete_age_costs
                else None
            )
        elif department.startswith("AMZ-"):
            costs = age_costs.get(department.removeprefix("AMZ-"))
            item["inventory_age_90_180_cost"] = (
                costs.get("inventory_91_180_cost") if costs else None
            )
            item["inventory_age_180_plus_cost"] = (
                costs.get("inventory_181_plus_cost") if costs else None
            )
        else:
            item["inventory_age_90_180_cost"] = None
            item["inventory_age_180_plus_cost"] = None
        item["inventory_age_cost_month"] = age_cost_month
        if int(item.get("is_total") or 0) == 1:
            department_volumes = (
                [ebay_volume, *amz_volume_by_department.values()]
                if ebay_volume is not None
                and amz_volume_by_department is not None
                else []
            )
            item["monthly_sales_qty"] = (
                sum(department_volumes, ZERO)
                if len(department_volumes) == len(DEPARTMENTS)
                else None
            )
        elif department == "EBAY-1":
            item["monthly_sales_qty"] = ebay_volume
        elif department.startswith("AMZ-"):
            item["monthly_sales_qty"] = (
                amz_volume_by_department.get(department, ZERO)
                if amz_volume_by_department is not None
                else None
            )
        else:
            item["monthly_sales_qty"] = None
        item["sales_volume_month"] = sales_volume_month
        items.append(item)
    return {
        "stat_month": month,
        "items": [_json_ready(item) for item in items],
    }


def get_manual_inputs(stat_month: str) -> dict[str, Any]:
    month = _month(stat_month)
    saved = {
        row["department_code"]: row
        for row in repo.manual_inputs(month)
    }
    items = []
    for code, name, order in DEPARTMENTS:
        row = saved.get(code, {})
        items.append(
            _json_ready(
                {
                    "department_code": code,
                    "department_name": name,
                    "display_order": order,
                    "local_end_in_transit_qty": row.get(
                        "local_end_in_transit_qty", ZERO
                    ),
                    "local_end_in_transit_total_cost": row.get(
                        "local_end_in_transit_total_cost", ZERO
                    ),
                    "updated_by": row.get("updated_by", ""),
                    "updated_at": row.get("updated_at"),
                }
            )
        )
    return {"stat_month": month, "items": items}


def save_manual_inputs(
    stat_month: str,
    items: list[dict[str, Any]],
    operator: str | None = None,
) -> dict[str, Any]:
    month = _month(stat_month)
    if not items:
        raise ValueError("人工在途数据不能为空")
    seen: set[str] = set()
    rows = []
    for item in items:
        department = normalize_text(item.get("department_code")).upper()
        if department not in VALID_DEPARTMENTS:
            raise ValueError(f"不支持的部门编码: {department or '空值'}")
        if department in seen:
            raise ValueError(f"部门编码重复: {department}")
        seen.add(department)
        qty = _num(item.get("local_end_in_transit_qty"))
        cost = _num(item.get("local_end_in_transit_total_cost"))
        if qty < ZERO or cost < ZERO:
            raise ValueError("人工填写的在途数量和金额不能小于0")
        rows.append(
            {
                "department_code": department,
                "local_end_in_transit_qty": qty,
                "local_end_in_transit_total_cost": cost,
            }
        )
    repo.upsert_manual_inputs(month, rows, normalize_text(operator)[:64])
    return get_manual_inputs(month)


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


def import_inventory_report_ebay_sales(
    content: bytes,
    file_name: str,
    stat_month: str,
    operator: str | None = None,
) -> dict[str, Any]:
    parsed = parse_inventory_report_ebay_sales_excel(
        content,
        file_name,
        _month(stat_month),
        operator,
    )
    replace_stats = repo.replace_ebay_sales_source_month(
        parsed["stat_month"], parsed["rows"]
    )
    try:
        rebuild = rebuild_monthly_inventory_report(parsed["stat_month"])
    except Exception as exc:
        raise RuntimeError(
            "eBay实际达成源数据已更新，但月度库存报表重算失败: "
            f"{exc}"
        ) from exc
    return {
        "stat_month": parsed["stat_month"],
        "batch_id": parsed["batch_id"],
        "source_rows": parsed["source_rows"],
        "inserted_rows": replace_stats["inserted_rows"],
        "deleted_rows": replace_stats["deleted_rows"],
        "skipped_rows": parsed["skipped_rows"],
        "total_amount": parsed["total_amount"],
        "rebuild": rebuild,
    }


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


def _clean_overseas(month, source_rows, ebay_rules):
    rows: list[dict[str, Any]] = []
    for source in source_rows:
        for child_index, item in _expanded_rows(source, "child_list"):
            sku = normalize_text(item.get("sku") or source.get("sku"))
            principal, match_source = _ebay_assignment(sku, ebay_rules)
            rows.append(
                _warehouse_detail(
                    month,
                    source,
                    child_index,
                    item,
                    "EBAY",
                    "EBAY-1",
                    "EBAY-1",
                    principal,
                    match_source,
                    include_api_sku=True,
                )
            )
    return rows


def _clean_amz_sales(month, source_rows, shops, rules):
    rows: list[dict[str, Any]] = []
    excluded_special_msku_rows = 0
    unmatched_department_rows = 0
    for source in source_rows:
        sid = str(source.get("sid") or "").strip()
        store_name = shops.get(sid, "")
        msku = normalize_text(source.get("msku"))
        if _exclude_special_store_msku(store_name, msku):
            excluded_special_msku_rows += 1
            continue
        local_sku = normalize_text(source.get("local_sku"))
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
                "sid": sid or None,
                "store_name": store_name or None,
                "group_code": group_code,
                "department_code": department_code,
                "principal_name": principal,
                "principal_match_source": match_source,
                "msku": msku or None,
                "local_sku": local_sku or None,
                "asin": normalize_text(source.get("asin")) or None,
                "item_name": normalize_text(source.get("item_name")) or None,
                "currency_code": normalize_text(
                    source.get("currency_code")
                ) or "CNY",
                "amount": _num(source.get("amount")),
                "volume": _num(source.get("volume")),
            }
        )
    return rows, {
        "amz_sales_excluded_special_msku_rows": excluded_special_msku_rows,
        "amz_sales_unmatched_department_rows": unmatched_department_rows,
    }


def _clean_ebay_sales(month, source_rows, rules):
    rows: list[dict[str, Any]] = []
    matched_rows = 0
    unmatched_rows = 0
    for source in source_rows:
        sku = normalize_text(source.get("sku"))
        principal, match_source = _ebay_assignment(sku, rules)
        if principal == UNASSIGNED:
            unmatched_rows += 1
        else:
            matched_rows += 1
        rows.append(
            {
                "stat_month": month,
                "source_id": source["id"],
                "sku": sku,
                "brand_code": normalize_text(source.get("brand_code")).upper(),
                "image_url": normalize_text(source.get("image_url")) or None,
                "multi_variant": normalize_text(source.get("multi_variant")) or None,
                "department_code": "EBAY-1",
                "principal_name": principal,
                "principal_match_source": match_source,
                "product_sales_amount": _num(
                    source.get("product_sales_amount")
                ),
                "receivable_shipping_amount": _num(
                    source.get("receivable_shipping_amount")
                ),
                "amount": _num(source.get("amount")),
            }
        )
    return rows, {
        "ebay_sales_matched_rows": matched_rows,
        "ebay_sales_unmatched_rows": unmatched_rows,
    }


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


def _department_summaries(
    month,
    fba_rows,
    overseas_rows,
    local_rows,
    manual_inputs=None,
    amz_sales_rows=None,
    ebay_sales_rows=None,
):
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
        "actual_achievement_amount",
        "target_achievement_rate",
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
    for row in amz_sales_rows or []:
        department = row.get("department_code")
        if department in aggregates:
            aggregates[department]["actual_achievement_amount"] += row["amount"]
    for row in ebay_sales_rows or []:
        aggregates["EBAY-1"]["actual_achievement_amount"] += row["amount"]
    manual_inputs = manual_inputs or {}
    for department, target in aggregates.items():
        manual = manual_inputs.get(department, {})
        target["local_end_in_transit_qty"] = _num(
            manual.get("local_end_in_transit_qty")
        )
        target["local_end_in_transit_total_cost"] = _num(
            manual.get("local_end_in_transit_total_cost")
        )
        sales_target = _sales_target(target)
        target["target_achievement_rate"] = (
            target["actual_achievement_amount"] / sales_target
            if sales_target != ZERO
            else ZERO
        )
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
    # 汽配小计的销售目标是各组按各自系数计算后的目标之和。
    total_sales_target = sum((_sales_target(row) for row in rows), ZERO)
    total["target_achievement_rate"] = (
        total["actual_achievement_amount"] / total_sales_target
        if total_sales_target != ZERO
        else ZERO
    )
    rows.append(total)
    return rows


def _sales_target(row: dict[str, Any]) -> Decimal:
    inventory_amount = (
        _num(row.get("overseas_end_inventory_total_cost"))
        + _num(row.get("fba_end_inventory_total_cost"))
    )
    transit_amount = (
        _num(row.get("overseas_end_in_transit_total_cost"))
        + _num(row.get("fba_end_in_transit_total_cost"))
    )
    factor = SALES_TARGET_FACTORS.get(
        normalize_text(row.get("department_code")).upper(),
        Decimal("0.4"),
    )
    inventory_target = inventory_amount / Decimal("3") / factor / Decimal("6.6")
    total_target = (
        (inventory_amount + transit_amount)
        / Decimal("5")
        / factor
        / Decimal("6.6")
    )
    return (inventory_target + total_target) / Decimal("2")


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


def _next_month(stat_month: str) -> str:
    year, month = (int(part) for part in stat_month.split("-", 1))
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _json_ready(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in row.items()
    }
