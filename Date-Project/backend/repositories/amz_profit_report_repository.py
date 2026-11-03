"""Storage for the AMZ profit report sources (all USD, one month per replace)."""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from backend.database import db_connection
from backend.schemas.amz_profit_report_fields import ORDER_COLUMNS, SETTLEMENT_COLUMNS


SELLER_TABLE = "ods_lingxing_profit_seller_daily"
MSKU_TABLE = "dwd_lingxing_profit_msku_month"
ORDER_TABLE = "ods_lingxing_order_profit_msku_month"

SELLER_FIELDS = (
    "stat_month", "posted_date", "sid", "store_name", "country_code",
    "currency_code", *SETTLEMENT_COLUMNS, "raw_json", "sync_batch_id", "synced_at",
)
MSKU_FIELDS = (
    "stat_month", "sid", "msku", "asin", "store_name", "country_code",
    "local_sku", "local_name", "principal_realname", "currency_code",
    *SETTLEMENT_COLUMNS, "estimate_fees_json", "source_rows",
    "sync_batch_id", "synced_at",
)
ORDER_FIELDS = (
    "stat_month", "sid", "msku", "asin", "local_sku", "local_name", "country",
    "principal_names", "currency_code", *ORDER_COLUMNS,
    "sync_batch_id", "synced_at",
)
JSON_FIELDS = {"raw_json", "estimate_fees_json"}


def replace_month(
    stat_month: str,
    seller_rows: list[dict[str, Any]],
    msku_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace all three sources of one month together, or none of them."""
    payloads = (
        (SELLER_TABLE, SELLER_FIELDS, seller_rows),
        (MSKU_TABLE, MSKU_FIELDS, msku_rows),
        (ORDER_TABLE, ORDER_FIELDS, order_rows),
    )
    deleted = 0
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for table, fields, rows in payloads:
                    deleted += cursor.execute(
                        f"DELETE FROM `{table}` WHERE stat_month=%s", (stat_month,)
                    ) or 0
                    _insert_rows(cursor, table, fields, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "deleted_rows": deleted,
        "seller_rows": len(seller_rows),
        "msku_rows": len(msku_rows),
        "order_rows": len(order_rows),
    }


def msku_month_rows(stat_month: str) -> list[dict[str, Any]]:
    return _select_month(MSKU_TABLE, (
        "sid", "msku", "store_name", "local_sku", *SETTLEMENT_COLUMNS,
    ), stat_month)


def order_month_rows(stat_month: str) -> list[dict[str, Any]]:
    return _select_month(ORDER_TABLE, (
        "sid", "msku", "local_sku", *ORDER_COLUMNS,
    ), stat_month)


def months(limit: int = 24) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT m.stat_month,MAX(m.synced_at) AS synced_at,
                   MAX(m.has_settlement) AS has_settlement,
                   MAX(m.has_order) AS has_order
            FROM (
                SELECT stat_month,MAX(synced_at) AS synced_at,
                       1 AS has_settlement,0 AS has_order
                FROM `{MSKU_TABLE}` GROUP BY stat_month
                UNION ALL
                SELECT stat_month,MAX(synced_at) AS synced_at,
                       0 AS has_settlement,1 AS has_order
                FROM `{ORDER_TABLE}` GROUP BY stat_month
            ) m
            GROUP BY m.stat_month
            ORDER BY m.stat_month DESC
            LIMIT %s
            """,
            (max(1, min(int(limit), 120)),),
        )
        return list(cursor.fetchall())


def _select_month(
    table: str, fields: tuple[str, ...], stat_month: str,
) -> list[dict[str, Any]]:
    columns = ",".join(f"`{field}`" for field in fields)
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {columns} FROM `{table}` WHERE stat_month=%s", (stat_month,)
        )
        return list(cursor.fetchall())


def _insert_rows(
    cursor, table: str, fields: tuple[str, ...], rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    columns = ",".join(f"`{field}`" for field in fields)
    values = ",".join(f"%({field})s" for field in fields)
    statement = f"INSERT INTO `{table}` ({columns}) VALUES ({values})"
    for batch in _chunks(rows, 300):
        cursor.executemany(statement, [_db_row(row, fields) for row in batch])


def _db_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    result = {field: row.get(field) for field in fields}
    for field in JSON_FIELDS & set(fields):
        if result[field] is not None:
            result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
    return result


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]
