from __future__ import annotations

from backend.database import db_connection

TABLE = "ods_goodcang_wh_inventory_storage"
FIELDS = (
    "currency_code", "isdb_volume", "is_amount", "is_date", "is_settlement_amount",
    "note", "settlement_currency_code", "warehouse_code", "wis_code", "wp_settlement_cycle",
    "request_date_from", "request_date_to", "source_page", "source_row_no",
    "api_count", "sync_batch_id", "pulled_at", "raw_json",
)


def replace_storage_rows(rows):
    """Only call after all pages are validated; empty confirmed results clear the table."""
    columns = ",".join(f"`{field}`" for field in FIELDS)
    placeholders = ",".join(f"%({field})s" for field in FIELDS)
    # Explicit begin prevents DBUtils reconnecting/replaying an individual SQL
    # statement after DELETE. Never use TRUNCATE (implicit commit).
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{TABLE}`")
                deleted = cursor.rowcount
                for start in range(0, len(rows), 500):
                    cursor.executemany(
                        f"INSERT INTO `{TABLE}` ({columns}) VALUES ({placeholders})",
                        rows[start:start + 500],
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"ods_rows": len(rows), "inserted_rows": len(rows), "deleted_rows": deleted}

