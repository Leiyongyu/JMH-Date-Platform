from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from backend.integrations.lingxing.domains.inventory import LingXingInventoryDomain
from backend.parsers.inventory_age_cost_parser import parse_inventory_age_cost_excel
from backend.repositories import clearance_repository as repo

TASK_CODE = "amz_fba_inventory_snapshot_sync"
PATH = "basicOpen/openapi/storage/fbaWarehouseDetail"
PAGE_SIZE = 200
MAX_PAGES = 10000
PARTIAL_PAGE_RETRIES = 2
PAGE_INTERVAL_SECONDS = 1.1
logger = logging.getLogger(__name__)


def import_inventory_age_cost(
    content: bytes,
    file_name: str,
    operator: str | None = None,
) -> dict:
    parsed = parse_inventory_age_cost_excel(content, file_name)
    with repo.connection() as conn:
        try:
            stats = repo.replace_inventory_age_cost_month(
                conn, parsed["cost_month"], parsed["rows"], operator
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "batch_id": parsed["batch_id"],
        "cost_month": parsed["cost_month"],
        "total_rows": len(parsed["rows"]),
        "amz_rows": parsed["amz_rows"],
        **stats,
    }


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
        ods.append({
            "pull_month": month, "sync_batch_id": batch_id,
            "source_offset": (index // PAGE_SIZE) * PAGE_SIZE,
            "source_row_no": index + 1, "sid": sid,
            "seller_sku": item.get("seller_sku"),
            "raw_json": json.dumps(item, ensure_ascii=False, default=str),
            "pulled_at": pulled_at,
        })
        group, source, store = _group(item, sid, shops)
        if not group:
            continue
        q0, c0 = _num(item.get("inv_age_0_to_90_days")), _num(item.get("inv_age_0_to_90_price"))
        q1, c1 = _num(item.get("inv_age_91_to_180_days")), _num(item.get("inv_age_91_to_180_price"))
        q2, c2 = _num(item.get("inv_age_181_to_270_days")), _num(item.get("inv_age_181_to_270_price"))
        q3, c3 = _num(item.get("inv_age_271_to_365_days")), _num(item.get("inv_age_271_to_365_price"))
        q4, c4 = _num(item.get("inv_age_365_plus_days")), _num(item.get("inv_age_365_plus_price"))
        dwd.append({
            "pull_month": month, "sync_batch_id": batch_id, "sid": sid,
            "store_name": store, "seller_group_name": item.get("seller_group_name"),
            "warehouse_name": item.get("name"), "asin": item.get("asin"),
            "seller_sku": item.get("seller_sku"), "fnsku": item.get("fnsku"),
            "sku": item.get("sku"), "product_name": item.get("product_name"),
            "group_code": group, "region_code": "EU" if group == "EU" else "US",
            "region_name": "欧洲组" if group == "EU" else "美国组",
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
    with repo.connection() as conn:
        repo.append_ods(conn, ods)
        conn.commit()
    with repo.connection() as conn:
        try:
            stats = repo.replace_month(conn, month, dwd, groups)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "pull_month": month, "sync_batch_id": batch_id,
        "extract_rows": len(remote), "ods_rows": len(ods),
        **stats, "unmatched_group_rows": len(remote) - len(dwd),
        "status": "completed",
    }


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
