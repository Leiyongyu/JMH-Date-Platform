"""Mixed sales reuses replenishment v2 generations; SQL groups SKU/site metrics."""
import re

from backend.database import db_connection
from backend.services import ebay_replenishment_read_model as model
from backend.services.ebay_order_product_key import product_sku
from backend.services.mixed_sales_sql import amazon_sources, canonical_site, site_sql
from backend.services.mixed_sales_age_service import attach_ages, age_filter_sql

STOCK_FIELDS = {
    'chengduInTransitQty': 'chengdu_in_transit_quantity',
    'chengduSellableQty': 'chengdu_sellable_quantity',
    'overseasInTransitQty': 'overseas_in_transit_quantity',
    'overseasSellableQty': 'overseas_sellable_quantity',
}
SALES_FIELDS = {'sales7d': 'sales_qty_7d', 'sales15d': 'sales_qty_15d', 'sales30d': 'sales_qty_30d'}
SORT_FIELDS = {'sku', 'site', 'totalInventory', *STOCK_FIELDS, *SALES_FIELDS}


def _stock(field):
    # field is always selected from module constants, never from a request.
    return f"CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(base.payload,'$.{field}')),'null') AS DECIMAL(24,6))"


def _select_metrics(grouped):
    values = {key: _stock(field) for key, field in STOCK_FIELDS.items()}
    values.update({key: f'base.{field}' for key, field in SALES_FIELDS.items()})
    values['totalInventory'] = '(' + '+'.join(_stock(field) for field in STOCK_FIELDS.values()) + ')'
    return ','.join(f'{"SUM(" + expr + ")" if grouped else expr} AS {key}' for key, expr in values.items())


def list_sales(*, site=None, sku=None, product_name=None, page=1, page_size=50,
               sort_field=None, sort_order=None, calculation_version=None, details=False,
               platform='ebay', sid=None, age_bucket=None, age_operator=None, age_days=None):
    if platform not in ('amz', 'ebay'):
        raise ValueError('无效平台')
    if sid is not None and int(sid) <= 0:
        raise ValueError('店铺参数无效')
    age_filter, age_args = age_filter_sql(platform, age_bucket=age_bucket,
        age_operator=age_operator, age_days=age_days, sid=sid, site=site)
    sku = str(sku or '').strip().upper() if platform == 'amz' else product_sku(sku)
    if details and not sku:
        raise ValueError('请选择要查看的产品SKU')
    if calculation_version and not re.fullmatch('[0-9a-f]{32}', calculation_version):
        raise ValueError('无效计算版本，请刷新页面')
    page, size = max(int(page), 1), min(max(int(page_size), 1), 200)
    version = calculation_version or model.ensure_generation()
    allowed = {'sku', 'site', 'fbaStock', 'fbaInbound', 'fbaTotalInventory', 'sales30d'} if platform == 'amz' else SORT_FIELDS
    field = sort_field if sort_field in allowed else ('fbaTotalInventory' if platform == 'amz' else 'sales30d')
    # A summary spans sites, so site sorting falls back to the stable SKU key.
    if field == 'site' and not details:
        field = 'sku'
    direction = 'ASC' if str(sort_order).lower() in ('asc', 'ascending') else 'DESC'
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        connection.begin()
        cursor.execute(f'SELECT metadata,created_at FROM {model.PREFIX}generation WHERE generation=%s', (version,))
        header = cursor.fetchone()
        if not header:
            raise ValueError('计算版本已过期，请刷新混销页面后重试')
        metadata = model._decode(header['metadata'])
        generation = metadata.get('data_generation', version)
        sites = []
        if platform == 'ebay' and not details:
            # Site options include only SKUs actually present on both platforms.
            cursor.execute(_common_sku_sources() + '''
                SELECT /*+ MAX_EXECUTION_TIME(15000) */ c.site FROM channels c JOIN sku_keys k ON k.sku=c.sku WHERE c.site IS NOT NULL
                UNION SELECT e.siteCode site FROM ebay_base e JOIN sku_keys k ON k.sku=e.sku
                WHERE e.siteCode IS NOT NULL''', (generation,))
            sites = sorted({r['site'] for r in cursor.fetchall() if r.get('site')})
        in_both = True
        if details:
            cursor.execute(_common_sku_sources(exact_sku=True) + ' SELECT /*+ MAX_EXECUTION_TIME(15000) */ COUNT(*) n FROM sku_keys WHERE sku=%s', (sku, generation, sku))
            in_both = bool(cursor.fetchone()['n'])
        ctes, query, args = _intersection_query(generation, platform,
                                         details, sku, sid, site)
        source = f'FROM ({query}) metrics'
        filters = []
        if product_name and product_name.strip() and not details:
            filters.append('productName LIKE %s')
            args.append(f'%{product_name.strip()}%')
        if age_filter:
            filters.append(age_filter)
            args.extend(age_args)
        if filters:
            source += ' WHERE ' + ' AND '.join(filters)
        order = f' ORDER BY {field} IS NULL,{field} {direction},sku' + (',site' if details else '')
        if details:
            # A single SKU produces only site aggregates. Compute them once;
            # counting and selecting separately would execute the same joins twice.
            cursor.execute(ctes + f' SELECT /*+ MAX_EXECUTION_TIME(15000) */ * {source}' + order, args)
            all_items = list(cursor.fetchall())
            total = len(all_items)
            items = all_items[(page-1)*size:page*size]
        elif not sku and not product_name and sid is None and not site and not age_filter:
            cursor.execute(ctes + ' SELECT /*+ MAX_EXECUTION_TIME(15000) */ COUNT(*) n FROM sku_keys', args)
        else:
            cursor.execute(ctes + f' SELECT /*+ MAX_EXECUTION_TIME(15000) */ COUNT(*) n {source}', args)
        if not details:
            total = int(cursor.fetchone()['n'])
            cursor.execute(ctes + f' SELECT /*+ MAX_EXECUTION_TIME(15000) */ * {source}' + order
                           + ' LIMIT %s OFFSET %s', [*args, size, (page-1)*size])
            items = list(cursor.fetchall())
            attach_ages(items, platform=platform, sid=sid, site=site, cursor=cursor)
    return dict(items=items, total=total, pageNum=page, pageSize=size,
                sites=sites, calculationVersion=version,
                calculatedAt=str(header['created_at']), referenceDate=metadata.get('reference_date'),
                skuInBothPlatforms=in_both)


AMZ_METRICS = ('fbaStock', 'fbaInbound', 'fbaTotalInventory', 'sales30d')


def _common_sku_sources(*, exact_sku=False):
    # Warehouse presence alone does not prove an Amazon product exists.
    # DISTINCT prevents shops/sites from multiplying the common SKU rows.
    return f'''WITH {amazon_sources(exact_sku=exact_sku)}, ebay_base AS (
        SELECT base.*, {site_sql('base.site')} siteCode FROM {model.PREFIX}result base WHERE base.generation=%s
        {"AND base.sku=(SELECT sku FROM wanted_sku)" if exact_sku else ''}
    ), sku_keys AS (
        SELECT DISTINCT c.sku FROM channels c
        INNER JOIN ebay_base e ON e.sku COLLATE utf8mb4_unicode_ci=c.sku
    )'''


def _intersection_query(generation, platform, details, sku, sid, site):
    code = canonical_site(site) if site else None
    if site and code is None:
        raise ValueError('无效站点')
    ctes = _common_sku_sources(exact_sku=details) + f''', amz_products AS (
        SELECT ws.sku,ws.warehouseNames,ws.warehouseSyncTime,
            MAX(c.productName) productName,MAX(c.imageUrl) imageUrl,
            COUNT(c.sellerSku) listingCount,COUNT(DISTINCT c.sid) storeCount,
            COUNT(c.fbaTotalInventory) inventoryMatchedCount,COUNT(c.sales30d) salesMatchedCount,
            {','.join(f'SUM(c.{k}) {k}' for k in AMZ_METRICS)},
            MIN(c.inventorySyncTime) inventorySyncTime,MIN(c.salesSyncTime) salesSyncTime
        FROM warehouse_skus ws LEFT JOIN channels c ON c.sku=ws.sku
        {"WHERE c.sid=%s" if sid is not None else ''}
        GROUP BY ws.sku,ws.warehouseNames,ws.warehouseSyncTime
    ), ebay_products AS (
        SELECT base.sku,MAX(base.product_name) productName,COUNT(DISTINCT base.site) siteCount,
            {_select_metrics(True)} FROM ebay_base base
        {"WHERE base.siteCode=%s" if code else ''} GROUP BY base.sku
    )'''
    args = [sku, generation] if details else [generation]
    if sid is not None:
        args.append(int(sid))
    if code:
        args.append(code)
    if details:
        if platform == 'amz':
            query = f'''SELECT c.sku,c.site,MAX(c.productName) productName,
                {','.join(f'SUM(c.{k}) {k}' for k in AMZ_METRICS)}
                FROM channels c JOIN sku_keys common ON common.sku=c.sku
                WHERE c.sku=%s {"AND c.sid=%s" if sid is not None else ''}
                {"AND c.site=%s" if code else ''}
                GROUP BY c.sku,c.site'''
            args.append(sku)
            if sid is not None:
                args.append(int(sid))
            if code:
                args.append(code)
        else:
            query = f'''SELECT k.sku,k.site,MAX(base.product_name) productName,{_select_metrics(True)}
                FROM (SELECT sku,siteCode site FROM ebay_base UNION SELECT sku,site FROM channels) k
                JOIN sku_keys common ON common.sku=k.sku
                LEFT JOIN ebay_base base ON base.sku=k.sku AND base.siteCode=k.site
                WHERE k.sku=%s {"AND k.site=%s" if code else ''} GROUP BY k.sku,k.site'''
            args.append(sku)
            if code:
                args.append(code)
    else:
        metrics = ('a.warehouseNames,a.warehouseSyncTime,a.imageUrl,a.listingCount,a.storeCount,'
                   'a.inventoryMatchedCount,a.salesMatchedCount,a.inventorySyncTime,a.salesSyncTime,'
                   + ','.join('a.' + k for k in AMZ_METRICS)) if platform == 'amz' else (
                       'e.siteCount,' + ','.join('e.' + k for k in (*STOCK_FIELDS, *SALES_FIELDS, 'totalInventory')))
        query = f'''SELECT k.sku,COALESCE(a.productName,e.productName) productName,{metrics}
            FROM sku_keys k LEFT JOIN amz_products a ON a.sku=k.sku LEFT JOIN ebay_products e ON e.sku=k.sku
            WHERE 1=1'''
        if sid is not None:
            query += ' AND a.sku IS NOT NULL'
        if code:
            query += ' AND (e.sku IS NOT NULL OR EXISTS (SELECT 1 FROM channels c WHERE c.sku=k.sku AND c.site=%s))'
            args.append(code)
        if sku:
            query += ' AND k.sku LIKE %s'
            args.append(f'%{sku}%')
    return ctes, query, args
