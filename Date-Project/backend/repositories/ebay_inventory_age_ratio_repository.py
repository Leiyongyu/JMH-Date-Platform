"""Daily frozen age valuations. Reads never rebuild from current sources."""
import json

from backend.database import db_connection
from backend.config import settings

TABLE = "ebay_inventory_age_ratio_snapshot"


def load_source(month):
    """Read inventory and the full candidate catalog in one consistent transaction.

    Matching is performed once per inventory row, not with a many-to-many join
    that would multiply warehouse quantities when a middle code has variants.
    """
    database = (settings.shop_source_database.strip() or "jmh_data_platform").replace("`", "``")
    with db_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                conn.begin()
                cur.execute(f"""
                    SELECT id AS source_inventory_age_id, snapshot_month AS pull_month,
                           sync_batch_id AS source_goodcang_batch_id,
                           product_sku AS source_product_sku, warehouse_code,
                           warehouse_desc AS warehouse_name, iba_quantity AS inventory_quantity,
                           warehouse_age AS warehouse_age_days, pulled_at AS source_pulled_at
                    FROM `{database}`.ods_goodcang_inventory_age_latest ORDER BY id
                """)
                inventory = list(cur.fetchall())
                cur.execute(f"""
                    SELECT p.sku,p.cg_price,p.sync_batch_id AS source_product_batch_id,sp.step_price
                    FROM `{database}`.ods_lingxing_product_procurement_monthly p
                    LEFT JOIN (
                        SELECT sku,MAX(NULLIF(price,0)) AS step_price
                        FROM `{database}`.ods_lingxing_product_supplier_step_price_monthly
                        WHERE snapshot_month=%s GROUP BY sku
                    ) sp ON sp.sku=p.sku
                    WHERE p.snapshot_month=%s ORDER BY p.sku
                """, (month, month))
                products = list(cur.fetchall())
                cur.execute(f"""
                    SELECT sku,country_code,MAX(transport_cost) AS transport_cost
                    FROM `{database}`.ods_lingxing_product_transport_cost_monthly
                    WHERE snapshot_month=%s AND country_code IN ('US','UK','DE','CZ')
                    GROUP BY sku,country_code
                """, (month,))
                transport = {}
                for row in cur.fetchall():
                    transport.setdefault(row["sku"], {})[row["country_code"]] = row["transport_cost"]
                for product in products:
                    product["transport_costs"] = transport.get(product["sku"], {})
            conn.commit()
            return inventory, products
        except Exception:
            conn.rollback()
            raise


def save_snapshot(report):
    # Both dimensions and diagnostics are published atomically in one document.
    with db_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {TABLE} (stat_date,generated_at,source_batch_id,report_json)
                    VALUES (%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE generated_at=VALUES(generated_at),
                        source_batch_id=VALUES(source_batch_id),report_json=VALUES(report_json)
                """, (report["stat_date"], report["generated_at"], report["source_batch_id"],
                      json.dumps(report, ensure_ascii=False, allow_nan=False)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def read_range(start_date, end_date):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT stat_date,report_json FROM {TABLE} WHERE stat_date BETWEEN %s AND %s ORDER BY stat_date DESC",
                    (start_date, end_date))
        snapshots = [(str(row['stat_date']), json.loads(row['report_json'])) for row in cur.fetchall()]
    return {
        "start_date": start_date, "end_date": end_date,
        "snapshot_dates": [day for day, _ in snapshots],
        "owners": [{**row, "stat_date": day} for day, report in snapshots for row in report.get('owners', [])],
        "sites": [{**row, "stat_date": day} for day, report in snapshots for row in report.get('sites', [])],
        "warnings": [f"{day}：{warning}" for day, report in snapshots for warning in report.get('warnings', [])],
    }


def read_snapshot(stat_date=None):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT stat_date FROM {TABLE} ORDER BY stat_date DESC")
        dates = [str(row["stat_date"]) for row in cur.fetchall()]
        selected = stat_date if stat_date and stat_date != "latest" else (dates[0] if dates else None)
        cur.execute(f"SELECT report_json FROM {TABLE} WHERE stat_date=%s", (selected,))
        row = cur.fetchone()
        report = json.loads(row["report_json"]) if row else {
            "stat_date": selected, "owners": [], "sites": [], "warnings": [],
        }
        return {**report, "available_dates": dates}
