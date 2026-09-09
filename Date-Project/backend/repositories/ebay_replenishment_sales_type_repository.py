"""补货2.0独立人工销售类型；不随订单导入、刷新或月份切换重建。"""
from pymysql.err import ProgrammingError

from backend.database import db_connection
from backend.repositories.ebay_replenishment_v2_repository import _source_database

TABLE_NAME = "ebay_replenishment_v2_sales_type"
MIGRATION_MESSAGE = "销售类型配置表未部署，请先执行09_补货2.0销售类型.sql"


def missing_table(error):
    return isinstance(error, ProgrammingError) and error.args[0] == 1146 and TABLE_NAME in str(error).lower()


def join_sql():
    return f"""LEFT JOIN `{_source_database()}`.{TABLE_NAME} sales_type
        ON sales_type.site=base.site COLLATE utf8mb4_unicode_ci
       AND sales_type.sku=base.sku COLLATE utf8mb4_unicode_ci"""


def save(site, sku, sales_type, operator):
    query = f"""INSERT INTO `{_source_database()}`.{TABLE_NAME}
        (site,sku,sales_type,update_by,create_time,update_time)
        VALUES (%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE sales_type=VALUES(sales_type),
            update_by=VALUES(update_by),update_time=NOW()"""
    with db_connection() as connection, connection.cursor() as cursor:
        try:
            cursor.execute(
                """SELECT 1 FROM dwd_ebay_sku_analysis_order
                   WHERE site_name=%s AND inventory_sku=%s LIMIT 1""", (site, sku))
            if not cursor.fetchone():
                raise ValueError("没有找到该站点和完整SKU对应的订单数据")
            cursor.execute(query, (site, sku, sales_type, operator))
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if missing_table(exc):
                raise ValueError(MIGRATION_MESSAGE) from exc
            raise
