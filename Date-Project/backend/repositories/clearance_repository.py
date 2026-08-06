from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.config import settings
from backend.database import db_connection


GROUP_ORDER_SQL = "FIELD(g.group_code,'EU','US1','US2','US2-MJ','US1-ZXY')"


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
             seller_sku,sku,group_code,region_code,region_name,group_match_source,
             inv_age_0_to_30_days,inv_age_0_to_30_price,
             inv_age_31_to_60_days,inv_age_31_to_60_price,
             inv_age_61_to_90_days,inv_age_61_to_90_price,
             inv_age_0_to_90_days,inv_age_0_to_90_price,
             inv_age_91_to_180_days,inv_age_91_to_180_price,
             inv_age_181_to_270_days,inv_age_181_to_270_price,
             inv_age_271_to_330_days,inv_age_271_to_330_price,
             inv_age_271_to_365_days,inv_age_271_to_365_price,
             inv_age_331_to_365_days,inv_age_331_to_365_price,
             inv_age_365_plus_days,inv_age_365_plus_price,pulled_at)
            VALUES
            (%(pull_month)s,%(sync_batch_id)s,%(source_offset)s,
             %(source_row_no)s,%(sid)s,%(seller_sku)s,%(sku)s,
             %(group_code)s,%(region_code)s,%(region_name)s,%(group_match_source)s,
             %(inv_age_0_to_30_days)s,%(inv_age_0_to_30_price)s,
             %(inv_age_31_to_60_days)s,%(inv_age_31_to_60_price)s,
             %(inv_age_61_to_90_days)s,%(inv_age_61_to_90_price)s,
             %(inv_age_0_to_90_days)s,%(inv_age_0_to_90_price)s,
             %(inv_age_91_to_180_days)s,%(inv_age_91_to_180_price)s,
             %(inv_age_181_to_270_days)s,%(inv_age_181_to_270_price)s,
             %(inv_age_271_to_330_days)s,%(inv_age_271_to_330_price)s,
             %(inv_age_271_to_365_days)s,%(inv_age_271_to_365_price)s,
             %(inv_age_331_to_365_days)s,%(inv_age_331_to_365_price)s,
             %(inv_age_365_plus_days)s,%(inv_age_365_plus_price)s,
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
                (pull_month,sync_batch_id,sid,seller_sku,sku,
                 group_code,region_code,region_name,group_match_source,
                 inventory_0_90_qty,inventory_0_90_cost,
                 inventory_91_180_qty,inventory_91_180_cost,
                 inventory_181_270_qty,inventory_181_270_cost,
                 inventory_271_365_qty,inventory_271_365_cost,
                 inventory_365_plus_qty,inventory_365_plus_cost,
                 inventory_181_plus_qty,inventory_181_plus_cost,
                 total_inventory_qty,total_inventory_cost,pulled_at)
                VALUES
                (%(pull_month)s,%(sync_batch_id)s,%(sid)s,
                 %(seller_sku)s,%(sku)s,%(group_code)s,%(region_code)s,%(region_name)s,
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


def replace_inventory_age_cost_month(
    conn,
    cost_month: str,
    rows: list[dict[str, Any]],
    operator: str | None,
) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) n FROM dwd_inventory_age_cost_monthly "
            "WHERE cost_month=%s",
            (cost_month,),
        )
        old_rows = int(cur.fetchone()["n"])
        cur.execute(
            "DELETE FROM dwd_inventory_age_cost_monthly WHERE cost_month=%s",
            (cost_month,),
        )
        if rows:
            payload = [{**row, "operator": operator} for row in rows]
            cur.executemany(
                """
                INSERT INTO dwd_inventory_age_cost_monthly
                (cost_month,department_code,group_code,
                 inventory_91_180_cost,inventory_181_plus_cost,
                 source_file_name,source_sheet,source_row,
                 import_batch_id,operator)
                VALUES
                (%(cost_month)s,%(department_code)s,%(group_code)s,
                 %(inventory_91_180_cost)s,%(inventory_181_plus_cost)s,
                 %(source_file_name)s,%(source_sheet)s,%(source_row)s,
                 %(import_batch_id)s,%(operator)s)
                """,
                payload,
            )
    return {
        "old_rows": old_rows,
        "inserted_rows": len(rows),
        "replaced_rows": old_rows,
    }


def list_groups(month: str | None) -> dict:
    with db_connection() as conn, conn.cursor() as cur:
        if not month:
            cur.execute("SELECT MAX(pull_month) m FROM dws_amz_fba_inventory_age_group")
            month = cur.fetchone()["m"]
        if not month:
            return {"pull_month": None, "items": [], "total": 0}
        month_start = datetime.strptime(month, "%Y-%m")
        previous_month = (month_start - timedelta(days=1)).strftime("%Y-%m")
        cur.execute(
            f"""
            SELECT g.*,
                   c.cost_month AS previous_cost_month,
                   c.inventory_91_180_cost AS previous_month_91_180_cost,
                   CASE WHEN c.id IS NULL THEN NULL
                        ELSE c.inventory_91_180_cost - g.inventory_91_180_cost END
                       AS inventory_91_180_variance,
                   c.inventory_181_plus_cost AS previous_month_181_plus_cost,
                   CASE WHEN c.id IS NULL THEN NULL
                        ELSE c.inventory_181_plus_cost - g.inventory_181_plus_cost END
                       AS inventory_181_plus_variance
            FROM dws_amz_fba_inventory_age_group g
            LEFT JOIN dwd_inventory_age_cost_monthly c
              ON c.cost_month=%s
             AND c.group_code=g.group_code
            WHERE g.pull_month=%s
            ORDER BY {GROUP_ORDER_SQL}
            """,
            (previous_month, month),
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


def inventory_age_details(month: str | None) -> dict[str, Any]:
    with db_connection() as conn, conn.cursor() as cur:
        if not month:
            cur.execute(
                "SELECT MAX(pull_month) m "
                "FROM ods_lingxing_amz_fba_inventory_raw "
                "WHERE group_code IS NOT NULL"
            )
            month = cur.fetchone()["m"]
        if not month:
            return {"pull_month": None, "items": []}
        cur.execute(
            """
            SELECT pull_month,region_name,group_code,sid,seller_sku,sku,
                   inv_age_0_to_30_days,inv_age_0_to_30_price,
                   inv_age_31_to_60_days,inv_age_31_to_60_price,
                   inv_age_61_to_90_days,inv_age_61_to_90_price,
                   inv_age_0_to_90_days,inv_age_0_to_90_price,
                   inv_age_91_to_180_days,inv_age_91_to_180_price,
                   inv_age_181_to_270_days,inv_age_181_to_270_price,
                   inv_age_271_to_330_days,inv_age_271_to_330_price,
                   inv_age_271_to_365_days,inv_age_271_to_365_price,
                   inv_age_331_to_365_days,inv_age_331_to_365_price,
                   inv_age_365_plus_days,inv_age_365_plus_price,
                   pulled_at,sync_batch_id
            FROM ods_lingxing_amz_fba_inventory_raw
            WHERE pull_month=%s AND group_code IS NOT NULL
            ORDER BY FIELD(group_code,'EU','US1','US2','US2-MJ','US1-ZXY'),
                     sid,seller_sku,sku,id
            """,
            (month,),
        )
        return {"pull_month": month, "items": list(cur.fetchall())}
