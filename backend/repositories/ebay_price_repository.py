from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pymysql.connections import Connection

from backend.database import db_connection


def replace_sku_mappings(sku_to_oes: dict[str, list[str]], source_file_name: str | None) -> dict[str, int]:
    if not sku_to_oes:
        return {
            "affected_skus": 0,
            "created_skus": 0,
            "updated_skus": 0,
            "inserted_mappings": 0,
        }
    with db_connection() as connection:
        try:
            result = replace_sku_mappings_in_connection(connection, sku_to_oes, source_file_name)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise


def replace_sku_mappings_in_connection(
    connection: Connection,
    sku_to_oes: dict[str, list[str]],
    source_file_name: str | None,
) -> dict[str, int]:
    skus = list(sku_to_oes)
    with connection.cursor() as cursor:
        existing = set()
        if skus:
            placeholders = ",".join(["%s"] * len(skus))
            cursor.execute(
                f"SELECT DISTINCT sku FROM dim_ebay_sku_oe_mapping WHERE sku IN ({placeholders})",
                skus,
            )
            existing = {row["sku"] for row in cursor.fetchall()}
        cursor.execute(
            f"DELETE FROM dim_ebay_sku_oe_mapping WHERE sku IN ({','.join(['%s'] * len(skus))})",
            skus,
        )
        rows = []
        for sku, oes in sku_to_oes.items():
            for index, oe in enumerate(oes, 1):
                rows.append(
                    {
                        "sku": sku,
                        "oe": oe,
                        "oe_index": index,
                        "source_file_name": source_file_name,
                    }
                )
        if rows:
            cursor.executemany(
                """
                INSERT INTO dim_ebay_sku_oe_mapping (
                    sku, oe, oe_index, source_file_name
                ) VALUES (
                    %(sku)s, %(oe)s, %(oe_index)s, %(source_file_name)s
                )
                """,
                rows,
            )
    return {
        "affected_skus": len(skus),
        "created_skus": len([sku for sku in skus if sku not in existing]),
        "updated_skus": len([sku for sku in skus if sku in existing]),
        "inserted_mappings": len(rows),
    }


def get_oes_by_skus(skus: Iterable[str]) -> dict[str, list[str]]:
    sku_list = [sku for sku in skus if sku]
    if not sku_list:
        return {}
    with db_connection() as connection:
        with connection.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(sku_list))
            cursor.execute(
                f"""
                SELECT sku, oe
                FROM dim_ebay_sku_oe_mapping
                WHERE sku IN ({placeholders})
                ORDER BY sku ASC, oe_index ASC, id ASC
                """,
                sku_list,
            )
            rows = cursor.fetchall()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row["sku"], []).append(row["oe"])
    return result


def list_mappings(keyword: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if keyword:
        where = "WHERE sku LIKE %s OR oe LIKE %s"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    params.append(max(1, min(limit, 1000)))
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT sku, GROUP_CONCAT(oe ORDER BY oe_index ASC, id ASC SEPARATOR ',') AS oe
                FROM dim_ebay_sku_oe_mapping
                {where}
                GROUP BY sku
                ORDER BY sku ASC
                LIMIT %s
                """,
                params,
            )
            return list(cursor.fetchall())
