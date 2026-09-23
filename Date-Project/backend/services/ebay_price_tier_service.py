"""兼容原eBay报表路由，读取独立美元七档统计。"""
from decimal import Decimal, ROUND_HALF_UP

from backend.services import listing_price_tier_service as service


def read_report():
    return service.read_report('ebay')


def refresh_report():
    return service.refresh_report('ebay')


def _rate(defect, total):
    """不良交易率 = 不良交易量 / 总交易量，保留四位小数；总量为0时返回None。

    返回 None 而不是 0：分母为0代表"这一档这个月没有成交"，
    画线时该点应当断开，而不是画一条贴着0的假线。
    """
    if not total:
        return None
    return str((Decimal(defect) / Decimal(total)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP))


def product_structure(year=''):
    """各月各价格档的不良交易率，外加每月的总体线。

    口径提醒：分子分母都来自飞书「不良交易刊登」表，该表只收录有不良交易的刊登，
    所以这是"被标记刊登内部"的不良率（实测15~18%），不能与eBay官方面板对数。
    """
    from backend.repositories import ebay_sku_unit_price_repository as unit_price
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
    return dict(
        months=months, years=years, year=year.strip(), series=series,
        details=[by_month[m] for m in months],
        note='分子分母均取自飞书「不良交易刊登」表，该表只收录有不良交易的刊登，'
             '故此处的不良交易率高于eBay官方面板（后者分母含全部交易），仅可用于横向比较各价格档与趋势。',
    )
