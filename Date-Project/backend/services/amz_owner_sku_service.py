from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.parsers.performance_common import normalize_text
from backend.repositories import amz_owner_sku_repository as repo
from backend.services.owner_sku_common import include_configured_owners, is_pc_sku
from backend.services.performance_service import UNASSIGNED, _amazon_principal, _amazon_store_rules


def summarize(rows: list[dict], rules: dict) -> dict:
    """Monthly performance assignment; dedup full seller SKU within each owner."""
    store_rules = _amazon_store_rules(rules)
    owners = defaultdict(set)
    missing_sku_rows = 0
    excluded_pc_rows = 0
    missing_shop_keys = set()
    for row in rows:
        if is_pc_sku(row.get("local_sku")) or is_pc_sku(row.get("seller_sku")):
            excluded_pc_rows += 1
            continue
        sku = normalize_text(row.get("seller_sku")).upper()
        if not sku:
            missing_sku_rows += 1
            continue
        principal, _, missing_shop = _amazon_principal(row, rules, store_rules)
        if missing_shop:
            missing_shop_keys.add((normalize_text(row.get("sid")), sku))
        # Missing shops remain visible as unassigned rather than disappearing.
        owners[principal].add(sku)
    items = sorted(
        [{"principal_name": name, "sku_count": len(keys), "unassigned": name == UNASSIGNED}
         for name, keys in owners.items()],
        key=lambda item: (-item["sku_count"], item["principal_name"]),
    )
    return {"items": items, "total": sum(item["sku_count"] for item in items),
            "owner_count": sum(not item["unassigned"] for item in items),
            "unassigned_count": len(owners.get(UNASSIGNED, ())),
            "missing_sku_rows": missing_sku_rows, "missing_shop_count": len(missing_shop_keys),
            "excluded_pc_rows": excluded_pc_rows}


def get_owner_sku_counts() -> dict:
    # Imports include future months: never select MAX(stat_month).
    month = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")
    source = repo.load_source(month)
    sync = source["sync"]
    result = {"rule_month": month, "source_api": "/erp/sc/data/mws/listing",
              "source_table": "ods_lingxing_amz_listing_latest",
              "dedup_key": ["principal_name", "seller_sku"],
              "listing_status": 1, "is_delete": 0, "items": [], "total": None, "warnings": []}
    if not sync or sync["status"] != "SUCCESS":
        return {**result, "state": "SOURCE_NOT_READY", "message":
                "尚无完整AMZ原始刊登快照，请执行“领星-AMZ刊登原始数据每周同步”后刷新；不回退到旧补货源表。"}
    if not source["rules"]:
        return {**result, "state": "MISSING_RULES", "message": f"缺少{month}的AMZ负责人规则，请先导入当月规则。"}
    rows = source["rows"]
    result.update(summarize(rows, source["rules"]))
    include_configured_owners(result, source["rules"].values())
    times = [row["sync_time"] for row in rows if row.get("sync_time")]
    result["source_updated_at"] = max(times).isoformat(sep=" ") if times else None
    result["source_rows"] = len(rows)
    result["state"] = "READY" if rows else "EMPTY"
    result["message"] = "" if rows else "当前没有status=1且is_delete=0的未删除在售刊登数据。"
    if result["missing_sku_rows"]:
        result["warnings"].append(f"{result['missing_sku_rows']}条记录缺少卖家SKU（seller_sku），未计入统计。")
    if result["missing_shop_count"]:
        result["warnings"].append(f"{result['missing_shop_count']}个店铺SKU缺少店铺名称，已计入未分配。")
    return result
