from backend.config import settings
from backend.database import db_connection
from backend.repositories.performance_repository import get_owner_rules


def load_source(rule_month: str) -> dict:
    database = (settings.shop_source_database.strip() or "jmh_data_platform").replace("`", "``")
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        try:
            cursor.execute(f"""
                SELECT id,status,start_time,end_time FROM `{database}`.data_sync_log
                WHERE sync_type='ebay_listing' AND status<>'SKIPPED'
                ORDER BY id DESC LIMIT 1
            """)
            sync = cursor.fetchone()
            rules = get_owner_rules(connection, "ebay", rule_month)
            cursor.execute(f"""
                SELECT store_id,msku,local_sku,sync_time
                FROM `{database}`.ebay_product_listing
                WHERE listing_status=1
            """)
            return {"rows": list(cursor.fetchall()), "rules": rules, "sync": sync}
        finally:
            connection.rollback()
