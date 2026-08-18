from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.config import settings
from backend.database import db_connection
from backend.schemas.inventory_report_source_fields import (
    FBA_SOURCE_FIELDS,
    LOCAL_SOURCE_FIELDS,
    OVERSEAS_SOURCE_FIELDS,
)


TABLE_FIELDS = {
    "fba": (
        "ods_lingxing_fba_monthly_inventory_detail",
        FBA_SOURCE_FIELDS,
    ),
    "overseas": (
        "ods_lingxing_overseas_monthly_inventory_detail",
        OVERSEAS_SOURCE_FIELDS,
    ),
    "local": (
        "ods_lingxing_local_monthly_inventory_detail",
        LOCAL_SOURCE_FIELDS,
    ),
    "order_profit": (
        "ods_lingxing_inventory_report_amz_order_profit",
        (),
    ),
}

INVENTORY_SOURCE_TYPES = ("fba", "overseas", "local")

ORDER_PROFIT_FIELDS = (
    "stat_month",
    "sid",
    "msku",
    "local_sku",
    "asin",
    "item_name",
    "currency_code",
    "amount",
    "volume",
    "pulled_at",
)

META_FIELDS = (
    "stat_month",
    "sync_batch_id",
    "query_start_date",
    "query_end_date",
    "request_scope_json",
    "source_page",
    "source_offset",
    "source_row_no",
    "api_code",
    "api_message",
    "api_trace_id",
    "api_request_id",
    "api_response_time",
    "api_error_details",
    "api_total",
    "api_start_date",
    "api_end_date",
    "api_day_interval",
    "api_amount_type",
    "api_size",
    "api_current",
)


def amazon_seller_ids() -> list[str]:
    database = _source_database()
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT CAST(sid AS CHAR) AS sid
            FROM `{database}`.`shop_list`
            WHERE platform_code = '10001'
              AND sid IS NOT NULL
              AND CAST(sid AS CHAR) <> ''
            ORDER BY sid
            """
        )
        return [str(row["sid"]) for row in cursor.fetchall()]


def warehouse_wids() -> list[str]:
    database = _source_database()
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT CAST(wid AS CHAR) AS wid
            FROM `{database}`.`warehouse`
            WHERE wid IS NOT NULL
              AND wid > 0
              AND (is_delete = 0 OR is_delete IS NULL)
            ORDER BY wid
            """
        )
        return [str(row["wid"]) for row in cursor.fetchall()]


def replace_source_month(
    stat_month: str,
    rows_by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Atomically replace one month in the three inventory source tables."""
    source_stats: dict[str, dict[str, int]] = {}
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for source in INVENTORY_SOURCE_TYPES:
                    table, fields = TABLE_FIELDS[source]
                    cursor.execute(
                        f"SELECT COUNT(1) AS total FROM `{table}` "
                        "WHERE stat_month = %s",
                        (stat_month,),
                    )
                    old_rows = int(cursor.fetchone()["total"] or 0)
                    cursor.execute(
                        f"DELETE FROM `{table}` WHERE stat_month = %s",
                        (stat_month,),
                    )
                    new_rows = rows_by_source.get(source, [])
                    _insert_rows(cursor, table, fields, new_rows)
                    source_stats[source] = {
                        "deleted_rows": old_rows,
                        "inserted_rows": len(new_rows),
                    }
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "sources": source_stats,
        "deleted_rows": sum(item["deleted_rows"] for item in source_stats.values()),
        "inserted_rows": sum(item["inserted_rows"] for item in source_stats.values()),
    }


def replace_order_profit_month(
    stat_month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace only one month's AMZ order-profit source snapshot."""
    table = TABLE_FIELDS["order_profit"][0]
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(1) AS total FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                old_rows = int(cursor.fetchone()["total"] or 0)
                cursor.execute(
                    f"DELETE FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                _insert_explicit_rows(cursor, table, ORDER_PROFIT_FIELDS, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted_rows": old_rows, "inserted_rows": len(rows)}


def _insert_rows(cursor, table: str, fields: tuple[str, ...], rows: list[dict]) -> None:
    if not rows:
        return
    columns = (*META_FIELDS, *fields, "raw_row_json", "pulled_at")
    column_sql = ",".join(f"`{column}`" for column in columns)
    value_sql = ",".join(f"%({column})s" for column in columns)
    sql = f"INSERT INTO `{table}` ({column_sql}) VALUES ({value_sql})"
    for batch in _chunks(rows, 300):
        cursor.executemany(sql, batch)


def _insert_explicit_rows(
    cursor,
    table: str,
    fields: tuple[str, ...],
    rows: list[dict],
) -> None:
    if not rows:
        return
    column_sql = ",".join(f"`{column}`" for column in fields)
    value_sql = ",".join(f"%({column})s" for column in fields)
    sql = f"INSERT INTO `{table}` ({column_sql}) VALUES ({value_sql})"
    for batch in _chunks(rows, 300):
        cursor.executemany(sql, batch)


def _chunks(rows: list[dict], size: int) -> Iterable[list[dict]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _source_database() -> str:
    return (settings.shop_source_database.strip() or "jmh_data_platform").replace(
        "`", "``"
    )
