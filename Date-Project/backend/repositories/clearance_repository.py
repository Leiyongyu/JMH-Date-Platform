from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.database import db_connection


def connection():
    return db_connection()


def amazon_shop_map() -> dict[str, str]:
    database = settings.shop_source_database.strip() or "jmh_data_platform"
    escaped_database = database.replace("`", "``")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT CAST(sid AS CHAR) sid, MAX(store_name) store_name
            FROM `{escaped_database}`.shop_list
            WHERE platform_code='10001' AND sid IS NOT NULL
            GROUP BY sid
            """
        )
        return {str(r["sid"]): r["store_name"] for r in cur.fetchall()}


def append_ods(conn, rows: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ods_lingxing_amz_fba_inventory_raw
            (pull_month,sync_batch_id,source_offset,source_row_no,sid,
             seller_sku,raw_json,pulled_at)
            VALUES
            (%(pull_month)s,%(sync_batch_id)s,%(source_offset)s,
             %(source_row_no)s,%(sid)s,%(seller_sku)s,%(raw_json)s,
             %(pulled_at)s)
            """,
            rows,
        )


def replace_month(conn, month: str, rows: list[dict], groups: list[dict]) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) n FROM dwd_amz_fba_inventory_monthly_snapshot "
            "WHERE pull_month=%s", (month,)
        )
        old = int(cur.fetchone()["n"])
        cur.execute(
            "DELETE FROM dwd_amz_fba_inventory_monthly_snapshot "
            "WHERE pull_month=%s", (month,)
        )
        if rows:
            cur.executemany(
                """
                INSERT INTO dwd_amz_fba_inventory_monthly_snapshot
                (pull_month,sync_batch_id,sid,store_name,seller_group_name,
                 warehouse_name,asin,seller_sku,fnsku,sku,product_name,
                 group_code,region_code,region_name,group_match_source,
                 inventory_0_90_qty,inventory_0_90_cost,
                 inventory_91_180_qty,inventory_91_180_cost,
                 inventory_181_270_qty,inventory_181_270_cost,
                 inventory_271_365_qty,inventory_271_365_cost,
                 inventory_365_plus_qty,inventory_365_plus_cost,
                 inventory_181_plus_qty,inventory_181_plus_cost,
                 total_inventory_qty,total_inventory_cost,pulled_at)
                VALUES
                (%(pull_month)s,%(sync_batch_id)s,%(sid)s,%(store_name)s,
                 %(seller_group_name)s,%(warehouse_name)s,%(asin)s,
                 %(seller_sku)s,%(fnsku)s,%(sku)s,%(product_name)s,
                 %(group_code)s,%(region_code)s,%(region_name)s,
                 %(group_match_source)s,%(inventory_0_90_qty)s,
                 %(inventory_0_90_cost)s,%(inventory_91_180_qty)s,
                 %(inventory_91_180_cost)s,%(inventory_181_270_qty)s,
                 %(inventory_181_270_cost)s,%(inventory_271_365_qty)s,
                 %(inventory_271_365_cost)s,%(inventory_365_plus_qty)s,
                 %(inventory_365_plus_cost)s,%(inventory_181_plus_qty)s,
                 %(inventory_181_plus_cost)s,%(total_inventory_qty)s,
                 %(total_inventory_cost)s,%(pulled_at)s)
                """, rows
            )
        cur.execute(
            "DELETE FROM dws_amz_fba_inventory_age_group WHERE pull_month=%s",
            (month,),
        )
        if groups:
            cur.executemany(
                """
                INSERT INTO dws_amz_fba_inventory_age_group
                (pull_month,region_code,region_name,group_code,group_name,
                 shop_count,source_row_count,inventory_0_90_qty,
                 inventory_0_90_cost,inventory_91_180_qty,
                 inventory_91_180_cost,inventory_181_plus_qty,
                 inventory_181_plus_cost,total_inventory_qty,
                 total_inventory_cost,pulled_at)
                VALUES
                (%(pull_month)s,%(region_code)s,%(region_name)s,
                 %(group_code)s,%(group_name)s,%(shop_count)s,
                 %(source_row_count)s,%(inventory_0_90_qty)s,
                 %(inventory_0_90_cost)s,%(inventory_91_180_qty)s,
                 %(inventory_91_180_cost)s,%(inventory_181_plus_qty)s,
                 %(inventory_181_plus_cost)s,%(total_inventory_qty)s,
                 %(total_inventory_cost)s,%(pulled_at)s)
                """, groups
            )
    new = len(rows)
    return {
        "old_rows": old,
        "dwd_rows": new,
        "group_rows": len(groups),
        "inserted_rows": max(new - old, 0),
        "updated_rows": min(old, new),
        "deleted_rows": max(old - new, 0),
    }


def list_groups(month: str | None) -> dict:
    with db_connection() as conn, conn.cursor() as cur:
        if not month:
            cur.execute("SELECT MAX(pull_month) m FROM dws_amz_fba_inventory_age_group")
            month = cur.fetchone()["m"]
        if not month:
            return {"pull_month": None, "items": [], "total": 0}
        cur.execute(
            "SELECT * FROM dws_amz_fba_inventory_age_group "
            "WHERE pull_month=%s ORDER BY FIELD(group_code,'EU','US1','US2','US3')",
            (month,),
        )
        items = list(cur.fetchall())
        return {"pull_month": month, "items": items, "total": len(items)}


def summary(month: str | None) -> dict:
    data = list_groups(month)
    fields = [
        "inventory_0_90_qty", "inventory_0_90_cost",
        "inventory_91_180_qty", "inventory_91_180_cost",
        "inventory_181_plus_qty", "inventory_181_plus_cost",
        "total_inventory_qty", "total_inventory_cost",
    ]
    result = {"pull_month": data["pull_month"], "group_count": data["total"]}
    for field in fields:
        result[field] = sum((row[field] for row in data["items"]), 0)
    result["pulled_at"] = max(
        (row["pulled_at"] for row in data["items"]), default=None
    )
    return result


def months(limit: int = 24) -> list[dict]:
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pull_month,MAX(pulled_at) pulled_at,COUNT(1) group_count "
            "FROM dws_amz_fba_inventory_age_group GROUP BY pull_month "
            "ORDER BY pull_month DESC LIMIT %s", (limit,)
        )
        return list(cur.fetchall())
