"""Attach native-currency price ranges to each platform's site inventory rows."""
from backend.services.ebay_mixed_sales_service import list_sales, AMZ_METRICS, STOCK_FIELDS
from backend.services.mixed_sales_price_service import list_price_ranges
from backend.services.mixed_sales_amz_store_service import list_store_inventory
from backend.services.mixed_sales_age_service import attach_ages

PRICE_FIELDS = ('amzMinPrice', 'amzMaxPrice', 'ebayMinPrice', 'ebayMaxPrice')
SALES_FIELDS = ('amzSales30d', 'ebaySales30d')


def _all_pages(fetch, **params):
    first = fetch(**params, page=1, page_size=200)
    rows = list(first['items'])
    params = dict(params)
    if 'calculation_version' in params and first.get('calculationVersion'):
        params['calculation_version'] = first['calculationVersion']
    if 'stat_month' in params and first.get('statMonth'):
        params['stat_month'] = first['statMonth']
    page = 1
    while len(rows) < first['total']:
        page += 1
        data = fetch(**params, page=page, page_size=200)
        if not data['items']:
            raise ValueError('明细数据已变化，请重新查询')
        rows.extend(data['items'])
    return first, rows


def list_site_details(*, sku, sid=None, calculation_version=None, stat_month=None,
                      page=1, page_size=20, sort_field=None, sort_order=None,
                      platform='amz', site=None):
    if platform not in ('amz','ebay'):
        raise ValueError('无效平台')
    inventory, inventory_rows = _all_pages(list_sales, platform=platform, details=True,
        sku=sku, sid=sid, site=site, calculation_version=calculation_version, sort_field='site', sort_order='asc')
    if inventory.get('skuInBothPlatforms') is False:
        return {**inventory, 'items': [], 'total': 0, 'pageNum': max(int(page), 1),
                'pageSize': min(max(int(page_size), 1), 200), 'months': [], 'statMonth': stat_month}
    peer_platform = 'ebay' if platform == 'amz' else 'amz'
    _, peer_rows = _all_pages(list_sales, platform=peer_platform, details=True,
        sku=sku, site=site, calculation_version=inventory.get('calculationVersion') or calculation_version,
        sort_field='site', sort_order='asc')
    # Sales belong to SKU + site, independently of the currency used for quotes.
    peer_by_site = {r['site']: r for r in peer_rows if r['site'] is not None}
    prices, price_rows = _all_pages(list_price_ranges, sku=sku, site=site, stat_month=stat_month)
    metrics = AMZ_METRICS if platform == 'amz' else (*STOCK_FIELDS, 'totalInventory', 'sales30d')
    if platform == 'amz':
        rows = _amz_store_rows(sku, list_store_inventory(sku=sku, sid=sid, site=site),
                               price_rows, peer_by_site, include_unmatched=sid is None)
        return _page_rows(rows, inventory, prices, metrics, platform, page, page_size, sort_field, sort_order)
    by_site = {r['site']: r for r in inventory_rows}
    rows = []
    covered = set()
    for quote in price_rows:
        site = quote['site']
        # Unknown sites from different platforms must not share inventory.
        own = by_site.get(site) if site is not None or quote.get('unmatchedPlatform') == platform.upper() else None
        if own is not None:
            covered.add(site)
        rows.append(dict(sku=sku, site=site, currency=quote['currency'],
                         productName=own.get('productName') if own else None,
                         **{field: own.get(field) if own else None for field in metrics},
                         **{field: quote.get(field) for field in PRICE_FIELDS}))
    for own in inventory_rows:
        if own['site'] not in covered:
            rows.append({key: own.get(key) for key in ('sku','site','productName',*metrics)}
                        | {'currency': None, **dict.fromkeys(PRICE_FIELDS)})
    displayed_sites = {row['site'] for row in rows}
    for peer_site, peer in peer_by_site.items():
        if peer_site not in displayed_sites and peer.get('sales30d') is not None:
            rows.append(dict(sku=sku,site=peer_site,productName=peer.get('productName'),currency=None,
                             **dict.fromkeys(metrics),**dict.fromkeys(PRICE_FIELDS)))
    own_sales_field = 'amzSales30d' if platform == 'amz' else 'ebaySales30d'
    peer_sales_field = 'ebaySales30d' if platform == 'amz' else 'amzSales30d'
    for row in rows:
        row[own_sales_field] = row.get('sales30d')
        row[peer_sales_field] = peer_by_site.get(row['site'], {}).get('sales30d')
    return _page_rows(rows, inventory, prices, metrics, platform, page, page_size, sort_field, sort_order)


def _amz_store_rows(sku, stores, prices, peer_by_site, *, include_unmatched):
    quotes = {(q['site'], q['currency']): q for q in prices
              if q['site'] is not None and q['currency'] is not None}
    rows, covered = [], set()
    for store in stores:
        row = dict(store)
        key = row['site'], row['currency']
        peer = quotes.get(key, {})
        covered.add(key)
        row.update(amzSales30d=row.get('sales30d'),
                   ebaySales30d=peer_by_site.get(row['site'], {}).get('sales30d'),
                   ebayMinPrice=peer.get('ebayMinPrice'), ebayMaxPrice=peer.get('ebayMaxPrice'))
        rows.append(row)
    if include_unmatched:
        # Preserve eBay-only SKU/site/currency comparisons without inventing an Amazon shop.
        for quote in prices:
            key = quote['site'], quote['currency']
            if key in covered and quote['site'] is not None and quote['currency'] is not None:
                continue
            if not any(quote.get(k) is not None for k in ('ebayMinPrice', 'ebayMaxPrice')):
                continue
            rows.append(dict(sku=sku, sid=None, storeName=None, site=quote['site'], currency=quote['currency'],
                **dict.fromkeys(AMZ_METRICS), amzSales30d=None, amzMinPrice=None, amzMaxPrice=None,
                ebaySales30d=peer_by_site.get(quote['site'], {}).get('sales30d'),
                ebayMinPrice=quote.get('ebayMinPrice'), ebayMaxPrice=quote.get('ebayMaxPrice')))
        sites = {row['site'] for row in rows}
        for site, peer in peer_by_site.items():
            if site not in sites and peer.get('sales30d') is not None:
                rows.append(dict(sku=sku, sid=None, storeName=None, site=site, currency=None,
                    **dict.fromkeys(AMZ_METRICS), **dict.fromkeys(PRICE_FIELDS),
                    amzSales30d=None, ebaySales30d=peer['sales30d']))
    return rows


def _page_rows(rows, inventory, prices, metrics, platform, page, page_size, sort_field, sort_order):
    default_sort = 'fbaTotalInventory' if platform == 'amz' else 'sales30d'
    field = sort_field if sort_field in {'sku', 'site', 'storeName', *metrics, *PRICE_FIELDS, *SALES_FIELDS} else default_sort
    descending = str(sort_order).lower() not in ('asc', 'ascending')
    rows.sort(key=lambda r: (r.get('site') or '', r.get('storeName') or '', str(r.get('sid') or ''), r.get('currency') or ''))
    available = [r for r in rows if r.get(field) is not None]
    available.sort(key=lambda r: r[field], reverse=descending)
    rows = available + [r for r in rows if r.get(field) is None]
    page, size = max(int(page), 1), min(max(int(page_size), 1), 200)
    selected = rows[(page-1)*size:page*size]
    attach_ages(selected, platform=platform, details=True)
    return {**inventory, 'items': selected, 'total': len(rows),
            'pageNum': page, 'pageSize': size, 'months': prices['months'], 'statMonth': prices['statMonth']}
