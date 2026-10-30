from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.config import settings
from backend.database import db_connection
from backend.services.clearance_metrics import BUCKETS, FIELDS, PREFIXES, GROUP_CODES, aggregate, attach_comparison, compare, previous_month, total_metrics


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


def ctu_warehouse_names(wids) -> dict[str, str]:
    """Read current warehouse names from the shared LingXing warehouse dimension."""
    normalized = [str(wid).strip() for wid in wids if str(wid).strip()]
    if not normalized:
        return {}
    database = settings.shop_source_database.strip() or "jmh_data_platform"
    escaped_database = database.replace("`", "``")
    placeholders = ",".join(["%s"] * len(normalized))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT CAST(wid AS CHAR) wid,MAX(NULLIF(TRIM(name),'')) warehouse_name
            FROM `{escaped_database}`.warehouse
            WHERE CAST(wid AS CHAR) IN ({placeholders})
            GROUP BY wid
            """,
            tuple(normalized),
        )
        return {
            str(row["wid"]): str(row["warehouse_name"]).strip()
            for row in cur.fetchall()
            if str(row.get("warehouse_name") or "").strip()
        }

def ebay_inventory_age_source_rows(month: str, *, latest: bool = False) -> list[dict[str, Any]]:
    """跨库读取谷仓库龄，并按去前缀后的SKU匹配领星采购与头程成本。"""
    database = settings.shop_source_database.strip() or "jmh_data_platform"
    escaped_database = database.replace("`", "``")
    # The default remains the clearance monthly snapshot. The age-ratio report
    # uses latest inventory with the calculation month's procurement costs.
    source_table = "ods_goodcang_inventory_age_latest" if latest else "ods_goodcang_inventory_age_monthly"
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
            FROM `{escaped_database}`.{source_table} g
            LEFT JOIN selected_products p
              ON {"1=1" if latest else "p.snapshot_month=g.snapshot_month"}
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
            WHERE {"%s IS NOT NULL" if latest else "g.snapshot_month=%s"}
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


def replace_ctu_inventory_month(
    conn,
    month: str,
    rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> dict[str, int]:
    """Atomically replace one current-month CTU detail and group snapshot."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) n FROM ods_lingxing_ctu_inventory_detail "
            "WHERE pull_month=%s",
            (month,),
        )
        old_ods_rows = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT COUNT(1) n FROM dws_ctu_inventory_age_group "
            "WHERE pull_month=%s",
            (month,),
        )
        old_group_rows = int(cur.fetchone()["n"])
        cur.execute(
            "DELETE FROM ods_lingxing_ctu_inventory_detail WHERE pull_month=%s",
            (month,),
        )
        cur.execute(
            "DELETE FROM dws_ctu_inventory_age_group WHERE pull_month=%s",
            (month,),
        )
        if rows:
            cur.executemany(
                """
                INSERT INTO ods_lingxing_ctu_inventory_detail
                (pull_month,wid,warehouse_name,group_code,sku,product_id,
                 product_total,stock_price,average_age,over_30_qty,
                 over_30_cost,stock_age_list,raw_json,sync_batch_id,pulled_at)
                VALUES
                (%(pull_month)s,%(wid)s,%(warehouse_name)s,%(group_code)s,
                 %(sku)s,%(product_id)s,%(product_total)s,%(stock_price)s,
                 %(average_age)s,%(over_30_qty)s,%(over_30_cost)s,
                 %(stock_age_list)s,%(raw_json)s,%(sync_batch_id)s,%(pulled_at)s)
                """,
                rows,
            )
        if groups:
            cur.executemany(
                """
                INSERT INTO dws_ctu_inventory_age_group
                (pull_month,group_code,warehouse_count,source_row_count,
                 over_30_qty,over_30_cost,pulled_at)
                VALUES
                (%(pull_month)s,%(group_code)s,%(warehouse_count)s,
                 %(source_row_count)s,%(over_30_qty)s,%(over_30_cost)s,
                 %(pulled_at)s)
                """,
                groups,
            )
    return {
        "ctu_ods_old_rows": old_ods_rows,
        "ctu_ods_deleted_rows": old_ods_rows,
        "ctu_ods_inserted_rows": len(rows),
        "ctu_group_old_rows": old_group_rows,
        "ctu_group_rows": len(groups),
    }


def ctu_over_30_costs(pull_month: str) -> dict[str, Decimal]:
    return {code: row['ctu_over_30_cost'] for code, row in ctu_group_metrics(pull_month).items() if code != '_TOTAL'}


def ctu_ebay_owner_cost_rows(pull_month: str) -> list[dict[str, Any]]:
    """仅eBay成都仓成本明细；空快照返回[]，有快照但无成本返回NULL占位行。"""
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.sku,d.over_30_cost
            FROM dws_ctu_inventory_age_group g
            LEFT JOIN ods_lingxing_ctu_inventory_detail d
              ON d.pull_month=g.pull_month AND d.group_code=g.group_code
             AND d.over_30_cost<>0
            WHERE g.pull_month=%s AND g.group_code='EBAY-1'
            """,
            (pull_month,),
        )
        return list(cur.fetchall())


def ctu_inventory_age_details(month: str | None) -> dict[str, Any]:
    """Return current-batch CTU SKU rows that actually contain over-30 stock."""
    with db_connection() as conn, conn.cursor() as cur:
        if not month:
            cur.execute(
                "SELECT MAX(pull_month) m FROM ods_lingxing_ctu_inventory_detail"
            )
            month = cur.fetchone()["m"]
        if not month:
            return {"pull_month": None, "items": []}
        cur.execute(
            """
            SELECT pull_month,group_code,wid,warehouse_name,sku,product_id,
                   product_total,stock_price,average_age,over_30_qty,
                   over_30_cost,stock_age_list,pulled_at,sync_batch_id
            FROM ods_lingxing_ctu_inventory_detail
            WHERE pull_month=%s AND over_30_qty>0
            ORDER BY FIELD(group_code,'EBAY-1','EU','US1','US2','US3'),
                     wid,sku,product_id,id
            """,
            (month,),
        )
        return {"pull_month": month, "items": list(cur.fetchall())}


def ctu_inventory_age_summary(month: str | None) -> dict[str, Any]:
    return ctu_group_metrics(month).get('_TOTAL', dict(ctu_over_30_qty=None,ctu_over_30_cost=None,ctu_over_30_sku_count=None))


def _metric_source_query(month: str, group_code: str | None = None, *, include_previous=True):
    """Use existing five-band AMZ details and exact eBay age days, without writes.

    Keep SKU and attribution identities until the final aggregation. Stored eBay
    costs intentionally remain unchanged (no multiplication by inventory qty).
    """
    selected = (month, previous_month(month)) if include_previous else (month, month)
    queries, params = [], []
    if group_code != 'EBAY-1':
        named = [f'COALESCE(inventory_{b}_{suffix},0) AS inventory_{b}_{suffix}' for b in BUCKETS for suffix in ('qty','cost')]
        for suffix in ('qty', 'cost'):
            named += ['(' + '+'.join(f'COALESCE(inventory_{b}_{suffix},0)' for b in BUCKETS[2:]) + f') AS inventory_181_plus_{suffix}',
                      '(' + '+'.join(f'COALESCE(inventory_{b}_{suffix},0)' for b in BUCKETS) + f') AS total_inventory_{suffix}']
        queries.append(f"""
            SELECT pull_month,'AMZ' AS platform_code,group_code,sid,store_name,warehouse_name,
                   COALESCE(NULLIF(TRIM(sku),''),seller_sku) AS sku,
                   NULL AS source_product_sku,NULL AS warehouse_code,1 AS source_row_count,pulled_at,
                   {','.join(named)}
            FROM dwd_amz_fba_inventory_monthly_snapshot
            WHERE pull_month IN (%s,%s)
            """ + (' AND group_code=%s' if group_code else ''))
        params.extend(selected)
        if group_code: params.append(group_code)
    if group_code in (None, 'EBAY-1'):
        conditions = {
            '0_90': "(warehouse_age_days BETWEEN 0 AND 90 OR (warehouse_age_days IS NULL AND inventory_age_bucket='0_90'))",
            '91_180': "(warehouse_age_days BETWEEN 91 AND 180 OR (warehouse_age_days IS NULL AND inventory_age_bucket='91_180'))",
            '181_270': 'warehouse_age_days BETWEEN 181 AND 270',
            '271_365': 'warehouse_age_days BETWEEN 271 AND 365',
            '365_plus': 'warehouse_age_days>365',
            '181_plus': "(warehouse_age_days>180 OR (warehouse_age_days IS NULL AND inventory_age_bucket='181_PLUS'))",
        }
        named = [f'CASE WHEN {conditions[b]} THEN COALESCE({source},0) ELSE 0 END AS inventory_{b}_{suffix}'
                 for b in (*BUCKETS, '181_plus') for suffix, source in [('qty','inventory_quantity'),('cost','inventory_age_cost')]]
        # Match the column order of the AMZ projection (legacy qty/cost then totals).
        amz_order = [f'inventory_{b}_{suffix}' for b in BUCKETS for suffix in ('qty','cost')] + [
            'inventory_181_plus_qty','total_inventory_qty','inventory_181_plus_cost','total_inventory_cost']
        expressions = {expr.rsplit(' AS ',1)[1]: expr for expr in named}
        expressions.update(total_inventory_qty='COALESCE(inventory_quantity,0) AS total_inventory_qty',
                           total_inventory_cost='COALESCE(inventory_age_cost,0) AS total_inventory_cost')
        queries.append(f"""
            SELECT pull_month,'EBAY' AS platform_code,'EBAY-1' AS group_code,NULL AS sid,NULL AS store_name,warehouse_name,
                   COALESCE(NULLIF(TRIM(sku),''),source_product_sku) AS sku,
                   source_product_sku,warehouse_code,1 AS source_row_count,pulled_at,
                   {','.join(expressions[field] for field in amz_order)}
            FROM dwd_ebay_inventory_age_cost_snapshot WHERE pull_month IN (%s,%s)
            """)
        params.extend(selected)
    return ' UNION ALL '.join(queries), tuple(params)


def metric_source_rows(month: str, group_code: str | None = None, *, include_previous=True) -> list[dict]:
    sql, params = _metric_source_query(month, group_code, include_previous=include_previous)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _group_metric_rows(month: str) -> list[dict]:
    """Return month/group totals; deduplicate net-positive middle codes in SQL.

    The company scope regroups product middle codes across all groups, never sums group
    counts. Costs and negative stock adjustments are summed without repricing.
    """
    source, params = _metric_source_query(month)
    sku = 'product_key'
    core = "UPPER(TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(core_sku,'-',2),'-',-1)))"
    sums = ','.join(f'SUM({field}) AS {field}' for field in FIELDS)
    counts = ','.join(f"SUM(CASE WHEN sku<>'' AND {prefix}_qty>0 THEN 1 ELSE 0 END) AS {prefix}_sku_count"
                      for prefix in PREFIXES)
    mismatch = ' OR '.join('(' + '+'.join(f'inventory_{b}_{suffix}' for b in BUCKETS)
                          + f')<>total_inventory_{suffix}' for suffix in ('qty', 'cost'))
    quality = f"""SUM(source_row_count) AS source_row_count,
                  SUM(CASE WHEN {sku}='' AND total_inventory_qty>0 THEN 1 ELSE 0 END) AS missing_sku_rows,
                  SUM(CASE WHEN {mismatch} THEN 1 ELSE 0 END) AS unbucketed_rows,
                  MAX(pulled_at) AS pulled_at"""
    sql = f"""
        WITH raw_source AS ({source}),
        product_parts AS (
            SELECT raw_source.*,
                   CASE WHEN UPPER(TRIM(SUBSTRING_INDEX(sku,'-',1))) REGEXP '^[0-9]+PC$'
                        THEN SUBSTRING(sku,INSTR(sku,'-')+1) ELSE sku END AS core_sku
            FROM raw_source
        ), source AS (
            SELECT product_parts.*,
                   CASE WHEN INSTR(core_sku,'-')>0 AND TRIM(SUBSTRING_INDEX(core_sku,'-',1))<>''
                         AND {core} REGEXP '^[A-Z0-9]{{1,64}}$' AND {core} REGEXP '[0-9]'
                        THEN {core} ELSE '' END AS product_key
            FROM product_parts
        ),
        sku_totals AS (
            SELECT pull_month,group_code,{sku} AS sku,{sums},{quality}
            FROM source GROUP BY pull_month,group_code,{sku}
            UNION ALL
            SELECT pull_month,'_TOTAL' AS group_code,{sku} AS sku,{sums},{quality}
            FROM source GROUP BY pull_month,{sku}
        ), metrics AS (
            SELECT pull_month,group_code,{sums},{counts},
                   SUM(source_row_count) AS source_row_count,
                   SUM(missing_sku_rows) AS missing_sku_rows,
                   SUM(unbucketed_rows) AS unbucketed_rows,MAX(pulled_at) AS pulled_at
            FROM sku_totals GROUP BY pull_month,group_code
        ), shops AS (
            SELECT pull_month,group_code,
                   COUNT(DISTINCT CASE WHEN platform_code='EBAY' THEN COALESCE(warehouse_code,'__UNKNOWN__')
                         WHEN COALESCE(sid,'0')<>'0' THEN sid END) AS shop_count
            FROM source GROUP BY pull_month,group_code
        )
        SELECT m.*,COALESCE(s.shop_count,0) AS shop_count FROM metrics m LEFT JOIN shops s
          ON s.pull_month=m.pull_month AND s.group_code=m.group_code
    """
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def ctu_group_metrics(month: str) -> dict[str, dict]:
    """Sum original CTU detail once per group, keeping zero-stock snapshot groups."""
    if not month:
        return {}
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT g.group_code,d.sku,d.over_30_qty,d.over_30_cost
            FROM dws_ctu_inventory_age_group g LEFT JOIN ods_lingxing_ctu_inventory_detail d
              ON d.pull_month=g.pull_month AND d.group_code=g.group_code
            WHERE g.pull_month=%s
            """, (month,))
        rows = list(cur.fetchall())
    grouped = {}
    for row in rows:
        grouped.setdefault(row['group_code'], []).append(row)
    result = {}
    for code, items in grouped.items():
        values = aggregate([{'sku': r['sku'], 'total_inventory_qty': r['over_30_qty'],
                             'total_inventory_cost': r['over_30_cost']} for r in items])
        result[code] = {'ctu_over_30_qty': values['total_inventory_qty'],
                        'ctu_over_30_cost': values['total_inventory_cost'],
                        'ctu_over_30_sku_count': values['total_inventory_sku_count']}
    values = aggregate([{'sku': r['sku'], 'total_inventory_qty': r['over_30_qty'],
                         'total_inventory_cost': r['over_30_cost']} for r in rows])
    if rows:
        result['_TOTAL'] = {'ctu_over_30_qty': values['total_inventory_qty'],
                            'ctu_over_30_cost': values['total_inventory_cost'],
                            'ctu_over_30_sku_count': values['total_inventory_sku_count']}
    return result


def list_groups(month: str | None) -> dict:
    if not month:
        latest = months(1)
        month = latest[0]['pull_month'] if latest else None
    if not month:
        return {'pull_month': None, 'items': [], 'total': 0, 'summary': {}}
    source = _group_metric_rows(month)
    ctu = ctu_group_metrics(month)
    current = {r['group_code']: r for r in source if r['pull_month'] == month}
    previous = {r['group_code']: r for r in source if r['pull_month'] == previous_month(month)}
    has_previous = bool(previous)
    def metrics(code):
        row = dict(current.get(code) or aggregate([]))
        attach_comparison(row, previous.get(code) or aggregate([]), has_previous)
        return row
    items = []
    for code in (current.keys() | previous.keys()) - {'_TOTAL'}:
        row = metrics(code)
        region = 'EBAY' if code == 'EBAY-1' else 'EU' if code == 'EU' else 'US'
        row.update(pull_month=month, group_code=code, group_name=code, region_code=region,
                   region_name={'EBAY':'eBay组','EU':'欧洲组','US':'美国组'}[region],
                   shop_count=row.get('shop_count', 0), pulled_at=row.get('pulled_at'),
                   previous_cost_month=previous_month(month) if has_previous else None,
                   brands=[], previous_brands=[])
        row.update(ctu.get('US3' if code in ('US2-MJ','US1-ZXY') else code,
                           dict(ctu_over_30_qty=None,ctu_over_30_cost=None,ctu_over_30_sku_count=None)))
        items.append(row)
    items.sort(key=lambda row: GROUP_CODES.index(row['group_code']) if row['group_code'] in GROUP_CODES else 99)
    totals = metrics('_TOTAL')
    totals.pop('group_code', None)
    totals.update(ctu.get('_TOTAL', dict(ctu_over_30_qty=None,ctu_over_30_cost=None,ctu_over_30_sku_count=None)))
    totals.update(pull_month=month,group_count=len(items),shop_count=sum(row['shop_count'] for row in items),
                  pulled_at=max((row['pulled_at'] for row in items if row['pulled_at']),default=None))
    return {'pull_month': month, 'items': items, 'total': len(items), 'summary': totals}


def summary(month: str | None) -> dict:
    return list_groups(month)['summary']


def list_site_dimensions(month: str) -> dict[str, Any]:
    source = metric_source_rows(month, 'EBAY-1')
    def identity(row):
        code = str(row.get('warehouse_code') or '').strip().upper()
        site = {'USEA':'US','USWE':'US','US':'US','UK':'UK','GB':'UK','DE':'DE','CZ':'DE'}.get(code, '未识别仓库：'+(code or '未知'))
        return site, site
    items = compare(source, month, identity)
    return {'pull_month':month,'group_code':'EBAY-1','dimension':'SITE','items':items,
            'total':len(items),'summary':total_metrics(source,month)}


def drilldown_source_rows(month: str, group_code: str) -> list[dict[str, Any]]:
    return metric_source_rows(month, group_code)


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
