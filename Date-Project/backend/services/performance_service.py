from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from backend.parsers.ebay_performance_profit_parser import parse_ebay_profit_excel
from backend.parsers.performance_common import (
    EU_UK_FIXED_OWNER,
    UNASSIGNED,
    normalize_text,
    owner_is_blank,
    owner_is_invisible_whitespace,
)
from backend.parsers.performance_owner_rule_parser import (
    parse_owner_rule_excel,
    parse_unified_owner_rule_excel,
)
from backend.repositories import performance_repository as repo
from backend.services.inventory_report_etl_service import (
    refresh_monthly_inventory_sales_snapshot_safely,
)


# Why a profit row never reached a real owner. Ordered most actionable first;
# the ERP ranking page renders them in this order.
UNMATCHED_REASONS = {
    "RULE_MISSING": "负责人划分表里没有这一行，需要新增后重新导入",
    "OWNER_BLANK": "规则行存在，但该月负责人列为空或填了待定/待到",
    "OWNER_WHITESPACE": (
        "该月负责人单元格只有不可见空白（全角空格/NBSP）；"
        "eBay 会把它当成真实负责人，必须在 Excel 里清掉"
    ),
    "KEY_EMPTY": "SKU 缺失或格式异常，取不出品牌码/中间码",
    "SHOP_UNKNOWN": "店铺主数据缺失：sid 在 shop_list 里查不到，金额未计入排名",
}

# Distinguishes "no rule row" from "rule row whose owner cell is empty",
# which None cannot do because an empty cell is stored as an empty string.
_MISSING = object()

UNMATCHED_DIMENSIONS = {
    "STORE": "Amazon 店铺名（去掉 US1/US2 前缀后的主体）",
    "BRAND": "Amazon EU SKU 品牌码（SKU 第 1 段）",
    "OTH_CODE": "Amazon EU 中间码（OTH- 后的第 2 段）",
    "EBAY_BRAND": "eBay 品牌码（SKU 品牌前缀）",
    "SHOP": "Amazon 店铺主数据",
}


def list_performance_rankings(
    platform: str = "combined",
    stat_month: str | None = None,
    principal_name: str | None = None,
    order_by: str = "gross_profit",
    order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    exclude_unassigned: bool = False,
) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 1000)
    data = repo.list_rankings(
        platform=platform,
        stat_month=stat_month,
        principal_name=principal_name,
        order_by=order_by,
        order=order,
        page=page,
        page_size=page_size,
        exclude_unassigned=exclude_unassigned,
    )
    items = [
        _ranking_item(row)
        for row in data["items"]
    ]
    return {
        "platform": platform,
        "stat_month": data["stat_month"],
        "currency": "CNY",
        "excludeUnassigned": exclude_unassigned,
        "partial": any(bool(row.get("partial")) for row in data["items"]),
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": data["total"],
        },
    }


def performance_months(limit: int = 12) -> list[dict]:
    return [_json_ready(row) for row in repo.months_status(limit=min(max(limit, 1), 60))]


def refresh_performance(
    stat_month: str,
    platform: str = "combined",
    require_all_platforms: bool = False,
    trigger_source: str = "api",
    request_id: str = "",
) -> dict:
    context = begin_performance_refresh(
        stat_month, platform, trigger_source, request_id
    )
    try:
        with repo.performance_connection() as connection:
            result = calculate_performance(
                connection, stat_month, platform, require_all_platforms
            )
            complete_performance_refresh(connection, context, result)
            connection.commit()
        result["status"] = "completed"
        return result
    except Exception as exc:
        fail_performance_refresh(context, exc)
        raise


def begin_performance_refresh(
    stat_month: str,
    platform: str,
    trigger_source: str,
    request_id: str,
) -> dict:
    context = {
        "refresh_id": str(uuid4()),
        "stat_month": stat_month,
        "platform": platform,
        "trigger_source": trigger_source,
        "request_id": request_id,
        "started_at": datetime.now(),
    }
    with repo.performance_connection() as connection:
        repo.upsert_refresh_run(
            connection,
            _refresh_payload(
                context["refresh_id"],
                stat_month,
                platform,
                "running",
                trigger_source,
                request_id,
                context["started_at"],
            ),
        )
        connection.commit()
    return context


def calculate_performance(
    connection,
    stat_month: str,
    platform: str = "combined",
    require_all_platforms: bool = False,
) -> dict:
    amz_profit_rows = repo.count_amz_profit_rows(connection, stat_month)
    ebay_profit_rows = repo.count_ebay_profit_rows(connection, stat_month)
    if require_all_platforms and (amz_profit_rows == 0 or ebay_profit_rows == 0):
        raise ValueError("指定月份 AMZ/eBay 数据未全部就绪")
    result = {
        "stat_month": stat_month,
        "platform": platform,
        "currency": "CNY",
        "partial": not (amz_profit_rows > 0 and ebay_profit_rows > 0),
        "amz_profit_rows": amz_profit_rows,
        "ebay_profit_rows": ebay_profit_rows,
        "source_rows": 0,
        "matched_rows": 0,
        "unmatched_rows": 0,
        "missing_shop_rows": 0,
        "amz_ranking_rows": 0,
        "ebay_ranking_rows": 0,
        "combined_ranking_rows": 0,
    }
    if platform in {"amazon", "combined"} and amz_profit_rows:
        amz = _refresh_amazon(connection, stat_month)
        result.update(
            {
                "source_rows": result["source_rows"] + amz["source_rows"],
                "matched_rows": result["matched_rows"] + amz["matched_rows"],
                "unmatched_rows": result["unmatched_rows"] + amz["unmatched_rows"],
                "missing_shop_rows": result["missing_shop_rows"]
                + amz["missing_shop_rows"],
                "amz_ranking_rows": amz["ranking_rows"],
            }
        )
    if platform in {"ebay", "combined"} and ebay_profit_rows:
        ebay = repo.refresh_ebay_ranking_sql(connection, stat_month)
        result.update(
            {
                "source_rows": result["source_rows"] + ebay["source_rows"],
                "matched_rows": result["matched_rows"] + ebay["matched_rows"],
                "unmatched_rows": result["unmatched_rows"] + ebay["unmatched_rows"],
                "ebay_ranking_rows": ebay["ranking_rows"],
            }
        )
    if platform in {"amazon", "ebay", "combined"}:
        result["combined_ranking_rows"] = repo.refresh_combined_ranking_sql(
            connection, stat_month, result["partial"]
        )
    return result


def complete_performance_refresh(
    connection, context: dict, result: dict
) -> None:
    repo.upsert_refresh_run(
        connection,
        {
            **_refresh_payload(
                context["refresh_id"],
                context["stat_month"],
                context["platform"],
                "completed",
                context["trigger_source"],
                context["request_id"],
                context["started_at"],
            ),
            **result,
            "completed_at": datetime.now(),
            "error_message": None,
            "partial": 1 if result["partial"] else 0,
        },
    )


def fail_performance_refresh(context: dict, exc: Exception) -> None:
    with repo.performance_connection() as connection:
        repo.upsert_refresh_run(
            connection,
            {
                **_refresh_payload(
                    context["refresh_id"],
                    context["stat_month"],
                    context["platform"],
                    "failed",
                    context["trigger_source"],
                    context["request_id"],
                    context["started_at"],
                ),
                "completed_at": datetime.now(),
                "error_message": str(exc),
            },
        )
        connection.commit()


def import_ebay_profit(
    content: bytes,
    file_name: str,
    rebuild: bool = True,
    stat_month: str | None = None,
    operator: str | None = None,
    request_id: str = "",
    idempotency_key: str | None = None,
) -> dict:
    batch_id = str(uuid4())
    parsed = parse_ebay_profit_excel(
        content, file_name, batch_id, stat_month=stat_month
    )
    started_at = datetime.now()
    with repo.performance_connection() as connection:
        repo.replace_ebay_profit_month(connection, parsed["stat_month"], parsed["rows"], parsed["raw_rows"])
        repo.insert_import_batch(
            connection,
            {
                "batch_id": batch_id,
                "import_type": "ebay_profit",
                "platform": "ebay",
                "stat_month": parsed["stat_month"],
                "source_file_name": file_name,
                "file_hash": parsed["file_hash"],
                "idempotency_key": idempotency_key,
                "status": "completed",
                "total_rows": len(parsed["rows"]),
                "inserted_rows": len(parsed["rows"]),
                "updated_rows": 0,
                "skipped_rows": 0,
                "operator": operator,
                "request_id": request_id,
                "error_message": None,
                "started_at": started_at,
                "completed_at": datetime.now(),
            },
        )
        connection.commit()
    refresh = refresh_performance(parsed["stat_month"], "ebay", trigger_source="ebay_profit_import", request_id=request_id) if rebuild else None
    # Monthly inventory OWNER rows read eBay sales from the refreshed ranking.
    # Without a rebuild the daily compensation picks the month up later.
    report_refresh = refresh_monthly_inventory_sales_snapshot_safely(
        parsed["stat_month"], trigger="ebay_profit_import",
    ) if rebuild else None
    return {
        "batch_id": batch_id,
        "stat_month": parsed["stat_month"],
        "inserted_rows": len(parsed["rows"]),
        "totals": parsed["totals"],
        "refresh": refresh,
        "report_refresh": report_refresh,
    }


def import_owner_rules(
    platform: str,
    content: bytes,
    file_name: str,
    rebuild: bool = True,
    stat_month: str | None = None,
    operator: str | None = None,
    request_id: str = "",
    idempotency_key: str | None = None,
) -> dict:
    batch_id = str(uuid4())
    parsed = parse_owner_rule_excel(content, file_name, platform, batch_id)
    months = [stat_month] if stat_month else parsed["months"]
    started_at = datetime.now()
    with repo.performance_connection() as connection:
        repo.upsert_owner_rules(connection, parsed["rules"], parsed["raw_rows"])
        repo.insert_import_batch(
            connection,
            {
                "batch_id": batch_id,
                "import_type": "owner_rule",
                "platform": platform,
                "stat_month": stat_month or (",".join(parsed["months"])[:7] if parsed["months"] else None),
                "source_file_name": file_name,
                "file_hash": parsed["file_hash"],
                "idempotency_key": idempotency_key,
                "status": "completed",
                "total_rows": len(parsed["rules"]),
                "inserted_rows": len(parsed["rules"]),
                "updated_rows": 0,
                "skipped_rows": 0,
                "operator": operator,
                "request_id": request_id,
                "error_message": None,
                "started_at": started_at,
                "completed_at": datetime.now(),
            },
        )
        connection.commit()
    refreshes = []
    if rebuild:
        for month in months:
            refreshes.append(
                refresh_performance(month, platform, trigger_source="owner_rule_import", request_id=request_id)
            )
    return {
        "batch_id": batch_id,
        "platform": platform,
        "imported_rows": len(parsed["rules"]),
        "months": parsed["months"],
        "month_count": len(parsed["months"]),
        "refreshes": refreshes,
    }


def import_unified_owner_rules(
    content: bytes,
    file_name: str,
    rebuild: bool = True,
    operator: str | None = None,
    request_id: str = "",
    idempotency_key: str | None = None,
) -> dict:
    """Incrementally upsert every monthly rule found in the unified workbook."""
    batch_id = str(uuid4())
    parsed = parse_unified_owner_rule_excel(
        content,
        file_name,
        batch_id,
    )
    return apply_unified_owner_rules(
        parsed, batch_id, file_name, import_type="owner_rule_unified", rebuild=rebuild,
        operator=operator, request_id=request_id, idempotency_key=idempotency_key,
    )


def apply_unified_owner_rules(
    parsed: dict,
    batch_id: str,
    file_name: str,
    *,
    import_type: str,
    rebuild: bool = True,
    operator: str | None = None,
    request_id: str = "",
    idempotency_key: str | None = None,
    only_months: set[str] | None = None,
) -> dict:
    """统一负责人规则入库（Excel 上传与飞书同步共用）：按月增量 upsert、记批次、重算有数据的月份。

    only_months 给出时只重算其中的月份（飞书同步只重算负责人真正有变化的月份）。
    """
    months = parsed["months"]
    started_at = datetime.now()
    with repo.performance_connection() as connection:
        # The current workbook merged the former US3 store rows into US2.
        # Remove only legacy US3 rules for months present in this import; all
        # other historical rules remain incremental and untouched.
        legacy_deleted = repo.delete_owner_rules_by_group(
            connection,
            platform="amazon",
            group_code="US3",
            stat_months=months,
        )
        repo.upsert_owner_rules(
            connection,
            parsed["rules"],
            parsed["raw_rows"],
        )
        repo.insert_import_batch(
            connection,
            {
                "batch_id": batch_id,
                "import_type": import_type,
                "platform": "combined",
                "stat_month": None,
                "source_file_name": file_name,
                "file_hash": parsed["file_hash"],
                "idempotency_key": idempotency_key,
                "status": "completed",
                "total_rows": len(parsed["rules"]),
                "inserted_rows": len(parsed["rules"]),
                "updated_rows": 0,
                "skipped_rows": sum(
                    int(item["skipped_blank_key_rows"])
                    + int(item["skipped_blank_principal_rows"])
                    for item in parsed["sheet_stats"]
                ),
                "operator": operator,
                "request_id": request_id,
                "error_message": None,
                "started_at": started_at,
                "completed_at": datetime.now(),
            },
        )
        connection.commit()

    available_months = (
        {
            str(item.get("stat_month") or "")
            for item in performance_months(60)
        }
        if rebuild
        else set()
    )
    refresh_months = [
        month for month in months
        if month in available_months and (only_months is None or month in only_months)
    ]
    refreshes = [
        refresh_performance(
            month,
            "combined",
            trigger_source="unified_owner_rule_import",
            request_id=request_id,
        )
        for month in refresh_months
    ]
    return {
        "batch_id": batch_id,
        "platform": "combined",
        "months": months,
        "month_count": len(months),
        "imported_rows": len(parsed["rules"]),
        "upserted_rows": len(parsed["rules"]),
        "platform_stats": parsed["platform_stats"],
        "sheet_stats": parsed["sheet_stats"],
        "ignored_sheets": parsed["ignored_sheets"],
        "deleted_ods_rows": legacy_deleted["ods_rows"],
        "deleted_dwd_rows": legacy_deleted["dwd_rows"],
        "refreshed_months": refresh_months if rebuild else [],
        "skipped_refresh_months": [
            month for month in months if month not in refresh_months
        ],
        "refresh": refreshes[-1] if refreshes else None,
        "refreshes": refreshes,
    }


def performance_unmatched(platform: str, stat_month: str | None) -> dict:
    """Explain, per matching key, why profit rows fell through to 未分配.

    Computed live from the current rule table rather than stored, so the answer
    always reflects the workbook as it stands now and no extra table has to be
    kept in step with the ranking refresh.
    """
    month = stat_month or repo.latest_ranking_month(platform)
    if not month:
        return {
            "platform": platform,
            "stat_month": None,
            "items": [],
            "totals": _empty_unmatched_totals(),
        }

    items: list[dict] = []
    with repo.performance_connection() as connection:
        if platform in {"amazon", "combined"}:
            items.extend(_amazon_unmatched(connection, month))
        if platform in {"ebay", "combined"}:
            items.extend(_ebay_unmatched(connection, month))

    reason_order = list(UNMATCHED_REASONS)
    items.sort(
        key=lambda item: (
            reason_order.index(item["reason"])
            if item["reason"] in reason_order
            else len(reason_order),
            -item["grossProfit"],
        )
    )
    return {
        "platform": platform,
        "stat_month": month,
        "items": [_json_ready(item) for item in items],
        "totals": _unmatched_totals(items),
    }


def _empty_unmatched_totals() -> dict:
    return {
        "keys": 0,
        "sourceRows": 0,
        "grossProfit": "0",
        "netSalesAmount": "0",
        "byReason": [],
    }


def _unmatched_totals(items: list[dict]) -> dict:
    by_reason: dict[str, dict] = {}
    for item in items:
        bucket = by_reason.setdefault(
            item["reason"],
            {
                "reason": item["reason"],
                "reasonText": item["reasonText"],
                "keys": 0,
                "sourceRows": 0,
                "grossProfit": Decimal("0"),
            },
        )
        bucket["keys"] += 1
        bucket["sourceRows"] += item["sourceRows"]
        bucket["grossProfit"] += item["grossProfit"]
    return {
        "keys": len(items),
        "sourceRows": sum(item["sourceRows"] for item in items),
        "grossProfit": str(sum((item["grossProfit"] for item in items), Decimal("0"))),
        "netSalesAmount": str(
            sum((item["netSalesAmount"] for item in items), Decimal("0"))
        ),
        "byReason": [
            {**bucket, "grossProfit": str(bucket["grossProfit"])}
            for bucket in by_reason.values()
        ],
    }


def _unmatched_item(
    platform: str,
    dimension: str,
    match_key: str,
    reason: str,
) -> dict:
    return {
        "platform": platform,
        "dimension": dimension,
        "dimensionText": UNMATCHED_DIMENSIONS.get(dimension, dimension),
        "matchKey": match_key,
        "reason": reason,
        "reasonText": UNMATCHED_REASONS.get(reason, reason),
        "sourceRows": 0,
        "grossProfit": Decimal("0"),
        "netSalesAmount": Decimal("0"),
        "sampleStore": None,
        "sampleSku": None,
        "countsInRanking": reason != "SHOP_UNKNOWN",
    }


def _amazon_unmatched(connection, stat_month: str) -> list[dict]:
    profit_rows = repo.get_amz_profit_rows(connection, stat_month)
    rules = repo.get_owner_rules(connection, "amazon", stat_month)
    raw_rules = repo.get_owner_rules_raw(connection, "amazon", stat_month)
    store_rules = _amazon_store_rules(rules)
    # Store rules are keyed by name only, so look the raw cell up the same way.
    raw_store_rules = {
        key[2]: value
        for key, value in raw_rules.items()
        if key[1] == "STORE" and key[0] != "EU"
    }

    buckets: dict[tuple[str, str, str], dict] = {}
    for row in profit_rows:
        target = _amazon_match_target(row)
        if target is None:
            dimension, match_key, reason = "SHOP", "", "SHOP_UNKNOWN"
        else:
            dimension, match_key = target
            if dimension == "EU_UK":
                continue
            if dimension == "STORE":
                if _amazon_store_owner(match_key, store_rules):
                    continue
                raw = raw_store_rules.get(match_key, _MISSING)
            else:
                if rules.get(("EU", dimension, match_key), UNASSIGNED) != UNASSIGNED:
                    continue
                raw = raw_rules.get(("EU", dimension, match_key), _MISSING)
            reason = _unmatched_reason(match_key, raw)

        bucket = buckets.setdefault(
            (dimension, match_key, reason),
            _unmatched_item("amazon", dimension, match_key, reason),
        )
        bucket["sourceRows"] += 1
        bucket["grossProfit"] += _decimal(row.get("gross_profit"))
        bucket["netSalesAmount"] += _decimal(row.get("net_sales_amount"))
        if bucket["sampleStore"] is None:
            bucket["sampleStore"] = normalize_text(row.get("store_name")) or None
        if bucket["sampleSku"] is None:
            bucket["sampleSku"] = normalize_text(row.get("local_sku")) or None
    return list(buckets.values())


def _unmatched_reason(match_key: str, raw_owner) -> str:
    if not match_key:
        return "KEY_EMPTY"
    if raw_owner is _MISSING:
        return "RULE_MISSING"
    if owner_is_invisible_whitespace(raw_owner):
        return "OWNER_WHITESPACE"
    if owner_is_blank(raw_owner):
        return "OWNER_BLANK"
    # The rule names a real person yet the row still missed it: the only way
    # left is a key that differs from the configured one after normalisation.
    return "RULE_MISSING"


def _ebay_unmatched(connection, stat_month: str) -> list[dict]:
    items = []
    for row in repo.ebay_unmatched_breakdown(connection, stat_month):
        item = _unmatched_item(
            "ebay",
            "EBAY_BRAND",
            str(row.get("match_key") or ""),
            str(row.get("reason") or "RULE_MISSING"),
        )
        item["sourceRows"] = int(row.get("source_rows") or 0)
        item["grossProfit"] = _decimal(row.get("gross_profit"))
        item["netSalesAmount"] = _decimal(row.get("net_sales_amount"))
        item["sampleSku"] = row.get("sample_sku") or None
        # The whitespace case is the one reason eBay still counts the row
        # under a blank-looking owner instead of 未分配.
        item["countsInRanking"] = item["reason"] != "OWNER_WHITESPACE"
        items.append(item)
    return items


def owner_rule_summary(platform: str, stat_month: str) -> dict:
    rows = repo.owner_rule_summary(platform, stat_month)
    return {"platform": platform, "stat_month": stat_month, "items": [_json_ready(row) for row in rows]}


def _refresh_amazon(connection, stat_month: str) -> dict:
    profit_rows = repo.get_amz_profit_rows(connection, stat_month)
    rules = repo.get_owner_rules(connection, "amazon", stat_month)
    store_rules = _amazon_store_rules(rules)
    aggregates = defaultdict(_empty_amz_aggregate)
    source_rows = matched_rows = unmatched_rows = missing_shop_rows = 0
    for row in profit_rows:
        principal, scoped, missing_shop = _amazon_principal(
            row, rules, store_rules
        )
        if missing_shop:
            missing_shop_rows += 1
            continue
        if not scoped:
            continue
        source_rows += 1
        if principal == UNASSIGNED:
            unmatched_rows += 1
        else:
            matched_rows += 1
        aggregate = aggregates[principal]
        aggregate["gross_profit"] += _decimal(row.get("gross_profit"))
        aggregate["amount"] += _decimal(row.get("amount"))
        aggregate["refund_amount"] += _decimal(row.get("refund_amount"))
        aggregate["promotion_discount"] += _decimal(
            row.get("promotion_discount")
        )
        aggregate["net_sales_amount"] += _decimal(
            row.get("net_sales_amount")
        )
        aggregate["source_rows"] += 1
    rows = []
    for principal_name, aggregate in aggregates.items():
        rows.append(
            {
                "stat_month": stat_month,
                "principal_name": principal_name,
                "gross_profit": aggregate["gross_profit"],
                "amount": aggregate["amount"],
                "refund_amount": aggregate["refund_amount"],
                "promotion_discount": aggregate["promotion_discount"],
                "net_sales_amount": aggregate["net_sales_amount"],
                "source_rows": aggregate["source_rows"],
                # Each DWS row describes its own owner aggregate. Persisting the
                # global matched count on every owner makes row-level audits
                # misleading and multiplies totals when the column is summed.
                "matched_rows": aggregate["source_rows"] if principal_name != UNASSIGNED else 0,
                "unmatched_rows": aggregate["source_rows"] if principal_name == UNASSIGNED else 0,
                "missing_shop_rows": missing_shop_rows if principal_name == UNASSIGNED else 0,
            }
        )
    repo.replace_amz_ranking(connection, stat_month, rows)
    return {
        "source_rows": source_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "missing_shop_rows": missing_shop_rows,
        "ranking_rows": len(rows),
    }


def _amazon_store_rules(
    rules: dict[tuple[str, str, str], str]
) -> dict[str, str]:
    """Build one Amazon store-owner map without US1/US2/US3 grouping."""
    result: dict[str, str] = {}
    for (group_code, rule_type, match_key), principal in rules.items():
        if rule_type != "STORE":
            continue
        # EU owner assignment is SKU-brand/OTH based (with UK fixed owner).
        # EU-店铺 is retained as an auditable store dimension but must not leak
        # into the group-agnostic US store map.
        if group_code == "EU":
            continue
        store_key = normalize_text(match_key)
        if not store_key:
            continue
        current = result.get(store_key)
        if current and current != principal:
            raise ValueError(
                f"Amazon店铺负责人配置冲突：店铺“{store_key}”同时配置给"
                f"“{current}”和“{principal}”"
            )
        result[store_key] = principal
    return result


def _amazon_match_target(row: dict) -> tuple[str, str] | None:
    """Resolve which rule dimension and key one Amazon profit row matches on.

    ``None`` means the row carries no store name at all, so it is out of
    scope for owner matching. Dimension ``EU_UK`` needs no key: those stores
    have a fixed owner. Keeping this in one place means the ranking ETL and
    the unmatched diagnostics can never compute the key differently.
    """
    store_name = normalize_text(row.get("store_name"))
    if not store_name:
        return None
    local_sku = normalize_text(row.get("local_sku")).upper()

    if store_name.startswith("EU-"):
        if store_name.upper().endswith("-UK"):
            return "EU_UK", ""
        if local_sku.startswith("OTH-"):
            return "OTH_CODE", _sku_segment(local_sku, 1)
        return "BRAND", _sku_segment(local_sku, 0)

    return "STORE", _store_segment(store_name)


def _amazon_store_owner(
    store_key: str, store_rules: dict[str, str]
) -> str | None:
    # Prefer the exact store configured for the selected month. "重庆茁凯"
    # historically shared the "邱存帅" rule, but newer owner files can
    # configure both rows independently. Keep that alias only as a fallback.
    principal = store_rules.get(store_key)
    if principal is None and store_key == "重庆茁凯":
        principal = store_rules.get("邱存帅")
    return principal or None


def _amazon_principal(
    row: dict,
    rules: dict[tuple[str, str, str], str],
    store_rules: dict[str, str] | None = None,
) -> tuple[str, bool, bool]:
    target = _amazon_match_target(row)
    if target is None:
        return UNASSIGNED, False, True
    dimension, match_key = target

    if dimension == "EU_UK":
        return EU_UK_FIXED_OWNER, True, False
    if dimension == "OTH_CODE":
        return rules.get(("EU", "OTH_CODE", match_key), UNASSIGNED), True, False
    if dimension == "BRAND":
        return rules.get(("EU", "BRAND", match_key), UNASSIGNED), True, False

    if store_rules is None:
        store_rules = _amazon_store_rules(rules)
    principal = _amazon_store_owner(match_key, store_rules)
    if principal:
        return principal, True, False

    # Amazon店铺负责人只按店铺名匹配；未配置的店铺计入“未分配”，
    # 不再因US1/US2/US3等店铺前缀而静默排除。
    return UNASSIGNED, True, False


def _sku_segment(sku: str, index: int) -> str:
    parts = [part for part in sku.split("-") if part]
    return parts[index].upper() if len(parts) > index else ""


def _store_segment(store_name: str) -> str:
    parts = [part for part in store_name.split("-") if part]
    return parts[1] if len(parts) > 1 else store_name


def _empty_amz_aggregate() -> dict:
    return {
        "gross_profit": Decimal("0"),
        "amount": Decimal("0"),
        "refund_amount": Decimal("0"),
        "promotion_discount": Decimal("0"),
        "net_sales_amount": Decimal("0"),
        "source_rows": 0,
    }


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or "0"))


def _ranking_item(row: dict) -> dict:
    """Return the minimal row contract consumed by the ERP ranking page."""
    return {
        "principalNames": row.get("principal_name"),
        # Amounts stay as decimal strings to avoid JSON floating-point loss.
        "grossProfit": str(row.get("gross_profit", "0")),
        "netSalesAmount": str(row.get("net_sales_amount", "0")),
    }


def _refresh_payload(refresh_id, stat_month, platform, status, trigger_source, request_id, started_at):
    return {
        "refresh_id": refresh_id,
        "stat_month": stat_month,
        "platform": platform,
        "status": status,
        "partial": 0,
        "source_rows": 0,
        "matched_rows": 0,
        "unmatched_rows": 0,
        "missing_shop_rows": 0,
        "amz_profit_rows": 0,
        "ebay_profit_rows": 0,
        "amz_ranking_rows": 0,
        "ebay_ranking_rows": 0,
        "combined_ranking_rows": 0,
        "trigger_source": trigger_source,
        "request_id": request_id,
        "error_message": None,
        "started_at": started_at,
        "completed_at": None,
    }


def _json_ready(value):
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value
