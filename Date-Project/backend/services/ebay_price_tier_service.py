"""eBay 美元价格结构：直接从 SKU 单价表按月聚合，不再走发布快照。

单价表 dws_ebay_sku_unit_price 本身就是按 月×店铺×SKU 存的，任意历史月份都能
当场算出来。再维护一份按月的发布快照只会多一处可能不一致的地方，所以这里
读什么就算什么；「刷新」做的事就是按飞书不良交易刊登表重算单价表。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from backend.repositories import ebay_sku_unit_price_repository as unit_price
from backend.services import listing_price_tier_service as service

CHINA = timezone(timedelta(hours=8))


def _percent(count, total):
    if not total:
        return '0.00'
    return str((Decimal(count) * 100 / Decimal(total)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def _rate(defect, total):
    """不良交易率；总量为0时返回None，画线时该点断开而不是贴着0画假线。"""
    if not total:
        return None
    return str((Decimal(defect) / Decimal(total)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP))


def _node(store, counts, quantities, defects, scope, site):
    total = sum(counts)
    labels, ranges = service.USD_LABELS, service.USD_RANGES
    return dict(
        node_id=service.node_id(scope, store, site), store_key=store, store_name=store,
        scope=scope, site=site, currencies=['USD'], group_sku_count=total,
        unclassified_sku_count=0, missing_sku_rows=0, invalid_price_rows=0,
        missing_rate_rows=0, missing_shop_rows=0, candidate_count=total,
        tiers=[dict(tier_no=i + 1, label=labels[i], range=ranges[i], sku_count=counts[i],
                    sku_percent=_percent(counts[i], total), total_qty=quantities[i],
                    defect_qty=defects[i], defect_rate=_rate(defects[i], quantities[i]))
               for i in range(len(labels))])


def read_report(month='', shop=''):
    """某个统计月份、每个店铺、每个价格档的SKU数与占比。

    month 为空取最新月份；shop 为空则返回全部店铺。
    """
    size = len(service.USD_LABELS)
    data = unit_price.tier_breakdown(month, shop)
    if not data['stat_month']:
        return dict(platform='ebay', state='EMPTY', items=[], stale=False, months=[], shops=[],
                    message='尚无SKU单价数据，请先同步飞书不良交易刊登表并刷新')

    per_shop = {}
    for row in data['items']:
        bucket = per_shop.setdefault(row['shop'], dict(counts=[0] * size, qty=[0] * size, defect=[0] * size))
        index = int(row['tier_no']) - 1
        if not 0 <= index < size:
            raise ValueError('单价表档位异常，请重新刷新')
        bucket['counts'][index] = int(row['sku_count'])
        bucket['qty'][index] = int(row['total_qty'] or 0)
        bucket['defect'][index] = int(row['defect_qty'] or 0)

    items = []
    for store, bucket in per_shop.items():
        parent = _node(store, bucket['counts'], bucket['qty'], bucket['defect'], 'SHOP', '')
        # 源表没有站点字段，店铺就是最细粒度；不造和店铺行同值的占位子节点，
        # 否则页面会多出一个展开箭头，点开看到的是一模一样的数字。
        parent['children'] = []
        items.append(parent)
    items.sort(key=lambda p: (-p['group_sku_count'], p['store_name']))

    totals = [sum(b['counts'][i] for b in per_shop.values()) for i in range(size)]
    return dict(
        platform='ebay', state='READY', stale=False, version=service.USD_VERSION,
        target_currency='USD', items=items, months=data['months'], shops=data['shops'],
        stat_month=data['stat_month'], unit_price_month=data['stat_month'],
        unit_price_reg_date=data['reg_date'], shop=shop.strip(),
        shop_count=len(items), site_group_count=0,
        # total_sku_count 是店铺SKU组合数（同一SKU铺在N个店铺算N个），
        # distinct_sku_count 才是去重后的商品数，两个都给页面。
        total_sku_count=sum(totals), distinct_sku_count=data.get('distinct_sku_count', 0), unclassified_sku_count=0, missing_sku_rows=0,
        invalid_price_rows=0, missing_rate_rows=0, missing_shop_rows=0,
        missing_currencies=[], rate_month='', rates={}, rate_months={},
        source_listing_count=sum(totals),
        generated_at=datetime.now(CHINA).strftime('%Y-%m-%d %H:%M:%S'),
    )


def refresh_report(month='', shop=''):
    """按飞书不良交易刊登表重算单价表，再返回分层结果。"""
    refreshed = unit_price.refresh()
    return dict(read_report(month, shop), unit_price_refresh=refreshed)


def product_structure(year=''):
    """各月各价格档的不良交易率，外加每月的总体线。不分店铺。

    口径提醒：分子分母都来自飞书「不良交易刊登」表，该表只收录有不良交易的刊登，
    所以这是"被标记刊登内部"的不良率（实测15~18%），不能与eBay官方面板对数。
    """
    rows, years = unit_price.defect_rate_by_tier(year.strip() or None)

    labels = service.USD_LABELS
    months, by_month = [], {}
    for row in rows:
        month = row['stat_month']
        if month not in by_month:
            by_month[month] = {'stat_month': month, 'tiers': {}, 'total_qty': 0, 'defect_qty': 0}
            months.append(month)
        bucket = by_month[month]
        total, defect = int(row['total_qty'] or 0), int(row['defect_qty'] or 0)
        bucket['tiers'][int(row['tier_no'])] = dict(
            sku_count=int(row['sku_count']), total_qty=total, defect_qty=defect,
            defect_rate=_rate(defect, total))
        bucket['total_qty'] += total
        bucket['defect_qty'] += defect

    series = [dict(tier_no=i + 1, label=labels[i],
                   points=[by_month[m]['tiers'].get(i + 1, {}).get('defect_rate') for m in months])
              for i in range(len(labels))]
    # 总体线：所有档位合计，用来看整体趋势，与各档位线画在一起。
    series.append(dict(tier_no=0, label='总体',
                       points=[_rate(by_month[m]['defect_qty'], by_month[m]['total_qty']) for m in months]))
    sales = _sales_share(year.strip() or None, labels)
    # 两张图的月份轴取并集：销量按付款时间归月，不良率按登记日期归月，
    # 两边覆盖的月份不一定一样，各画各的轴反而更实。
    return dict(
        months=months, years=years, year=year.strip(), series=series,
        details=[by_month[m] for m in months],
        sales=sales,
        note='分子分母均取自飞书「不良交易刊登」表，该表只收录有不良交易的刊登，'
             '故此处的不良交易率高于eBay官方面板（后者分母含全部交易），仅可用于横向比较各价格档与趋势。',
    )


def _sales_share(year, labels):
    """不同价格段销售数量占比：销量按付款时间归月，档位按登记日期归月。

    销量来自 eBay 补货2.0 的同一个数据源 dwd_ebay_sku_analysis_order，
    不分站点、不分店铺，看总的。占比的分母只算能配上档位的那部分销量——
    配不上的是当月不在不良交易刊登表里的SKU，没有单价就没有档位，
    硬塞进某一档会把图画歪，所以单列出来让页面说明覆盖了多少。
    """
    from backend.repositories import ebay_sku_unit_price_repository as unit_price
    months, buckets = unit_price.sales_by_tier(year)
    series = []
    for index, label in enumerate(labels):
        tier = index + 1
        points = []
        for month in months:
            bucket = buckets[month]
            matched = bucket['matched_qty']
            qty = bucket['tiers'].get(tier, {}).get('qty', 0)
            points.append(_percent_ratio(qty, matched))
        series.append(dict(tier_no=tier, label=label, points=points))
    coverage = [dict(stat_month=m,
                     matched_qty=buckets[m]['matched_qty'],
                     unmatched_qty=buckets[m]['unmatched_qty'],
                     total_qty=buckets[m]['matched_qty'] + buckets[m]['unmatched_qty'],
                     rate=_percent_ratio(buckets[m]['matched_qty'],
                                         buckets[m]['matched_qty'] + buckets[m]['unmatched_qty']))
                for m in months]
    # 图上悬浮时除了占比还要看得到绝对量：销量多少件、对应多少个订单行。
    return dict(
        months=months, series=series, coverage=coverage,
        quantities=[dict(stat_month=m,
                         tiers={t: dict(qty=buckets[m]['tiers'].get(t, {}).get('qty', 0),
                                        order_rows=buckets[m]['tiers'].get(t, {}).get('order_rows', 0),
                                        sku_count=buckets[m]['tiers'].get(t, {}).get('sku_count', 0))
                                for t in range(1, len(labels) + 1)},
                         matched_qty=buckets[m]['matched_qty'],
                         matched_orders=buckets[m]['matched_orders'])
                    for m in months],
        note='销量取自eBay补货2.0同一数据源（按付款时间归月，不分站点）；价格档来自'
             '同月的SKU单价表（按登记日期归月）。两者都有的SKU才计入，占比的分母是'
             '这部分销量，页面上标出了覆盖比例。',
    )


def _percent_ratio(part, whole):
    """占比，保留四位小数；分母为0返回None，画图时该点断开。"""
    if not whole:
        return None
    return str((Decimal(part) / Decimal(whole)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP))
