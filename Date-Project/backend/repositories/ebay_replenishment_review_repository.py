"""按站点+归并SKU保存备注及运营确认，独立于滚动销量。"""
from pymysql.err import ProgrammingError

from backend.database import db_connection
from backend.repositories.ebay_replenishment_v2_repository import _source_database
from backend.services.ebay_order_product_key import product_orders_cte

TABLE = "ebay_replenishment_v2_review"
MIGRATION_MESSAGE = "运营/开发备注尚未部署，请执行20261015_ebay_replenishment_v2_review.sql"
DEFAULTS = {"operations_note": "", "development_note": "", "operations_version": 0,
            "development_version": 0, "operations_confirmed": False,
            "operations_confirmed_by": None, "operations_confirmed_at": None}


def missing_table(error):
    return isinstance(error, ProgrammingError) and error.args[0] == 1146 and TABLE in str(error).lower()


def join_sql():
    return f"""LEFT JOIN `{_source_database()}`.{TABLE} review
        ON review.site=base.site COLLATE utf8mb4_unicode_ci
       AND review.sku=base.sku COLLATE utf8mb4_unicode_ci"""


def select_sql():
    return ','.join(f'review.{key}' for key in DEFAULTS)


def empty_select_sql():
    return ','.join(f'NULL AS {key}' for key in DEFAULTS)


def note_presence_filters(operations_filled=None, development_filled=None):
    clauses, args = [], []
    for field, value in [('operations', operations_filled), ('development', development_filled)]:
        if value is None:
            continue
        if type(value) is not bool:
            raise ValueError('备注已填/未填筛选必须为布尔值')
        clauses.append(f"REGEXP_LIKE(COALESCE(review.{field}_note,''),'[^[:space:]]')=%s")
        args.append(int(value))
    return clauses, args


def review_values(row):
    result = {key: row.get(key) if row.get(key) is not None else value for key, value in DEFAULTS.items()}
    result['operations_confirmed'] = bool(result['operations_confirmed'])
    return result


def save(site, sku, field, text, expected_version, operator, *, confirm=False):
    # field is strictly validated by service; never interpolate arbitrary input.
    if field not in ('operations', 'development') or (confirm and field != 'operations'):
        raise ValueError('无效备注字段')
    table = f'`{_source_database()}`.{TABLE}'
    with db_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(f"WITH {product_orders_cte()} SELECT 1 FROM product_orders WHERE site_name=%s AND inventory_sku=%s LIMIT 1", (site, sku))
            if not cur.fetchone():
                raise ValueError('没有找到对应站点和SKU的订单数据')
            cur.execute(f"INSERT INTO {table}(site,sku) VALUES(%s,%s) ON DUPLICATE KEY UPDATE sku=sku", (site, sku))
            cur.execute(f"SELECT * FROM {table} WHERE site=%s AND sku=%s FOR UPDATE", (site, sku))
            row = cur.fetchone()
            if int(row[f'{field}_version']) != expected_version:
                raise ValueError('该备注或确认状态已被其他人修改，请刷新后再操作')
            if confirm:
                if not row['operations_confirmed']:
                    cur.execute(f"""UPDATE {table} SET operations_confirmed=1,
                        operations_confirmed_by=%s,operations_confirmed_at=NOW(),
                        operations_version=operations_version+1 WHERE site=%s AND sku=%s""", (operator, site, sku))
            elif row[f'{field}_note'] != text:
                reset = ',operations_confirmed=0,operations_confirmed_by=NULL,operations_confirmed_at=NULL' if field == 'operations' else ''
                cur.execute(f"""UPDATE {table} SET {field}_note=%s,{field}_version={field}_version+1,
                    {field}_update_by=%s,{field}_update_time=NOW(){reset} WHERE site=%s AND sku=%s""", (text, operator, site, sku))
            cur.execute(f"SELECT * FROM {table} WHERE site=%s AND sku=%s", (site, sku))
            result = review_values(cur.fetchone())
            conn.commit()
            return {'site': site, 'sku': sku, **result}
        except Exception as exc:
            conn.rollback()
            if missing_table(exc):
                raise ValueError(MIGRATION_MESSAGE) from exc
            raise
