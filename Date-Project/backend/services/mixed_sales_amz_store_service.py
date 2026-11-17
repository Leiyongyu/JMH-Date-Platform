"""Amazon mixed-sales detail at warehouse SKU + shop + site + currency."""
from backend.database import db_connection
from backend.services.mixed_sales_sql import amazon_sources, canonical_site


def list_store_inventory(*, sku, sid=None, site=None):
    sku = str(sku or '').strip().upper()
    if not sku:
        raise ValueError('请选择产品SKU')
    code = canonical_site(site) if site else None
    if site and not code:
        raise ValueError('无效站点')
    if sid is not None and int(sid) <= 0:
        raise ValueError('店铺参数无效')
    where, args = ['sku=%s'], [sku]
    if sid is not None:
        where.append('sid=%s')
        args.append(int(sid))
    if code:
        where.append('site=%s')
        args.append(code)
    # Sum each SID/MSKU once before joining currency ranges. A different shop's
    # quote must never expand this shop's min/max or multiply its stock/sales.
    sql = f'''WITH {amazon_sources(exact_sku=True)}, selected AS (
        SELECT * FROM channels WHERE {' AND '.join(where)}
    ), inventory AS (
        SELECT sku,sid,site,MAX(storeName) storeName,MAX(productName) productName,
            SUM(fbaStock) fbaStock,SUM(fbaInbound) fbaInbound,
            SUM(fbaTotalInventory) fbaTotalInventory,SUM(sales30d) sales30d
        FROM selected GROUP BY sku,sid,site
    ), quotes AS (
        SELECT sku,sid,site,NULLIF(currency,'') currency,
            MIN(salePrice) amzMinPrice,MAX(salePrice) amzMaxPrice
        FROM selected GROUP BY sku,sid,site,NULLIF(currency,'')
    ) SELECT /*+ MAX_EXECUTION_TIME(15000) */ i.*,q.currency,q.amzMinPrice,q.amzMaxPrice
      FROM inventory i JOIN quotes q ON q.sku=i.sku AND q.sid <=> i.sid AND q.site <=> i.site
      ORDER BY i.site,i.storeName,i.sid,q.currency'''
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, [sku, *args])
        return list(cursor.fetchall())
