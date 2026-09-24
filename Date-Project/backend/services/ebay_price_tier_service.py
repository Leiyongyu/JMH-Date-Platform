"""eBay 美元价格结构：从 dws_ebay_listing_price_tier 按月聚合。

数据链路（三层，见 ebay_listing_price_repository 的模块注释）：
    每月5日拉在售刊登 -> ods_ebay_store_listing_latest
                     -> dwd_ebay_listing_sku（拆变体、清洗，仍是原币）
                     -> dws_ebay_listing_price_tier（换美元、落七档）
                     -> 本文件按 月/店铺 现场聚合

为什么价格档不再用飞书「不良交易刊登」表算：那张表只收录**有不良交易的**刊登，
SKU 远不全。实测 2026-09 它只有 372 个 SKU / 551 行，而在售刊登有 2023 个 SKU /
16989 个店铺站点SKU组合。拿它当价格结构的主表，看到的是问题刊登的价格分布，
不是店铺商品的价格分布。它现在只负责提供「不良交易量」这一个事实。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from backend.database import db_connection
from backend.repositories import ebay_listing_price_repository as listing_price
from backend.repositories import ebay_sku_unit_price_repository as unit_price
from backend.services import listing_price_tier_service as service

CHINA = timezone(timedelta(hours=8))
TIER_COUNT = len(service.USD_LABELS)


def _percent(count, total):
    if not total:
        return '0.00'
    return str((Decimal(count) * 100 / Decimal(total)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def _ratio(part, whole, places='.0001'):
    """比值，分母为0返回None——画线时该点断开，而不是贴着0画一条假线。"""
    if not whole:
        return None
    return str((Decimal(part) / Decimal(whole)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _tiers(counts):
    total = sum(counts)
    return [dict(tier_no=i + 1, label=service.USD_LABELS[i], range=service.USD_RANGES[i],
                 sku_count=counts[i], sku_percent=_percent(counts[i], total))
            for i in range(TIER_COUNT)]


def _node(scope, store, site, counts, currencies):
    total = sum(counts)
    return dict(
        node_id=service.node_id(scope, store, site), store_key=store, store_name=store,
        scope=scope, site=site, currencies=currencies, group_sku_count=total,
        # 清洗丢弃的行是按月统计的，落不到具体店铺，所以节点上一律0，
        # 真实数字放在报表顶层（页面那条警告读的是顶层）。
        unclassified_sku_count=0, missing_sku_rows=0, invalid_price_rows=0,
        missing_rate_rows=0, missing_shop_rows=0, candidate_count=total,
        tiers=_tiers(counts))


def _counts(rows, key):
    """把 (维度, 档位, SKU数) 的行摊成 {维度: [七个档位的SKU数]}。"""
    buckets = {}
    for row in rows:
        index = int(row['tier_no']) - 1
        if not 0 <= index < TIER_COUNT:
            raise ValueError('分层表档位异常，请重新统计')
        buckets.setdefault(key(row), [0] * TIER_COUNT)[index] = int(row['sku_count'])
    return buckets


def read_report(month='', shop=''):
    """某个统计月份、每个店铺（可展开到站点）、每个价格档的SKU数与占比。

    month 为空取最新月份；shop 为空则返回全部店铺。
    """
    data = listing_price.tier_breakdown(month, shop)
    if not data['stat_month']:
        return dict(platform='ebay', state='EMPTY', items=[], stale=False, months=[], shops=[],
                    message='尚无在售刊登数据，请先执行「eBay店铺商品信息每月同步」，再点刷新')

    state = data['state'] or {}
    shop_counts = _counts(data['shop_rows'], lambda r: r['seller_account'])
    site_counts = _counts(data['site_rows'], lambda r: (r['seller_account'], r['site']))
    site_currencies = {(r['seller_account'], r['site']):
                       sorted(str(r['currencies'] or '').split(',')) if r['currencies'] else []
                       for r in data['site_rows']}

    items = []
    for store, counts in shop_counts.items():
        sites = sorted(key for key in site_counts if key[0] == store)
        children = [_node('SITE', store, key[1], site_counts[key], site_currencies.get(key, []))
                    for key in sites]
        currencies = sorted({c for child in children for c in child['currencies']})
        parent = _node('SHOP', store, '', counts, currencies)
        # 店铺行不是站点行相加：同一SKU在DE和UK各挂一条，站点各计一次，
        # 店铺按SKU去重只算一个（取该店铺内最低的那一档）。
        parent['children'] = children
        items.append(parent)
    items.sort(key=lambda p: (-p['group_sku_count'], p['store_name']))

    totals = [sum(counts[i] for counts in shop_counts.values()) for i in range(TIER_COUNT)]
    missing = [c for c in str(state.get('missing_currencies') or '').split(',') if c]
    return dict(
        platform='ebay', state='READY', stale=bool(data['stale']), version=service.USD_VERSION,
        target_currency='USD', items=items, months=data['months'], shops=data['shops'],
        stat_month=data['stat_month'], shop=shop.strip(),
        shop_count=len(items), site_group_count=sum(len(p['children']) for p in items),
        # total_sku_count 是店铺SKU组合数（同一SKU铺在N个店铺算N个），
        # distinct_sku_count 才是去重后的商品数，两个都给页面。
        total_sku_count=sum(totals), distinct_sku_count=data['distinct_sku_count'],
        unclassified_sku_count=0,
        missing_sku_rows=int(state.get('dropped_no_sku') or 0),
        invalid_price_rows=int(state.get('dropped_bad_price') or 0)
        + int(state.get('dropped_no_site') or 0),
        missing_rate_rows=int(state.get('dropped_no_rate') or 0),
        missing_shop_rows=0, missing_currencies=missing,
        rate_month=state.get('rate_month') or '', rates=data['rates'],
        rate_months=data['rate_months'], rate_field=listing_price.RATE_FIELD,
        source_listing_count=int(state.get('ods_rows') or 0),
        source_pulled_at=str(state.get('source_pulled_at') or ''),
        generated_at=str(state.get('computed_at') or datetime.now(CHINA).strftime('%Y-%m-%d %H:%M:%S')),
    )


def refresh_report(month='', shop=''):
    """重新跑一遍 ODS->DWD->DWS，再返回分层结果。不拉取任何外部接口。

    拉取是每月5日的定时任务干的事；这里只把已经拉回来的刊登重新清洗、
    重新换汇、重新分档——汇率表更新了、或者补跑了某个月的同步，点它就够了。

    顺带把飞书那张不良交易量的月度表也重算一遍：它每周三同步一批原始记录，
    但同步任务只落 ODS 不做汇总（用户明确要求"就点击更新再重算"），
    产品结构的不良率图读的是汇总后的量，不在这里重算就会一直停在上次的数。
    """
    defect = unit_price.refresh()
    refreshed = listing_price.refresh()
    return dict(read_report(month, shop), etl=refreshed, defect_refresh=defect)


def product_structure(year=''):
    """产品结构一页三图：销售数量占比、不良交易率、转化率（未接入）。

    三张图共用同一套价格档：在售刊登的挂牌价换成美元后落七档。
    事实数据各自来源不同（销量来自订单清洗层，不良量来自飞书表），
    但"这个SKU属于哪一档"只有一个定义，三张图才能横着看。
    """
    year = str(year or '').strip()
    with db_connection() as connection, connection.cursor() as cursor:
        years = listing_price.structure_years(cursor)
        if year and year not in years:
            year = ''
        if not year and years:
            year = years[0]
        sales_rows = listing_price.sales_by_sku(cursor, year or None)
        defect_rows = listing_price.defect_by_sku(cursor, year or None)
        wanted = sorted({row['stat_month'] for row in sales_rows}
                        | {row['stat_month'] for row in defect_rows})
        tiers, tier_source = listing_price.sku_tier_lookup(cursor, wanted)

    sales = _sales_share(sales_rows, tiers)
    defect = _defect_rate(defect_rows, tiers)
    fallback = sorted({f'{m}→{s}' for m, s in tier_source.items() if m != s})
    return dict(
        years=years, year=year, tier_source=tier_source,
        months=defect['months'], series=defect['series'], details=defect['details'],
        sales=sales,
        note='价格档统一来自 eBay 在售刊登：挂牌价按 dim_lingxing_currency_month.rate_org '
             '换成美元后落七档，同一SKU在多个店铺/站点挂不同价时取最低价定档。'
             '不良交易率的分子分母来自飞书「不良交易刊登」表，该表只收录有不良交易的刊登，'
             '故其数值高于eBay官方面板（后者分母含全部交易），只可用于横向比较各价格档与趋势。'
             + (f'　注意：{"、".join(fallback)} 这些月份没有当月的刊登快照，'
                f'用了箭头后面那个月的挂牌价定档。' if fallback else ''),
    )


def _sales_share(rows, tiers):
    """不同价格段销售数量占比。销量按付款时间归月，不分站点、不分店铺。

    销量是毛销量，不扣退货，与 eBay 补货2.0 同口径；退货量单列出来。
    配不上价格档的销量不塞进任何一档，单独计数——页面要能说清覆盖了多少。
    """
    months, buckets = [], {}
    for row in rows:
        month = row['stat_month']
        if month not in buckets:
            buckets[month] = dict(tiers={}, matched_qty=0, unmatched_qty=0,
                                  matched_orders=0, unmatched_orders=0,
                                  refund_qty=0, matched_skus=0, unmatched_skus=0)
            months.append(month)
        bucket = buckets[month]
        qty, order_rows = int(row['qty'] or 0), int(row['order_rows'] or 0)
        bucket['refund_qty'] += int(row['refund_qty'] or 0)
        matched = tiers.get(month, {}).get(row['sku'])
        if not matched:
            bucket['unmatched_qty'] += qty
            bucket['unmatched_orders'] += order_rows
            bucket['unmatched_skus'] += 1
            continue
        slot = bucket['tiers'].setdefault(int(matched['tier_no']),
                                          dict(qty=0, order_rows=0, sku_count=0))
        slot['qty'] += qty
        slot['order_rows'] += order_rows
        slot['sku_count'] += 1
        bucket['matched_qty'] += qty
        # 订单行数可加；COUNT(DISTINCT 订单号) 跨SKU相加会把一单多SKU的订单重复计，
        # 所以档位层面用行数。
        bucket['matched_orders'] += order_rows
        bucket['matched_skus'] += 1
    months.sort()
    series = [dict(tier_no=i + 1, label=service.USD_LABELS[i],
                   points=[_ratio(buckets[m]['tiers'].get(i + 1, {}).get('qty', 0),
                                  buckets[m]['matched_qty']) for m in months])
              for i in range(TIER_COUNT)]
    return dict(
        months=months, series=series,
        coverage=[dict(stat_month=m, matched_qty=buckets[m]['matched_qty'],
                       unmatched_qty=buckets[m]['unmatched_qty'],
                       total_qty=buckets[m]['matched_qty'] + buckets[m]['unmatched_qty'],
                       rate=_ratio(buckets[m]['matched_qty'],
                                   buckets[m]['matched_qty'] + buckets[m]['unmatched_qty']))
                  for m in months],
        quantities=[dict(stat_month=m,
                         tiers={t: buckets[m]['tiers'].get(t, dict(qty=0, order_rows=0, sku_count=0))
                                for t in range(1, TIER_COUNT + 1)},
                         matched_qty=buckets[m]['matched_qty'],
                         matched_orders=buckets[m]['matched_orders'],
                         refund_qty=buckets[m]['refund_qty'])
                    for m in months],
        note='销量取自 eBay 补货2.0 同一数据源 dwd_ebay_sku_analysis_order（按付款时间归月，'
             '不分站点、毛销量不扣退货）；价格档来自在售刊登。只有两边都有的SKU才计入，'
             '占比的分母就是这部分销量。',
    )


def _defect_rate(rows, tiers):
    """不同价格段不良交易率；额外画一条「总体」线作为基准。"""
    months, buckets = [], {}
    for row in rows:
        month = row['stat_month']
        if month not in buckets:
            buckets[month] = dict(stat_month=month, tiers={}, total_qty=0, defect_qty=0,
                                  unmatched_qty=0)
            months.append(month)
        bucket = buckets[month]
        total, defect = int(row['total_qty'] or 0), int(row['defect_qty'] or 0)
        matched = tiers.get(month, {}).get(row['sku'])
        # 总体线含全部SKU，包括配不上价格档的那些——它问的是"整体不良率"，
        # 不该因为某个SKU没挂在售刊登就被排除。
        bucket['total_qty'] += total
        bucket['defect_qty'] += defect
        if not matched:
            bucket['unmatched_qty'] += total
            continue
        slot = bucket['tiers'].setdefault(int(matched['tier_no']),
                                          dict(sku_count=0, total_qty=0, defect_qty=0))
        slot['sku_count'] += 1
        slot['total_qty'] += total
        slot['defect_qty'] += defect
    months.sort()
    for bucket in buckets.values():
        for slot in bucket['tiers'].values():
            slot['defect_rate'] = _ratio(slot['defect_qty'], slot['total_qty'])
    series = [dict(tier_no=i + 1, label=service.USD_LABELS[i],
                   points=[buckets[m]['tiers'].get(i + 1, {}).get('defect_rate') for m in months])
              for i in range(TIER_COUNT)]
    series.append(dict(tier_no=0, label='总体',
                       points=[_ratio(buckets[m]['defect_qty'], buckets[m]['total_qty'])
                               for m in months]))
    return dict(months=months, series=series, details=[buckets[m] for m in months])
