"""Shared, request-independent SQL identifiers and site keys for mixed sales."""
from backend.repositories.ebay_replenishment_v2_repository import _source_database

SITE_ALIASES = {
    'US': ('US', '美国', 'USA', 'UNITED STATES'),
    'UK': ('UK', 'GB', '英国', 'UNITED KINGDOM'),
    'DE': ('DE', '德国', 'GERMANY'), 'FR': ('FR', '法国', 'FRANCE'),
    'IT': ('IT', '意大利', 'ITALY'), 'ES': ('ES', '西班牙', 'SPAIN'),
    'CA': ('CA', '加拿大', 'CANADA'), 'MX': ('MX', '墨西哥', 'MEXICO'),
    'NL': ('NL', '荷兰'), 'BE': ('BE', '比利时'), 'SE': ('SE', '瑞典'),
    'PL': ('PL', '波兰'), 'JP': ('JP', '日本'), 'AU': ('AU', '澳大利亚'),
    'CZ': ('CZ', '捷克'), 'AT': ('AT', '奥地利'), 'IE': ('IE', '爱尔兰'),
}


def canonical_site(value):
    value = str(value or '').strip().upper()
    return next((code for code, aliases in SITE_ALIASES.items() if value in aliases), None)


def site_sql(expression):
    # Only module constants and trusted SQL expressions are interpolated.
    cases = ' '.join("WHEN '" + alias + "' THEN '" + code + "'"
                     for code, aliases in SITE_ALIASES.items() for alias in aliases)
    return f"CASE UPPER(TRIM({expression})) {cases} ELSE NULL END"


def amazon_sources(*, exact_sku=False):
    # Shared node 1 is a regional rollup tagged with one representative SID.
    # Only node 2 (country) and node 3 (independent site) are valid site sales.
    db = f'`{_source_database()}`'
    site = site_sql('COALESCE(NULLIF(l.marketplace,\'\'),sh.countryCode)')
    requested = "wanted_sku AS (SELECT %s COLLATE utf8mb4_unicode_ci sku), " if exact_sku else ''
    warehouse_filter = "AND UPPER(TRIM(d.sku)) COLLATE utf8mb4_unicode_ci=(SELECT sku FROM wanted_sku)" if exact_sku else ''
    channel_filter = "AND UPPER(TRIM(local_sku)) COLLATE utf8mb4_unicode_ci=(SELECT sku FROM wanted_sku)" if exact_sku else ''
    sales_filter = "AND EXISTS (SELECT 1 FROM channel_keys k WHERE k.sid=r.sid AND k.seller_sku=r.msku)" if exact_sku else ''
    return requested + f"""warehouse_skus AS (
        SELECT UPPER(TRIM(d.sku)) COLLATE utf8mb4_unicode_ci sku,
            GROUP_CONCAT(DISTINCT COALESCE(NULLIF(w.name,''),CAST(d.wid AS CHAR)) ORDER BY w.name SEPARATOR '、') warehouseNames,
            MAX(d.sync_time) warehouseSyncTime
        FROM {db}.amz_warehouse_inventory_detail d LEFT JOIN {db}.warehouse w ON w.wid=d.wid
        WHERE NULLIF(TRIM(d.sku),'') IS NOT NULL {warehouse_filter}
        GROUP BY UPPER(TRIM(d.sku)) COLLATE utf8mb4_unicode_ci
    ), channel_keys AS (
        SELECT sid,seller_sku FROM {db}.amz_product_listing WHERE seller_sku!='' {channel_filter}
        UNION SELECT sid,seller_sku FROM {db}.amz_product_performance_inventory WHERE seller_sku!='' {channel_filter}
    ), sales AS (
        SELECT sid,msku,MAX(sales_30d) sales30d,MAX(updated_at) salesSyncTime
        FROM {db}.amz_restock_summary r
        WHERE node_type IN (2,3) AND TRIM(msku)!='' {sales_filter} GROUP BY sid,msku
    ), shops AS (
        SELECT sid,MAX(NULLIF(store_name,'')) storeName,
            CASE WHEN COUNT(DISTINCT NULLIF(country_code,''))=1 THEN MAX(NULLIF(country_code,'')) END countryCode,
            CASE WHEN COUNT(DISTINCT NULLIF(currency,''))=1 THEN MAX(NULLIF(currency,'')) END currency
        FROM {db}.shop_list WHERE platform_code='10001' GROUP BY sid
    ), channels AS (
        SELECT DISTINCT ws.sku,k.sid,k.seller_sku sellerSku,sh.storeName,
            l.local_name productName,l.small_image_url imageUrl,{site} site,
            l.price salePrice,UPPER(TRIM(COALESCE(NULLIF(l.currency_code,''),sh.currency))) COLLATE utf8mb4_unicode_ci currency,
            i.fba_stock fbaStock,i.fba_inbound fbaInbound,i.fba_stock+i.fba_inbound fbaTotalInventory,
            s.sales30d,i.sync_time inventorySyncTime,s.salesSyncTime,l.sync_time listingSyncTime
        FROM channel_keys k
        LEFT JOIN {db}.amz_product_listing l ON l.sid=k.sid AND l.seller_sku=k.seller_sku
        LEFT JOIN {db}.amz_product_performance_inventory i ON i.sid=k.sid AND i.seller_sku=k.seller_sku
        LEFT JOIN sales s ON s.sid=k.sid AND s.msku=k.seller_sku
        LEFT JOIN shops sh ON sh.sid=k.sid
        INNER JOIN warehouse_skus ws ON ws.sku=UPPER(TRIM(COALESCE(NULLIF(l.local_sku,''),NULLIF(i.local_sku,'')))) COLLATE utf8mb4_unicode_ci
    )"""
