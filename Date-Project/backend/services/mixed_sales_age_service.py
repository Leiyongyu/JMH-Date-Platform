"""Read existing age snapshots, aggregate in SQL, and never alter inventory totals."""
from contextlib import contextmanager

from backend.database import db_connection
from backend.repositories.ebay_replenishment_v2_repository import _source_database
from backend.services.ebay_order_product_key import product_sku_sql
from backend.services.mixed_sales_sql import canonical_site

AMZ_BUCKETS = {1: '0–90天', 2: '91–180天', 3: '181–270天', 4: '271–365天', 5: '365天以上'}
AGE_OPERATORS = {'gt': '>', 'gte': '>=', 'eq': '=', 'lte': '<=', 'lt': '<'}


def validate_age_filter(platform, age_bucket=None, age_operator=None, age_days=None):
    if age_bucket is not None and (platform != 'amz' or age_bucket not in AMZ_BUCKETS):
        raise ValueError('请选择有效的Amazon库龄区间')
    if age_operator is not None or age_days is not None:
        if (platform != 'ebay' or age_operator not in AGE_OPERATORS
                or not isinstance(age_days, int) or isinstance(age_days, bool)
                or age_days < 0 or age_days > 2147483647):
            raise ValueError('eBay库龄筛选需要有效的比较条件和非负整数天数')


def age_filter_sql(platform, *, age_bucket=None, age_operator=None, age_days=None, sid=None, site=None):
    """Filter SKU rows, keeping their inventory/sales aggregates unchanged."""
    validate_age_filter(platform, age_bucket, age_operator, age_days)
    if age_bucket is None and age_operator is None:
        return None, []
    sql, args = age_query(platform, sid=sid, site=site)
    if platform == 'amz':
        # Match a real shop in this SKU's channels, not an orphan age SID.
        return f'''EXISTS (SELECT 1 FROM ({sql}) age_match
            JOIN channels age_channel ON age_channel.sku=age_match.sku COLLATE utf8mb4_unicode_ci
                AND CAST(age_channel.sid AS CHAR) COLLATE utf8mb4_unicode_ci=age_match.sid
            WHERE age_match.sku=metrics.sku COLLATE utf8mb4_unicode_ci AND age_match.ageValue=%s)''', [*args, age_bucket]
    return f'''metrics.sku COLLATE utf8mb4_unicode_ci IN (
        SELECT sku FROM ({sql}) age_match GROUP BY sku
        HAVING MAX(ageValue) {AGE_OPERATORS[age_operator]} %s)''', [*args, age_days]


@contextmanager
def _cursor(existing):
    if existing is not None:
        yield existing
    else:
        with db_connection() as connection, connection.cursor() as cursor:
            yield cursor


def attach_ages(items, *, platform, sid=None, site=None, details=False, cursor=None):
    if not items:
        return
    if platform == 'amz' and not details:
        # Amazon age always belongs to a shop, never a cross-shop summary.
        for item in items:
            item['inventoryAge'] = None
        return
    skus = sorted({str(r['sku']).strip().upper() for r in items})
    sql, args = age_query(platform, skus=skus, sid=sid, site=site)
    with _cursor(cursor) as cur:
        cur.execute(sql, args)
        sources = cur.fetchall()
    grouped = {}
    for source in sources:
        value = source.get('ageValue')
        if value is None:
            continue
        dimension = (str(source.get('sid')) if platform == 'amz' else source.get('site')) if details else None
        key = source['sku'], dimension
        if key not in grouped or value > grouped[key]['ageValue']:
            grouped[key] = source
    for item in items:
        dimension = (str(item.get('sid')) if platform == 'amz' else item.get('site')) if details else None
        source = grouped.get((str(item['sku']).strip().upper(), dimension), {})
        value = source.get('ageValue')
        item['inventoryAge'] = (AMZ_BUCKETS[int(value)] if platform == 'amz' else f'{int(value)}天') if value is not None else None
        item['inventoryAgeSourceMonth'] = source.get('sourceMonth')
        item['inventoryAgeUpdatedAt'] = str(source['updatedAt']) if source.get('updatedAt') else None
        if platform == 'amz':
            item['inventoryAgeShared'] = bool(source.get('sharedAge'))
            item['inventoryAgeNameMatched'] = bool(source.get('nameMatched'))


def age_query(platform, *, skus=None, sid=None, site=None):
    """Shared age aggregation for display and SQL filtering before pagination."""
    placeholders = ','.join(['%s'] * len(skus or []))
    args = list(skus or [])
    if platform == 'amz':
        # These fields contain inventory QUANTITIES, not exact ages in days.
        # Always use the latest overall snapshot, not an older month per SKU.
        db = _source_database()
        sql = f'''WITH age_rows AS (
            SELECT UPPER(TRIM(sku)) COLLATE utf8mb4_unicode_ci sku,
                TRIM(COALESCE(CAST(sid AS CHAR),'')) COLLATE utf8mb4_unicode_ci sid,
                seller_group_name,share_type,pull_month,pulled_at,
                CASE WHEN inv_age_365_plus_days>0 THEN 5
                     WHEN inv_age_271_to_365_days>0 THEN 4
                     WHEN inv_age_181_to_270_days>0 THEN 3
                     WHEN inv_age_91_to_180_days>0 THEN 2
                     WHEN inv_age_0_to_90_days>0 THEN 1 END ageValue
            FROM ods_lingxing_amz_fba_inventory_raw
            WHERE pull_month=(SELECT MAX(pull_month) FROM ods_lingxing_amz_fba_inventory_raw)
              {"AND UPPER(TRIM(sku)) IN (" + placeholders + ")" if skus is not None else ""}
        ), shop_names AS (
            SELECT TRIM(store_name) COLLATE utf8mb4_unicode_ci storeName,
                   MIN(CAST(sid AS CHAR)) COLLATE utf8mb4_unicode_ci sid
            FROM `{db}`.shop_list WHERE platform_code='10001'
              AND sid IS NOT NULL AND sid>0 AND NULLIF(TRIM(store_name),'') IS NOT NULL
            GROUP BY TRIM(store_name) COLLATE utf8mb4_unicode_ci
            HAVING COUNT(DISTINCT sid)=1
        ), resolved AS (
            SELECT sku,sid,ageValue,pull_month,pulled_at,
                   CASE WHEN share_type IN (1,2) THEN 1 ELSE 0 END isShared,0 nameMatched
            FROM age_rows WHERE sid NOT IN ('','0')
            UNION ALL
            SELECT a.sku,s.sid,a.ageValue,a.pull_month,a.pulled_at,
                   CASE WHEN a.share_type IN (1,2) OR LOCATE(',',a.seller_group_name)>0 THEN 1 ELSE 0 END isShared,
                   1 nameMatched
            FROM age_rows a
            JOIN JSON_TABLE(CONCAT('[',REPLACE(JSON_QUOTE(COALESCE(a.seller_group_name,'')),',','","'),']'),
                            '$[*]' COLUMNS(storeName VARCHAR(512) PATH '$')) names ON TRUE
            JOIN shop_names s ON s.storeName=TRIM(names.storeName) COLLATE utf8mb4_unicode_ci
            WHERE a.sid IN ('','0')
        ) SELECT /*+ MAX_EXECUTION_TIME(15000) */ sku,sid,MAX(ageValue) ageValue,
            MAX(pull_month) sourceMonth,MAX(pulled_at) updatedAt,
            MAX(isShared) sharedAge,MAX(nameMatched) nameMatched
          FROM resolved WHERE ageValue IS NOT NULL {"AND sid=%s" if sid is not None else ''}
          GROUP BY sku,sid'''
        if sid is not None:
            args.append(str(sid))
    elif platform == 'ebay':
        db = _source_database()
        sku_expr = product_sku_sql('product_sku')
        product_expr = product_sku_sql('sku')
        sql = f'''WITH product_keys AS (
            SELECT ({product_expr}) COLLATE utf8mb4_unicode_ci sku
            FROM `{db}`.ods_lingxing_product_procurement_monthly
            WHERE snapshot_month=(SELECT MAX(snapshot_month)
                FROM `{db}`.ods_lingxing_product_procurement_monthly)
        ), unique_products AS (
            SELECT SUBSTRING(sku,LOCATE('-',sku)+1) skuTail,MAX(sku) sku
            FROM product_keys WHERE sku NOT LIKE 'JMH-%%' AND LOCATE('-',sku)>0
            GROUP BY SUBSTRING(sku,LOCATE('-',sku)+1)
            HAVING COUNT(DISTINCT sku)=1
        ), raw_ages AS (
            SELECT ({sku_expr}) sku,
                CASE WHEN UPPER(TRIM(warehouse_code)) IN ('DE','CZ','IT') THEN 'DE'
                     WHEN UPPER(TRIM(warehouse_code)) IN ('UK','GB') THEN 'UK'
                     WHEN UPPER(TRIM(warehouse_code))='FR' THEN 'FR'
                     WHEN UPPER(TRIM(warehouse_code)) LIKE 'US%%' THEN 'US' END site,
                warehouse_age,iba_quantity,pulled_at,
                TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json,'$.warehouse_age'))) rawAge
            FROM `{db}`.ods_goodcang_inventory_age_latest
        ), age_rows AS (
            SELECT COALESCE(p.sku,a.sku COLLATE utf8mb4_unicode_ci) sku,
                   a.site,a.warehouse_age,a.iba_quantity,a.pulled_at,a.rawAge
            FROM raw_ages a LEFT JOIN unique_products p
              ON a.sku LIKE 'JMH-%%'
             AND SUBSTRING(a.sku,5) COLLATE utf8mb4_unicode_ci=p.skuTail
        ) SELECT /*+ MAX_EXECUTION_TIME(15000) */ sku,site,
            MAX(warehouse_age) ageValue,MAX(pulled_at) updatedAt
          FROM age_rows WHERE site IS NOT NULL {"AND sku IN (" + placeholders + ")" if skus is not None else ""}
            AND iba_quantity>0 AND warehouse_age>=0
            AND rawAge REGEXP '^[0-9]{{1,10}}$'
            AND CAST(rawAge AS DECIMAL(30,0))=warehouse_age
            {"AND site=%s" if site else ''}
          GROUP BY sku,site'''
        if site:
            args.append(canonical_site(site))
    else:
        raise ValueError('无效平台')
    return sql, args
