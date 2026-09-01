from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from backend.parsers.ebay_performance_profit_parser import parse_ebay_profit_excel
from backend.parsers.performance_common import normalize_text
from backend.parsers.performance_owner_rule_parser import (
    parse_owner_rule_excel,
    parse_unified_owner_rule_excel,
)
from backend.repositories import performance_repository as repo


UNASSIGNED = "未分配"


def list_performance_rankings(
    platform: str = "combined",
    stat_month: str | None = None,
    principal_name: str | None = None,
    order_by: str = "gross_profit",
    order: str = "desc",
    page: int = 1,
    page_size: int = 100,
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
    )
    items = [
        _ranking_item(row)
        for row in data["items"]
    ]
    return {
        "platform": platform,
        "stat_month": data["stat_month"],
        "currency": "CNY",
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
    return {
        "batch_id": batch_id,
        "stat_month": parsed["stat_month"],
        "inserted_rows": len(parsed["rows"]),
        "totals": parsed["totals"],
        "refresh": refresh,
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
    stat_month: str,
    rebuild: bool = True,
    operator: str | None = None,
    request_id: str = "",
    idempotency_key: str | None = None,
) -> dict:
    """Replace one month's AMZ/eBay owner rules from the unified workbook."""
    batch_id = str(uuid4())
    parsed = parse_unified_owner_rule_excel(
        content,
        file_name,
        stat_month,
        batch_id,
    )
    month = parsed["stat_month"]
    started_at = datetime.now()
    with repo.performance_connection() as connection:
        replace_stats = repo.replace_unified_owner_rule_month(
            connection,
            month,
            parsed["rules"],
            parsed["raw_rows"],
        )
        repo.insert_import_batch(
            connection,
            {
                "batch_id": batch_id,
                "import_type": "owner_rule_unified",
                "platform": "combined",
                "stat_month": month,
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

    refresh = (
        refresh_performance(
            month,
            "combined",
            trigger_source="unified_owner_rule_import",
            request_id=request_id,
        )
        if rebuild
        else None
    )
    return {
        "batch_id": batch_id,
        "platform": "combined",
        "stat_month": month,
        "months": [month],
        "month_count": 1,
        "imported_rows": len(parsed["rules"]),
        "platform_stats": parsed["platform_stats"],
        "sheet_stats": parsed["sheet_stats"],
        **replace_stats,
        "refresh": refresh,
        "refreshes": [refresh] if refresh else [],
    }


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
        aggregate["net_sales_amount"] += _decimal(row.get("amount")) - _decimal(row.get("refund_amount"))
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
    for (_, rule_type, match_key), principal in rules.items():
        if rule_type != "STORE":
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


def _amazon_principal(
    row: dict,
    rules: dict[tuple[str, str, str], str],
    store_rules: dict[str, str] | None = None,
) -> tuple[str, bool, bool]:
    store_name = normalize_text(row.get("store_name"))
    local_sku = normalize_text(row.get("local_sku")).upper()
    if not store_name:
        return UNASSIGNED, False, True

    if store_name.startswith("EU-"):
        if store_name.endswith("-UK"):
            return "吴清栩", True, False
        if local_sku.startswith("OTH-"):
            key = _sku_segment(local_sku, 1)
            return rules.get(("EU", "OTH_CODE", key), UNASSIGNED), True, False
        return rules.get(("EU", "BRAND", _sku_segment(local_sku, 0)), UNASSIGNED), True, False

    if store_rules is None:
        store_rules = _amazon_store_rules(rules)
    store_key = _store_segment(store_name)
    # Prefer the exact store configured for the selected month. "重庆茁凯"
    # historically shared the "邱存帅" rule, but newer owner files can
    # configure both rows independently. Keep that alias only as a fallback.
    principal = store_rules.get(store_key)
    if principal is None and store_key == "重庆茁凯":
        principal = store_rules.get("邱存帅")
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
