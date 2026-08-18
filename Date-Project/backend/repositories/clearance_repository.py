from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.config import settings
from backend.database import db_connection


GROUP_ORDER_SQL = (
    "FIELD(g.group_code,'EBAY-1','EU','US1','US2','US2-MJ','US1-ZXY')"
)

GROUP_SOURCE_SQL = """
    SELECT pull_month,region_code,region_name,group_code,group_name,
           shop_count,source_row_count,inventory_0_90_qty,
           inventory_0_90_cost,inventory_91_180_qty,
           inventory_91_180_cost,inventory_181_plus_qty,
           inventory_181_plus_cost,total_inventory_qty,
           total_inventory_cost,pulled_at
    FROM dws_amz_fba_inventory_age_group
    UNION ALL
    SELECT pull_month,'EBAY' AS region_code,'eBay组' AS region_name,
           'EBAY-1' AS group_code,'EBAY-1' AS group_name,
           COUNT(DISTINCT warehouse_code) AS shop_count,
           COUNT(*) AS source_row_count,
           COALESCE(SUM(CASE WHEN inventory_age_bucket='0_90'
                    THEN inventory_quantity ELSE 0 END),0) AS inventory_0_90_qty,
           COALESCE(SUM(CASE WHEN inventory_age_bucket='0_90'
                    THEN inventory_age_cost ELSE 0 END),0) AS inventory_0_90_cost,
           COALESCE(SUM(CASE WHEN inventory_age_bucket='91_180'
                    THEN inventory_quantity ELSE 0 END),0) AS inventory_91_180_qty,
           COALESCE(SUM(CASE WHEN inventory_age_bucket='91_180'
                    THEN inventory_age_cost ELSE 0 END),0) AS inventory_91_180_cost,
           COALESCE(SUM(CASE WHEN inventory_age_bucket='181_PLUS'
                    THEN inventory_quantity ELSE 0 END),0) AS inventory_181_plus_qty,
           COALESCE(SUM(CASE WHEN inventory_age_bucket='181_PLUS'
                    THEN inventory_age_cost ELSE 0 END),0) AS inventory_181_plus_cost,
           COALESCE(SUM(inventory_quantity),0) AS total_inventory_qty,
           COALESCE(SUM(inventory_age_cost),0) AS total_inventory_cost,
           MAX(pulled_at) AS pulled_at
    FROM dwd_ebay_inventory_age_cost_snapshot
    GROUP BY pull_month
"""


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


def resolve_store_name(
    shops: dict[str, str],
    sid: Any,
    warehouse_name: Any = None,
) -> str:
    store_name = shops.get(str(sid or ""))
    normalized = str(store_name or "").strip()
    if normalized:
        return normalized
    if str(sid or "0") == "0":
        normalized_warehouse = str(warehouse_name or "").strip()
        if normalized_warehouse:
            return normalized_warehouse
    return "0"


def ebay_inventory_age_source_rows(month: str) -> list[dict[str, Any]]:
    """跨库读取谷仓库龄，并按去前缀后的SKU匹配领星采购与头程成本。"""
    database = settings.shop_source_database.strip() or "jmh_data_platform"
    escaped_database = database.replace("`", "``")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            WITH product_candidates AS (
                SELECT p.id,p.snapshot_month,p.sku,p.cg_price,
                       p.sync_batch_id,
                       CASE WHEN LOCATE('-',p.sku)>0
                            THEN SUBSTRING(p.sku,LOCATE('-',p.sku)+1)
                            ELSE p.sku END AS sku_middle,
                       COUNT(*) OVER (
                           PARTITION BY p.snapshot_month,
                             CASE WHEN LOCATE('-',p.sku)>0
                                  THEN SUBSTRING(p.sku,LOCATE('-',p.sku)+1)
                                  ELSE p.sku END
                       ) AS candidate_count,
                       SUM(CASE WHEN p.sku NOT LIKE 'JMH-%%' THEN 1 ELSE 0 END)
                           OVER (
                           PARTITION BY p.snapshot_month,
                             CASE WHEN LOCATE('-',p.sku)>0
                                  THEN SUBSTRING(p.sku,LOCATE('-',p.sku)+1)
                                  ELSE p.sku END
                       ) AS non_jmh_count,
                       ROW_NUMBER() OVER (
                           PARTITION BY p.snapshot_month,
                             CASE WHEN LOCATE('-',p.sku)>0
                                  THEN SUBSTRING(p.sku,LOCATE('-',p.sku)+1)
                                  ELSE p.sku END
                           ORDER BY CASE WHEN p.sku LIKE 'JMH-%%' THEN 1 ELSE 0 END,
                                    p.sku,p.id
                       ) AS candidate_rank
                FROM `{escaped_database}`.ods_lingxing_product_procurement_monthly p
                WHERE p.snapshot_month=%s
            ), selected_products AS (
                SELECT * FROM product_candidates WHERE candidate_rank=1
            ), step_prices AS (
                SELECT snapshot_month,sku,MAX(NULLIF(price,0)) AS step_price
                FROM `{escaped_database}`.ods_lingxing_product_supplier_step_price_monthly
                WHERE snapshot_month=%s
                GROUP BY snapshot_month,sku
            ), transport_costs AS (
                SELECT snapshot_month,sku,country_code,
                       MAX(transport_cost) AS transport_cost
                FROM `{escaped_database}`.ods_lingxing_product_transport_cost_monthly
                WHERE snapshot_month=%s
                  AND country_code IN ('US','UK','DE','CZ')
                GROUP BY snapshot_month,sku,country_code
            )
            SELECT g.id AS source_inventory_age_id,
                   g.snapshot_month AS pull_month,
                   g.sync_batch_id AS source_goodcang_batch_id,
                   p.sync_batch_id AS source_product_batch_id,
                   g.product_sku AS source_product_sku,
                   CASE WHEN LOCATE('-',g.product_sku)>0
                        THEN SUBSTRING(g.product_sku,LOCATE('-',g.product_sku)+1)
                        ELSE g.product_sku END AS sku_middle,
                   p.sku,p.cg_price,sp.step_price,
                   g.warehouse_code,g.warehouse_desc AS warehouse_name,
                   CASE
                       WHEN UPPER(g.warehouse_code) IN ('USEA','USWE') THEN 'US'
                       WHEN UPPER(g.warehouse_code)='UK' THEN 'UK'
                       WHEN UPPER(g.warehouse_code)='DE' THEN 'DE'
                       WHEN UPPER(g.warehouse_code)='CZ' THEN 'CZ'
                       ELSE NULL
                   END AS transport_country_code,
                   g.iba_quantity AS inventory_quantity,
                   g.warehouse_age AS warehouse_age_days,
                   tc.transport_cost AS first_leg_cost,
                   p.candidate_count,p.non_jmh_count,
                   g.pulled_at AS source_pulled_at
            FROM `{escaped_database}`.ods_goodcang_inventory_age_monthly g
            LEFT JOIN selected_products p
              ON p.snapshot_month=g.snapshot_month
             AND p.sku_middle=(
                 CASE WHEN LOCATE('-',g.product_sku)>0
                      THEN SUBSTRING(g.product_sku,LOCATE('-',g.product_sku)+1)
                      ELSE g.product_sku END
             )
            LEFT JOIN step_prices sp
              ON sp.snapshot_month=p.snapshot_month AND sp.sku=p.sku
            LEFT JOIN transport_costs tc
              ON tc.snapshot_month=p.snapshot_month AND tc.sku=p.sku
             AND tc.country_code=(
                 CASE
                     WHEN UPPER(g.warehouse_code) IN ('USEA','USWE') THEN 'US'
                     WHEN UPPER(g.warehouse_code)='UK' THEN 'UK'
                     WHEN UPPER(g.warehouse_code)='DE' THEN 'DE'
                     WHEN UPPER(g.warehouse_code)='CZ' THEN 'CZ'
                     ELSE NULL
                 END
             )
            WHERE g.snapshot_month=%s
            ORDER BY g.id
            """,
            (month, month, month, month),
        )
        return list(cur.fetchall())


def replace_ebay_inventory_age_month(
    conn,
    month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """按月整月替换eBay库龄成本清洗明细。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) n FROM dwd_ebay_inventory_age_cost_snapshot "
            "WHERE pull_month=%s",
            (month,),
        )
        old_rows = int(cur.fetchone()["n"])
        cur.execute(
            "DELETE FROM dwd_ebay_inventory_age_cost_snapshot "
            "WHERE pull_month=%s",
            (month,),
        )
        if rows:
            cur.executemany(
                """
                INSERT INTO dwd_ebay_inventory_age_cost_snapshot
                (pull_month,sync_batch_id,source_inventory_age_id,
                 source_goodcang_batch_id,source_product_batch_id,
                 source_product_sku,sku_middle,sku,warehouse_code,
                 warehouse_name,transport_country_code,inventory_quantity,
                 warehouse_age_days,inventory_age_bucket,cg_price,step_price,
                 purchase_price,first_leg_cost,unit_landed_cost,
                 inventory_age_cost,match_status,source_pulled_at,pulled_at)
                VALUES
                (%(pull_month)s,%(sync_batch_id)s,%(source_inventory_age_id)s,
                 %(source_goodcang_batch_id)s,%(source_product_batch_id)s,
                 %(source_product_sku)s,%(sku_middle)s,%(sku)s,
                 %(warehouse_code)s,%(warehouse_name)s,
                 %(transport_country_code)s,%(inventory_quantity)s,
                 %(warehouse_age_days)s,%(inventory_age_bucket)s,
                 %(cg_price)s,%(step_price)s,%(purchase_price)s,
                 %(first_leg_cost)s,%(unit_landed_cost)s,
                 %(inventory_age_cost)s,%(match_status)s,
                 %(source_pulled_at)s,%(pulled_at)s)
                """,
                rows,
            )
    return {
        "ebay_old_rows": old_rows,
        "ebay_dwd_rows": len(rows),
        "ebay_deleted_rows": old_rows,
        "ebay_inserted_rows": len(rows),
    }


def replace_ods_month(
    conn,
    month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) n FROM ods_lingxing_amz_fba_inventory_raw "
            "WHERE pull_month=%s",
            (month,),
        )
        old_rows = int(cur.fetchone()["n"])
        cur.execute(
            "DELETE FROM ods_lingxing_amz_fba_inventory_raw WHERE pull_month=%s",
            (month,),
        )
        if rows:
            cur.executemany(
                """
                INSERT INTO ods_lingxing_amz_fba_inventory_raw
                (pull_month,sync_batch_id,source_offset,source_row_no,sid,
                 seller_sku,sku,warehouse_name,seller_group_name,share_type,
                 group_code,region_code,region_name,group_match_source,
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
                 %(warehouse_name)s,%(seller_group_name)s,%(share_type)s,
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
    return {
        "ods_old_rows": old_rows,
        "ods_deleted_rows": old_rows,
        "ods_inserted_rows": len(rows),
    }


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
                 warehouse_name,seller_sku,sku,
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
                 %(store_name)s,%(seller_group_name)s,%(warehouse_name)s,
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
            cur.execute(
                f"SELECT MAX(pull_month) m FROM ({GROUP_SOURCE_SQL}) groups_all"
            )
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
            FROM ({GROUP_SOURCE_SQL}) g
            LEFT JOIN dwd_inventory_age_cost_monthly c
              ON c.cost_month=%s
             AND (
                 c.group_code=g.group_code
                 OR (g.group_code='EBAY-1' AND c.department_code='EBAY-1')
             )
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
            f"""
            SELECT pull_month,MAX(pulled_at) pulled_at,COUNT(1) group_count
            FROM ({GROUP_SOURCE_SQL}) groups_all
            GROUP BY pull_month
            ORDER BY pull_month DESC LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def inventory_age_details(month: str | None) -> dict[str, Any]:
    shops = amazon_shop_map()
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
            SELECT pull_month,region_name,group_code,sid,
                   warehouse_name,seller_group_name,share_type,seller_sku,sku,
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
              AND sync_batch_id = (
                  SELECT sync_batch_id
                  FROM ods_lingxing_amz_fba_inventory_raw
                  WHERE pull_month=%s AND group_code IS NOT NULL
                  ORDER BY pulled_at DESC,id DESC
                  LIMIT 1
              )
            ORDER BY FIELD(group_code,'EU','US1','US2','US2-MJ','US1-ZXY'),
                     sid,seller_sku,sku,id
            """,
            (month, month),
        )
        items = list(cur.fetchall())
        for item in items:
            item["store_name"] = resolve_store_name(
                shops,
                item.get("sid"),
                item.get("warehouse_name"),
            )
            item["shared_store_names"] = (
                str(item.get("seller_group_name") or "").strip()
                if str(item.get("sid") or "0") == "0"
                else ""
            )
        return {"pull_month": month, "items": items}
