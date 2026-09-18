"""Isolated latest raw listing snapshot in the Python database, never the Java table."""
from __future__ import annotations

import json
from datetime import datetime
from itertools import islice
from zoneinfo import ZoneInfo

from backend.config import settings
from backend.database import db_connection

FIELDS = tuple("""listing_id sid marketplace seller_sku fnsku asin parent_asin small_image_url
status is_delete item_name local_sku local_name currency_code price landed_price listing_price
shipping points quantity afn_fulfillable_quantity afn_unsellable_quantity reserved_fc_transfers
reserved_fc_processing reserved_customerorders afn_inbound_shipped_quantity afn_inbound_working_quantity
afn_inbound_receiving_quantity open_date open_date_display listing_update_date seller_rank seller_brand
seller_category review_num last_star fulfillment_channel_type principal_info seller_category_new
pair_update_time first_order_time on_sale_time store_type total_volume yesterday_volume fourteen_volume
thirty_volume yesterday_amount seven_amount fourteen_amount thirty_amount average_seven_volume
average_fourteen_volume average_thirty_volume dimension_info small_rank global_tags variant""".split())
JSON_FIELDS = {"principal_info", "seller_category_new", "dimension_info", "small_rank", "global_tags", "variant"}
TABLE = "ods_lingxing_amz_listing_latest"
STATE_TABLE = "ods_lingxing_amz_listing_state"
METADATA = ("source_row_no", "request_sids", "source_offset", "source_row_in_page", "api_total",
            "api_request_id", "api_response_time", "response_meta_json", "sync_batch_id", "pulled_at", "raw_json")


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def shop_sids() -> list[str]:
    database = (settings.shop_source_database.strip() or "jmh_data_platform").replace("`", "``")
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT DISTINCT sid FROM `{database}`.shop_list "
                       "WHERE platform_code='10001' AND status=1 AND sid IS NOT NULL AND sid<>'' ORDER BY sid")
        values = [str(row["sid"]).strip() for row in cursor.fetchall()]
    if not values or any(not s.isascii() or not s.isdecimal() or int(s) <= 0 for s in values):
        raise ValueError("Amazon启用店铺sid为空或不合法；拒绝替换原始表，请先同步店铺")
    return list(dict.fromkeys(str(int(s)) for s in values))


def record_values(record, batch_id, pulled_at):
    row = record["row"]
    values = []
    for field in FIELDS:
        value = row.get(field)
        if value is not None:
            if field in JSON_FIELDS or isinstance(value, (dict, list, bool)):
                value = dumps(value)
            elif field not in {"sid", "status", "is_delete"}:
                value = str(value)
        values.append(value)
    meta = record["response_meta"]
    return tuple(values) + (record["row_no"], record["request_sids"], record["offset"],
        record["row_in_page"], record["total"], str(meta.get("request_id") or ""),
        str(meta.get("response_time") or ""), dumps(meta), batch_id, pulled_at, dumps(row))


def replace_snapshot(records, *, expected_rows: int, batch_id: str, pulled_at: datetime, shop_count: int):
    """Single transaction: old data and publication marker survive any insert failure."""
    columns = FIELDS + METADATA
    sql = f"INSERT INTO {TABLE} (" + ",".join(f"`{c}`" for c in columns) + ") VALUES (" + ",".join(["%s"] * len(columns)) + ")"
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {TABLE}")
                deleted = cursor.rowcount
                inserted = 0
                iterator = iter(records)
                while chunk := list(islice(iterator, 250)):
                    cursor.executemany(sql, [record_values(r, batch_id, pulled_at) for r in chunk])
                    inserted += len(chunk)
                cursor.execute(f"SELECT COUNT(*) AS n FROM {TABLE}")
                if inserted != expected_rows or int(cursor.fetchone()["n"]) != expected_rows:
                    raise ValueError("AMZ原始刊登写入数量与已校验拉取数量不一致")
                published_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
                cursor.execute(f"INSERT INTO {STATE_TABLE} (id,sync_batch_id,row_count,shop_count,pulled_at,published_at) "
                               "VALUES (1,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                               "sync_batch_id=VALUES(sync_batch_id),row_count=VALUES(row_count),"
                               "shop_count=VALUES(shop_count),pulled_at=VALUES(pulled_at),published_at=VALUES(published_at)",
                               (batch_id, inserted, shop_count, pulled_at, published_at))
            connection.commit()
            return {"ods_rows": inserted, "inserted_rows": inserted, "deleted_rows": deleted}
        except Exception:
            connection.rollback()
            raise
