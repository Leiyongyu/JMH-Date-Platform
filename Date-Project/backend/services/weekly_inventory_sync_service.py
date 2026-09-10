from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from backend.integrations.lingxing.client import LingXingClient
from backend.repositories import weekly_inventory_repository as repo
from backend.services.weekly_inventory_api import WeeklyRequestError, request_response, safe_text

TASK_CODE = "weekly_inventory_bin_export"
LOG = logging.getLogger(__name__)
PREFIX = "erp/sc/routing/data/local_inventory/"
INV_NUMBERS = "product_total product_valid_num expect_valid_num product_bad_num product_qc_num product_lock_num good_lock_num bad_lock_num storage_distribute_num quantity_receive expect_pending_num product_onway available_inventory_box_qty stock_cost_total stock_cost stock_price purchase_price price head_stock_price transit_head_cost".split()
PRODUCT_NUMBERS = ("cg_price cg_product_length cg_product_width cg_product_height cg_package_length cg_package_width cg_package_height cg_box_length cg_box_width cg_box_height cg_box_weight cg_product_net_weight cg_product_gross_weight").split()
PRODUCT_TEXT = "sku product_name model unit brand_name category_name category_full_name product_developer cg_opt_username cg_product_material currency bg_customs_export_name bg_customs_import_name bg_export_hs_code bg_import_hs_code".split()


def number(value):
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("领星返回非法数值") from exc
    if not result.is_finite():
        raise ValueError("领星返回非有限数值")
    return result


def integer(value, *, required=False):
    value = number(value)
    if value is None:
        if required:
            raise ValueError("领星返回缺失的主键")
        return None
    if value != value.to_integral_value() or (required and value <= 0):
        raise ValueError("领星返回非法整数或主键")
    return int(value)


def response_rows(response):
    if not isinstance(response, dict) or str(response.get("code")) != "0" or not isinstance(response.get("data"), list):
        raise ValueError("领星周报接口失败或返回结构异常；请查任务日志")
    rows = response["data"]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("领星周报接口行结构异常")
    return rows


def fetch_pages(client, endpoint, size, *, batch="-"):
    rows, expected = [], None
    for page_no in range(1, 10001):
        body = {"offset": len(rows), "length": size}
        response = request_response(client, endpoint, body, batch=batch, page=page_no)
        page = response_rows(response)
        try:
            total = integer(response.get("total"))
            if total is None or total < 0:
                raise ValueError("领星分页接口缺少有效total，拒绝不完整快照")
            if expected is not None and expected != total:
                raise ValueError("拉取期间接口total变化，请重新生成完整快照")
            if len(page) > size or len(rows) + len(page) > total:
                raise ValueError("领星分页数量异常")
            if len(rows) + len(page) != total and (not page or len(page) < size):
                raise ValueError("领星分页提前结束，拒绝不完整快照")
        except ValueError as exc:
            raise WeeklyRequestError(
                f"领星周报完整性校验失败；接口={PREFIX}{endpoint} batch={batch} "
                f"page={page_no} offset={len(rows)} length={size} code=0 "
                f"upstream_request_id={safe_text(response.get('request_id'), client, 100)}；{exc}"
            ) from None
        expected = total
        rows.extend(page)
        if len(rows) == total:
            return rows
    raise ValueError("领星分页超过安全上限")


def unique(rows, fields):
    seen = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in seen:
            # Reject repeated pages as well as conflicting duplicates: do not
            # conceal an incomplete source behind a successful total count.
            raise ValueError(f"领星快照主键重复：{fields}={key}")
        seen[key] = row
    return rows


def normalize(inventory, bins, products, day, batch, pulled_at):
    common = {"snapshot_date": day, "sync_batch_id": batch}
    result = {key: [] for key in repo.TABLES}
    for source in inventory:
        row = {**common, "wid": integer(source.get("wid"), required=True),
               "product_id": integer(source.get("product_id"), required=True),
               "seller_id": str(source.get("seller_id") or "0"),
               "sku": source.get("sku"), "fnsku": source.get("fnsku")}
        row.update({field: number(source.get(field)) for field in INV_NUMBERS})
        row.update(average_age=integer(source.get("average_age")), stock_age_list=source.get("stock_age_list"),
                   third_inventory=source.get("third_inventory"), raw_json=source, pulled_at=pulled_at)
        result["inventory"].append(row)
        buckets = source.get("stock_age_list") or []
        if not isinstance(buckets, list) or len(buckets) > 127:
            raise ValueError("库存库龄分档结构异常")
        names = set()
        for index, bucket in enumerate(buckets):
            name = str(bucket.get("name") or "").strip()
            if not name or name in names:
                raise ValueError("库存库龄分档名为空或重复")
            names.add(name)
            result["age"].append({**common, **{k: row[k] for k in ("wid", "product_id", "seller_id")},
                                  "bucket_index": index, "bucket_name": name, "qty": number(bucket.get("qty"))})
    for source in bins:
        row = {**common, **{key: integer(source.get(key), required=True) for key in ("wid", "whb_id", "product_id")}}
        row.update({key: source.get(key) for key in "wh_name whb_name whb_type_name sku product_name msku store_id fnsku".split()})
        row.update(whb_type=integer(source.get("whb_type")), total=number(source.get("total")),
                   lock_num=number(source.get("lockNum")), valid_num=number(source.get("validNum")),
                   third_inventory=source.get("third_inventory"), raw_json=source, pulled_at=pulled_at)
        result["bins"].append(row)
    for source in products:
        row = {**common, "product_id": integer(source.get("id"), required=True)}
        row.update({key: source.get(key) for key in PRODUCT_TEXT})
        row.update({key: number(source.get(key)) for key in PRODUCT_NUMBERS})
        row.update({key: integer(source.get(key)) for key in "status is_combo cg_delivery cg_box_pcs".split()})
        row.update(raw_json=source, pulled_at=pulled_at)
        result["products"].append(row)
    unique(result["inventory"], ("wid", "product_id", "seller_id"))
    unique_bin_rows(result["bins"])
    unique(result["products"], ("product_id",))
    return result


def bin_identity(row):
    """Match the generated binary database key without changing source fields.

    Missing/blank store means unassigned (0); missing MSKU/FNSKU means empty.
    Preserve MSKU/FNSKU case and spaces, exactly as the SQL length framing does.
    """
    values = []
    for field in ("store_id", "msku", "fnsku"):
        value = row.get(field)
        if value is not None and (not isinstance(value, (str, int)) or isinstance(value, bool)):
            raise ValueError(f"领星仓位明细{field}类型异常")
        values.append("" if value is None else str(value))
    values[0] = values[0].strip(" ") or "0"
    return (row["wid"], row["whb_id"], row["product_id"], *values)


def unique_bin_rows(rows):
    seen = set()
    for row in rows:
        key = bin_identity(row)
        if key in seen:
            raise ValueError(
                "领星仓位明细完整业务键重复，拒绝不确定去重："
                f"(wid,whb_id,product_id,store_id,msku,fnsku)={key}"
            )
        seen.add(key)
    return rows


def sync_weekly_inventory(trigger_type="JOB"):
    """Called under the scheduler's global named lock; never label live data as historical."""
    from backend.services.weekly_inventory_export_service import export_root, write_export

    now, batch = datetime.now(), str(uuid4())
    day = now.date()
    filename = f"仓位库存明细_{day}_{batch}.xlsx"
    root = export_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / filename
    repo.begin_export(batch, day, filename, path, trigger_type)
    try:
        repo.require_bin_identity_schema()
        # One retry owner only: four attempts per page/batch in request_response.
        # Other consumers retain their existing LingXingClient retry settings.
        client = LingXingClient(max_retries=0)
        inventory = fetch_pages(client, "inventoryDetails", 800, batch=batch)
        if not inventory:
            raise ValueError("库存源数据为空，拒绝生成空周报")
        bins = fetch_pages(client, "inventoryBinDetails", 500, batch=batch)
        ids = sorted({integer(row.get("product_id"), required=True) for row in inventory})
        products = []
        for start in range(0, len(ids), 100):
            requested = ids[start:start + 100]
            response = request_response(client, "batchGetProductInfo", {"productIds": requested},
                                        batch=batch, page=start // 100 + 1)
            data = response_rows(response)
            try:
                returned = [integer(row.get("id"), required=True) for row in data]
                if len(returned) != len(set(returned)) or set(returned) != set(requested):
                    raise ValueError("领星产品详情缺失、重复或返回非请求产品，拒绝不完整快照")
            except ValueError as exc:
                raise WeeklyRequestError(
                    f"领星产品详情完整性校验失败；{exc}；"
                    f"接口={PREFIX}batchGetProductInfo batch={batch} page={start // 100 + 1} "
                    f"product_count={len(requested)} returned_count={len(data)} code=0 "
                    f"upstream_request_id={safe_text(response.get('request_id'), client, 100)}"
                ) from None
            products.extend(data)
        groups = normalize(inventory, bins, products, day, batch, datetime.now())
        ods_rows = repo.insert_snapshot(groups)
        # Read exactly this committed batch, never today's latest rows.
        metrics = write_export(repo.snapshot(batch), repo.warehouse_names(), path)
        repo.finish_export(batch, file_name=filename, **metrics)
        return {"sync_batch_id": batch, "snapshot_date": str(day), "extract_rows": len(inventory) + len(bins) + len(products),
                "ods_rows": ods_rows, "file_name": filename, **metrics,
                "deduplicated_inventory_rows": len(inventory) - metrics["row_count"]}
    except Exception as exc:
        LOG.exception("Weekly inventory failed, batch=%s", batch)
        try:
            summary = str(exc) if isinstance(exc, WeeklyRequestError) else "请查看服务器任务日志"
            repo.finish_export(batch, file_name=filename, error=f"生成失败，批次 {batch}；{summary}；已有快照及文件保留")
        except Exception:
            LOG.exception("Weekly inventory failure registration failed, batch=%s", batch)
        raise
