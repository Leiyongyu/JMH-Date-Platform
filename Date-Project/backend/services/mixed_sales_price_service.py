"""SQL native-currency min/max comparison; no currency conversion or fuzzy SKU join."""
import re

from backend.database import db_connection
from backend.repositories.ebay_mixed_sales_price_repository import TABLE
from backend.services.ebay_order_product_key import product_sku_sql
from backend.services.mixed_sales_sql import amazon_sources, canonical_site, site_sql


def list_price_ranges(*, sku, site=None, stat_month=None, page=1, page_size=20):
    # The SKU has already been normalized in the parent platform's main list.
    sku = str(sku or '').strip().upper()
    if not sku:
        raise ValueError('请选择产品SKU')
    if stat_month and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', stat_month):
        raise ValueError('售价月份无效')
    code = canonical_site(site) if site else None
    if site and code is None:
        raise ValueError('无效站点')
    page, size = max(int(page), 1), min(max(int(page_size), 1), 200)
    with db_connection() as connection, connection.cursor() as cursor:
        connection.begin()
        cursor.execute(f"SELECT DISTINCT stat_month FROM {TABLE} WHERE record_type='SHOP' ORDER BY stat_month DESC")
        months = [r['stat_month'] for r in cursor.fetchall()]
        month = stat_month or (months[0] if months else None)
        # Filter before grouping, but never give a parent price to variant SKUs.
        ctes = f'''WITH {amazon_sources(exact_sku=True)}, ebay_quotes AS (
            SELECT t.normalized_sku sku,{site_sql('t.site')} site,
                UPPER(TRIM(t.currency)) COLLATE utf8mb4_unicode_ci currency,t.current_price price,t.pulled_at pulledAt
            FROM {TABLE} t WHERE t.stat_month=%s AND t.record_type='ITEM'
                AND t.normalized_sku=%s AND COALESCE(JSON_LENGTH(t.variations_json),0)=0
            UNION ALL
            SELECT ({product_sku_sql('v.sku')}) COLLATE utf8mb4_unicode_ci,{site_sql('t.site')},
                UPPER(TRIM(v.currency)) COLLATE utf8mb4_unicode_ci,v.price COLLATE utf8mb4_unicode_ci,t.pulled_at
            FROM {TABLE} t JOIN JSON_TABLE(t.variations_json,'$[*]' COLUMNS(
                sku VARCHAR(255) PATH '$.sku',price VARCHAR(128) PATH '$.price.value',
                currency VARCHAR(16) PATH '$.price.currency')) v ON TRUE
            WHERE t.stat_month=%s AND t.record_type='ITEM' AND ({product_sku_sql('v.sku')})=%s
        ), quotes AS (
            SELECT 'AMZ' platform,site,NULLIF(currency,'') currency,
                CAST(salePrice AS DECIMAL(30,10)) price,listingSyncTime syncTime FROM channels WHERE sku=%s
            UNION ALL
            SELECT 'EBAY',site,NULLIF(currency,''),
                CASE WHEN TRIM(price) REGEXP '^[0-9]+([.][0-9]+)?$' THEN CAST(price AS DECIMAL(30,10)) END,pulledAt
                FROM ebay_quotes
        ), keyed AS (
            SELECT *,CASE WHEN site IS NULL OR currency IS NULL THEN platform ELSE '' END unmatchedPlatform FROM quotes
        ), ranges AS (
            SELECT site,currency,unmatchedPlatform,
                MIN(CASE WHEN platform='AMZ' THEN price END) amzMinPrice,
                MAX(CASE WHEN platform='AMZ' THEN price END) amzMaxPrice,
                MIN(CASE WHEN platform='EBAY' THEN price END) ebayMinPrice,
                MAX(CASE WHEN platform='EBAY' THEN price END) ebayMaxPrice,
                MAX(CASE WHEN platform='AMZ' THEN syncTime END) amzSyncTime,
                MAX(CASE WHEN platform='EBAY' THEN syncTime END) ebaySyncTime
            FROM keyed GROUP BY site,currency,unmatchedPlatform
        )'''
        args = [sku, month, sku, month, sku, sku]
        where = ' WHERE site=%s' if code else ''
        if code:
            args.append(code)
        cursor.execute(ctes + ' SELECT /*+ MAX_EXECUTION_TIME(15000) */ * FROM ranges' + where
                       + ' ORDER BY site IS NULL,site,currency,unmatchedPlatform', args)
        all_rows = list(cursor.fetchall())
        total = len(all_rows)
        rows = all_rows[(page-1)*size:page*size]
    return dict(items=rows,total=total,months=months,statMonth=month,pageNum=page,pageSize=size)
