from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from backend.integrations.lingxing.domains.inventory import LingXingInventoryDomain
from backend.repositories import clearance_repository as repo

TASK_CODE = "amz_fba_inventory_snapshot_sync"
PATH = "basicOpen/openapi/storage/fbaWarehouseDetail"
PAGE_SIZE = 200
MAX_PAGES = 10000
PARTIAL_PAGE_RETRIES = 2
PAGE_INTERVAL_SECONDS = 1.1
logger = logging.getLogger(__name__)


def sync_fba_inventory(pull_month: str | None = None) -> dict:
    month = pull_month or datetime.now().strftime("%Y-%m")
    batch_id = str(uuid4())
    pulled_at = datetime.now()
    domain = LingXingInventoryDomain()
    remote = []
    offset = 0
    expected_total = None
    completed = False
    for _ in range(MAX_PAGES):
        body = {
            "offset": offset,
            "length": PAGE_SIZE,
            "query_fba_storage_quantity_list": True,
        }
        response = domain.request(
            PATH,
            body,
        )
        batch, response_total = _response_page(response)
        if response_total is not None:
            expected_total = response_total
        if not batch:
            completed = True
            break
        if len(batch) < PAGE_SIZE:
            for _retry in range(PARTIAL_PAGE_RETRIES):
                time.sleep(PAGE_INTERVAL_SECONDS)
                retry_batch, retry_total = _response_page(
                    domain.request(PATH, body)
                )
                if retry_total is not None:
                    expected_total = retry_total
                if len(retry_batch) > len(batch):
                    batch = retry_batch
        remote.extend(batch)
        if len(batch) < PAGE_SIZE:
            completed = True
            break
        offset += PAGE_SIZE
        time.sleep(PAGE_INTERVAL_SECONDS)
    if not completed:
        raise RuntimeError(f"领星FBA库存超过最大分页限制: {MAX_PAGES}页")
    if expected_total is not None and expected_total != len(remote):
        logger.warning(
            "领星FBA库存分页期间total发生变化或存在延迟: "
            "接口报告%s条，按短页结束标志实际取得%s条",
            expected_total,
            len(remote),
        )
    if not remote:
        raise RuntimeError("领星FBA库存返回0条，拒绝覆盖")

    shops = repo.amazon_shop_map()
    ods, dwd = [], []
    for index, item in enumerate(remote):
        sid = str(item.get("sid") or "0")
        age_fields = _inventory_age_fields(item)
        identity_fields = _inventory_identity_fields(item)
        group, source, _store = _group(item, sid, shops)
        region_code = "EU" if group == "EU" else "US" if group else None
        region_name = "欧洲组" if group == "EU" else "美国组" if group else None
        ods.append({
            "pull_month": month, "sync_batch_id": batch_id,
            "source_offset": (index // PAGE_SIZE) * PAGE_SIZE,
            "source_row_no": index + 1, "sid": sid,
            "seller_sku": item.get("seller_sku"),
            "sku": item.get("sku"),
            **identity_fields,
            "group_code": group,
            "region_code": region_code,
            "region_name": region_name,
            "group_match_source": source,
            **age_fields,
            "pulled_at": pulled_at,
        })
        if not group:
            continue
        q0, c0 = age_fields["inv_age_0_to_90_days"], age_fields["inv_age_0_to_90_price"]
        q1, c1 = age_fields["inv_age_91_to_180_days"], age_fields["inv_age_91_to_180_price"]
        q2, c2 = age_fields["inv_age_181_to_270_days"], age_fields["inv_age_181_to_270_price"]
        q3, c3 = age_fields["inv_age_271_to_365_days"], age_fields["inv_age_271_to_365_price"]
        q4, c4 = age_fields["inv_age_365_plus_days"], age_fields["inv_age_365_plus_price"]
        dwd.append({
            "pull_month": month, "sync_batch_id": batch_id, "sid": sid,
            "store_name": repo.resolve_store_name(
                shops, sid, identity_fields["warehouse_name"]
            ),
            "seller_group_name": identity_fields["seller_group_name"],
            "warehouse_name": identity_fields["warehouse_name"],
            "seller_sku": item.get("seller_sku"), "sku": item.get("sku"),
            "group_code": group, "region_code": region_code,
            "region_name": region_name,
            "group_match_source": source,
            "inventory_0_90_qty": q0, "inventory_0_90_cost": c0,
            "inventory_91_180_qty": q1, "inventory_91_180_cost": c1,
            "inventory_181_270_qty": q2, "inventory_181_270_cost": c2,
            "inventory_271_365_qty": q3, "inventory_271_365_cost": c3,
            "inventory_365_plus_qty": q4, "inventory_365_plus_cost": c4,
            "inventory_181_plus_qty": q2 + q3 + q4,
            "inventory_181_plus_cost": c2 + c3 + c4,
            "total_inventory_qty": q0 + q1 + q2 + q3 + q4,
            "total_inventory_cost": c0 + c1 + c2 + c3 + c4,
            "pulled_at": pulled_at,
        })
    groups = _groups(month, dwd, pulled_at)
    ebay_source = repo.ebay_inventory_age_source_rows(month)
    if not ebay_source:
        raise RuntimeError(
            f"{month} 谷仓eBay库存库龄源数据为0条，拒绝覆盖清洗明细；"
            "请先完成Java端谷仓和领星产品源数据同步"
        )
    ebay_rows, ebay_stats = _ebay_inventory_age_rows(
        month, batch_id, pulled_at, ebay_source
    )
    with repo.connection() as conn:
        try:
            ods_stats = repo.replace_ods_month(conn, month, ods)
            stats = repo.replace_month(conn, month, dwd, groups)
            ebay_persisted = repo.replace_ebay_inventory_age_month(
                conn, month, ebay_rows
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "pull_month": month, "sync_batch_id": batch_id,
        "extract_rows": len(remote), "ods_rows": len(ods),
        **ods_stats, **stats,
        "unmatched_group_rows": len(remote) - len(dwd),
        "ebay_extract_rows": len(ebay_source),
        **ebay_stats,
        **ebay_persisted,
        "status": "completed",
    }


REQUIRED_INVENTORY_FIELDS = (
    "inv_age_0_to_30_days",
    "inv_age_0_to_30_price",
    "inv_age_31_to_60_days",
    "inv_age_31_to_60_price",
    "inv_age_61_to_90_days",
    "inv_age_61_to_90_price",
    "inv_age_0_to_90_days",
    "inv_age_0_to_90_price",
    "inv_age_91_to_180_days",
    "inv_age_91_to_180_price",
    "inv_age_181_to_270_days",
    "inv_age_181_to_270_price",
    "inv_age_271_to_330_days",
    "inv_age_271_to_330_price",
    "inv_age_271_to_365_days",
    "inv_age_271_to_365_price",
    "inv_age_331_to_365_days",
    "inv_age_331_to_365_price",
    "inv_age_365_plus_days",
    "inv_age_365_plus_price",
)


def _group(item, sid, shops):
    store = shops.get(sid)
    if store:
        for code in ("EU", "US1", "US2"):
            if store.startswith(code + "-"):
                return code, "shop_list", store
        if store.startswith("US3-"):
            if any(name in store for name in ("新志楠", "富琳顿", "富林顿")):
                return "US2-MJ", "shop_list_us3_split", store
            return "US1-ZXY", "shop_list_us3_split", store
    if sid == "0" and (
        str(item.get("seller_group_name") or "").startswith("EU-")
        or str(item.get("name") or "").startswith("AMZ-EU-")
    ):
        return "EU", "shared_warehouse", store
    return None, None, store


def _response_page(response: dict) -> tuple[list[dict], int | None]:
    if not isinstance(response, dict):
        raise RuntimeError("领星FBA库存接口返回为空")
    if int(response.get("code", -1)) != 0:
        raise RuntimeError(
            "领星FBA库存失败: "
            f"code={response.get('code')}, "
            f"message={response.get('message') or response.get('msg')}, "
            f"error_details={response.get('error_details') or response.get('errorDetails')}"
        )
    batch = response.get("data")
    if not isinstance(batch, list):
        raise RuntimeError("领星FBA库存data不是数组")
    try:
        total = int(response["total"]) if response.get("total") is not None else None
    except (TypeError, ValueError):
        total = None
    return batch, total


def _num(value) -> Decimal:
    text = str(value or "0").replace(",", "").replace("￥", "").replace("¥", "").replace("$", "").strip()
    try:
        return Decimal(text or "0")
    except InvalidOperation:
        return Decimal("0")


def _inventory_age_fields(item: dict) -> dict[str, Decimal]:
    """Keep only the LingXing inventory-age fields required by clearance."""
    return {field: _num(item.get(field)) for field in REQUIRED_INVENTORY_FIELDS}


def _inventory_identity_fields(item: dict) -> dict[str, str | int | None]:
    """Keep the shared-warehouse identity needed for later exports."""
    warehouse_name = str(item.get("name") or "").strip() or None
    seller_group_name = str(item.get("seller_group_name") or "").strip() or None
    try:
        share_type = (
            int(item["share_type"])
            if item.get("share_type") not in (None, "")
            else None
        )
    except (TypeError, ValueError):
        share_type = None
    return {
        "warehouse_name": warehouse_name,
        "seller_group_name": seller_group_name,
        "share_type": share_type,
    }


def _groups(month, rows, pulled_at):
    agg = defaultdict(list)
    for row in rows:
        agg[row["group_code"]].append(row)
    result = []
    for code in ("EU", "US1", "US2", "US2-MJ", "US1-ZXY"):
        items = agg.get(code, [])
        if not items:
            continue
        result.append({
            "pull_month": month, "group_code": code, "group_name": code,
            "region_code": "EU" if code == "EU" else "US",
            "region_name": "欧洲组" if code == "EU" else "美国组",
            "shop_count": len({x["sid"] for x in items if x["sid"] != "0"}),
            "source_row_count": len(items),
            **{f: sum((x[f] for x in items), Decimal("0")) for f in (
                "inventory_0_90_qty", "inventory_0_90_cost",
                "inventory_91_180_qty", "inventory_91_180_cost",
                "inventory_181_plus_qty", "inventory_181_plus_cost",
                "total_inventory_qty", "total_inventory_cost")},
            "pulled_at": pulled_at,
        })
    return result


def _ebay_inventory_age_rows(
    month: str,
    batch_id: str,
    pulled_at: datetime,
    source_rows: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """将谷仓库龄与领星采购、头程数据清洗为可追溯成本明细。"""
    rows = []
    status_counts: dict[str, int] = defaultdict(int)
    for source in source_rows:
        candidate_count = int(source.get("candidate_count") or 0)
        non_jmh_count = int(source.get("non_jmh_count") or 0)
        product_matched = non_jmh_count == 1 or (
            non_jmh_count == 0 and candidate_count == 1
        )
        if not product_matched:
            status = (
                "PRODUCT_AMBIGUOUS"
                if candidate_count > 0
                else "PRODUCT_NOT_FOUND"
            )
            sku = None
            source_product_batch_id = None
            cg_price = None
            step_price = None
            purchase_price = None
            first_leg_cost = None
        else:
            sku = source.get("sku")
            source_product_batch_id = source.get("source_product_batch_id")
            cg_price = _optional_num(source.get("cg_price"))
            step_price = _optional_num(source.get("step_price"))
            purchase_price = (
                step_price
                if step_price is not None and step_price > Decimal("0")
                else cg_price
            )
            first_leg_cost = _optional_num(source.get("first_leg_cost"))
            if purchase_price is None:
                status = "PURCHASE_PRICE_NOT_FOUND"
            elif first_leg_cost is None:
                status = "TRANSPORT_COST_NOT_FOUND"
            else:
                status = "MATCHED"

        quantity = _num(source.get("inventory_quantity"))
        unit_landed_cost = (
            purchase_price + first_leg_cost
            if purchase_price is not None and first_leg_cost is not None
            else None
        )
        inventory_age_cost = unit_landed_cost
        age = _optional_int(source.get("warehouse_age_days"))
        bucket = (
            "UNKNOWN"
            if age is None
            else "0_90"
            if age <= 90
            else "91_180"
            if age <= 180
            else "181_PLUS"
        )
        status_counts[status] += 1
        rows.append({
            "pull_month": month,
            "sync_batch_id": batch_id,
            "source_inventory_age_id": source["source_inventory_age_id"],
            "source_goodcang_batch_id": source["source_goodcang_batch_id"],
            "source_product_batch_id": source_product_batch_id,
            "source_product_sku": source.get("source_product_sku") or "",
            "sku_middle": source.get("sku_middle") or "",
            "sku": sku,
            "warehouse_code": source.get("warehouse_code") or "",
            "warehouse_name": source.get("warehouse_name"),
            "transport_country_code": source.get("transport_country_code"),
            "inventory_quantity": quantity,
            "warehouse_age_days": age,
            "inventory_age_bucket": bucket,
            "cg_price": cg_price,
            "step_price": step_price,
            "purchase_price": purchase_price,
            "first_leg_cost": first_leg_cost,
            "unit_landed_cost": unit_landed_cost,
            "inventory_age_cost": inventory_age_cost,
            "match_status": status,
            "source_pulled_at": source["source_pulled_at"],
            "pulled_at": pulled_at,
        })
    return rows, {
        "ebay_matched_rows": status_counts["MATCHED"],
        "ebay_unmatched_rows": len(rows) - status_counts["MATCHED"],
        "ebay_product_not_found_rows": status_counts["PRODUCT_NOT_FOUND"],
        "ebay_product_ambiguous_rows": status_counts["PRODUCT_AMBIGUOUS"],
        "ebay_purchase_price_missing_rows": status_counts[
            "PURCHASE_PRICE_NOT_FOUND"
        ],
        "ebay_transport_cost_missing_rows": status_counts[
            "TRANSPORT_COST_NOT_FOUND"
        ],
    }


def _optional_num(value) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    text = (
        str(value)
        .replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("$", "")
        .strip()
    )
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _optional_int(value) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError):
        return None
