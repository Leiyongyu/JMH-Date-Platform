from __future__ import annotations

from itertools import islice

from backend.database import db_connection

TABLE = "ods_goodcang_wh_inventory_storage"
DETAIL_TABLE = "ods_goodcang_wh_inventory_storage_detail"
FIELDS = (
    "currency_code", "isdb_volume", "is_amount", "is_date", "is_settlement_amount",
    "note", "settlement_currency_code", "warehouse_code", "wis_code", "wp_settlement_cycle",
    "request_date_from", "request_date_to", "source_page", "source_row_no",
    "api_count", "sync_batch_id", "pulled_at", "raw_json",
)
DETAIL_FIELDS = (
    "wis_code", "reference_no", "warehouse_code", "product_sku", "product_barcode",
    "product_name", "quantity", "length", "width", "height", "volume", "cargo_type",
    "day", "bill_amount", "settlement_amount", "warehouse_rent_amount",
    "bill_currency_code", "settlement_currency_code", "charge_date", "putaway_date",
    "request_wis_code", "request_date_from", "request_date_to", "source_page",
    "source_row_no", "api_count", "sync_batch_id", "pulled_at", "raw_json",
)


def _insert_rows(cursor, table, fields, rows):
    columns = ",".join(f"`{field}`" for field in fields)
    placeholders = ",".join(f"%({field})s" for field in fields)
    query = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
    iterator = iter(rows)
    inserted = 0
    while batch := list(islice(iterator, 500)):
        cursor.executemany(query, batch)
        inserted += len(batch)
    return inserted


def replace_storage_snapshot(summary_rows, detail_rows):
    """Atomically replace both tables, only after the entire remote chain is validated.

    detail_rows is a disk-backed iterator. An IO/parse error while consuming it
    must roll back both DELETEs and all inserts, just like a database failure.
    """
    with db_connection() as connection:
        # Explicit begin prevents DBUtils reconnect/replay after an individual DELETE.
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{DETAIL_TABLE}`")
                deleted_details = cursor.rowcount
                cursor.execute(f"DELETE FROM `{TABLE}`")
                deleted_summaries = cursor.rowcount
                summaries = _insert_rows(cursor, TABLE, FIELDS, summary_rows)
                details = _insert_rows(cursor, DETAIL_TABLE, DETAIL_FIELDS, detail_rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "ods_rows": summaries + details, "inserted_rows": summaries + details,
        "deleted_rows": deleted_summaries + deleted_details,
        "summary_ods_rows": summaries, "detail_ods_rows": details,
        "deleted_summary_rows": deleted_summaries, "deleted_detail_rows": deleted_details,
    }
