from __future__ import annotations

import pymysql

from backend.config import settings
from backend.database import db_connection
from backend.parsers.performance_common import normalize_text
from backend.repositories.performance_repository import get_owner_rules


def load_source(rule_month: str) -> dict:
    """Read listings, matching rules and sync state in one read-only snapshot."""
    database = (settings.shop_source_database.strip() or "jmh_data_platform").replace("`", "``")
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        try:
            cursor.execute("""
                SELECT id, 'SUCCESS' AS status, pulled_at AS start_time,
                       published_at AS end_time, sync_batch_id
                FROM ods_lingxing_amz_listing_state WHERE id=1
            """)
            sync = cursor.fetchone()
            if not sync:
                return {"rows": [], "rules": {}, "sync": {"status": "NOT_INITIALIZED"}}
            rules = get_owner_rules(connection, "amazon", rule_month)
            # sid types differ across the source tables; SQL equality casts to
            # double and scans every shop for every listing (~4s locally).
            # Load the small shop dictionary once, no per-SKU queries.
            cursor.execute(f"""
                SELECT sid, store_name FROM `{database}`.shop_list
                WHERE platform_code='10001'
            """)
            shops = {}
            for shop in cursor.fetchall():
                sid = _sid(shop.get("sid"))
                name = normalize_text(shop.get("store_name"))
                if sid in shops and shops[sid] != name:
                    raise ValueError("AMZ店铺数据存在同sid不同店铺名称，请先核对店铺同步数据")
                shops[sid] = name
            cursor.execute("""
                SELECT pl.sid, pl.local_sku, pl.seller_sku, pl.pulled_at AS sync_time
                FROM ods_lingxing_amz_listing_latest pl
                WHERE pl.status=1 AND pl.is_delete=0
            """)
            rows = list(cursor.fetchall())
            for row in rows:
                row["store_name"] = shops.get(_sid(row.get("sid")))
            return {"rows": rows, "rules": rules, "sync": sync}
        except pymysql.err.ProgrammingError as exc:
            if exc.args and exc.args[0] == 1146:
                return {"rows": [], "rules": {}, "sync": {"status": "NOT_INITIALIZED"}}
            raise
        finally:
            connection.rollback()


def _sid(value) -> str:
    text = normalize_text(value)
    return str(int(text)) if text.isdecimal() else text
