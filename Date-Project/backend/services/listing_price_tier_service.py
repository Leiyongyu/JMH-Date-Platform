"""AMZ人民币五档/eBay美元七档报表；原始表和汇率表只读。"""
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from fractions import Fraction

VERSION = 2
# 3->4：美元档位由5档改为7档，旧快照按旧档位存着，版本号必须跟着走，
# 否则 read_report 会把5档数据套到7档标签上。
USD_VERSION = 4
LABELS = ('低价引流层', '基础走量层', '利润核心层', '高客单层', '专业/稀缺层')
# 美元档位不用业务分层叫法，直接显示价格段。
USD_LABELS = ('0-5', '5-20', '20-50', '50-100', '100-200', '200-500', '500以上')
RANGES = ('< ¥340', '¥340–<680', '¥680–<1,020', '¥1,020–1,690', '> ¥1,690')
USD_RANGES = ('$0–<5', '$5–<20', '$20–<50', '$50–<100', '$100–<200', '$200–<500', '≥ $500')
# 美元分档阈值，左闭右开；人民币档位沿用旧口径（第4档含上界1690），不动。
USD_BOUNDS = (5, 20, 50, 100, 200, 500)
METRICS = ('group_sku_count', 'unclassified_sku_count', 'missing_sku_rows', 'invalid_price_rows',
           'missing_rate_rows', 'missing_shop_rows', 'candidate_count')


def text(value):
    return str(value or '').strip()


def decimal_value(value):
    if value is None or isinstance(value, bool) or not str(value).strip():
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def node_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def labels_for(target_currency='CNY'):
    return USD_LABELS if target_currency == 'USD' else LABELS


def ranges_for(target_currency='CNY'):
    return USD_RANGES if target_currency == 'USD' else RANGES


def tier_count(target_currency='CNY'):
    return len(labels_for(target_currency))


def tier_index(price, target_currency='CNY'):
    if target_currency == 'USD':
        # 七档一律左闭右开：[0,5) [5,20) [20,50) [50,100) [100,200) [200,500) [500,∞)
        for i, bound in enumerate(USD_BOUNDS):
            if price < bound: return i
        return len(USD_BOUNDS)
    a, b, c, d = 340, 680, 1020, 1690
    if price < a: return 0
    if price < b: return 1
    if price < c: return 2
    if price <= d: return 3
    return 4


def tiers(counts, target_currency='CNY'):
    total = sum(counts)
    labels, ranges = labels_for(target_currency), ranges_for(target_currency)
    return [dict(tier_no=i+1, label=labels[i], range=ranges[i], sku_count=count,
                 sku_percent=str((Decimal(count)*100/total).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if total else '0.00')
            for i, count in enumerate(counts)]


def ebay_candidates(rows):
    for row in rows:
        try:
            # 原始表不再存整份normalized_json（其余键与扁平列重复），只留变体数组。
            # NULL 表示这条刊登没有变体，退回用父级的sku与价格，不是数据异常。
            variations = row['variations_json']
            if isinstance(variations, str): variations = json.loads(variations)
            if variations is None: variations = []
            if not isinstance(variations, list): raise ValueError()
            candidates = variations or [{'sku': row.get('sku'), 'price': {'value': row.get('current_price'), 'currency': row.get('currency')}}]
            for item in candidates:
                money = item.get('price') or {}
                yield dict(store_key=row['seller_user_id'], store_name=row['seller_account'], site=text(row.get('site')).upper(),
                           currency=text(money.get('currency')).upper(), sku=text(item.get('sku')), price=money.get('value'), missing_shop=False)
        except (ValueError, TypeError, AttributeError):
            raise ValueError('eBay原始规格结构异常，保留旧报表') from None


def amz_shop(sid, shops):
    shop = shops.get(str(sid))
    if not shop or not text(shop.get('store_name')):
        return dict(store_key='sid:'+str(sid), store_name='未匹配店铺 sid='+str(sid), site='', missing_shop=True)
    name, country = text(shop['store_name']), text(shop.get('country_code')).upper()
    # 只去掉与真实country_code完全一致的末尾后缀，不任意截断店名。
    base = name[:-(len(country)+1)] if country and name.upper().endswith('-'+country) else name
    return dict(store_key=node_id('amz-shop', base), store_name=base, site=country, missing_shop=False)


def amz_candidates(rows, shops):
    for row in rows:
        if row.get('status') != 1 or row.get('is_delete') != 0:
            continue
        shop = amz_shop(row['sid'], shops)
        yield dict(shop, site=shop['site'] or text(row.get('marketplace')), sku=text(row.get('seller_sku')),
                   currency=text(row.get('currency_code')).upper(), price=row.get('landed_price'))


def summarize(candidates, rates, empty_stores=(), *, target_currency='CNY'):
    if target_currency not in ('CNY', 'USD'):
        raise ValueError('不支持的统计币种')
    groups, stores = {}, {}
    missing_currencies = set()
    for row in candidates:
        store_key, site = row['store_key'], row['site']
        stores[store_key] = row['store_name']
        key = (store_key, site)  # 换算后同站点跨币种同SKU也去重。
        if key not in groups:
            groups[key] = dict(store_key=store_key, store_name=row['store_name'], site=site, prices={}, seen=set(),
                               currencies=set(), **{m: 0 for m in METRICS})
        group = groups[key]
        group['candidate_count'] += 1
        group['currencies'].add(row['currency'] or '未知')
        if row['missing_shop']: group['missing_shop_rows'] += 1
        price = decimal_value(row['price'])
        # USD originals bypass FX entirely. CNY originals already are the intermediate currency.
        native_usd = target_currency == 'USD' and row['currency'] == 'USD'
        rate = Decimal(1) if native_usd or (target_currency == 'USD' and row['currency'] == 'CNY') else decimal_value(rates.get(row['currency']))
        usd_rate = decimal_value(rates.get('USD')) if target_currency == 'USD' and not native_usd else Decimal(1)
        if price is None or not site: group['invalid_price_rows'] += 1
        missing_rate = rate is None or rate <= 0
        missing_usd = usd_rate is None or usd_rate <= 0
        if missing_rate:
            missing_currencies.add(row['currency'] or '未知')
        if missing_usd:
            missing_currencies.add('USD')
        if missing_rate or missing_usd:
            group['missing_rate_rows'] += 1
        if not row['sku']:
            group['missing_sku_rows'] += 1
            continue
        group['seen'].add(row['sku'])
        if price is None or not site or missing_rate or missing_usd: continue
        # 不先截断汇率或将单价四舍五入，避免在档位边界翻档。
        if target_currency == 'USD':
            # Exact rational FX avoids recurring-decimal rounding at tier boundaries.
            converted = Fraction(price) if native_usd else Fraction(price) * Fraction(rate) / Fraction(usd_rate)
        else:
            with localcontext() as ctx:
                ctx.prec = max(64, len(price.as_tuple().digits)+len(rate.as_tuple().digits)+2)
                converted = price*rate
        group['prices'][row['sku']] = min(converted, group['prices'].get(row['sku'], converted))
    for store in empty_stores:
        stores.setdefault(store['store_key'], store['store_name'])
    parents = {key: dict(node_id=node_id('SHOP', key), store_key=key, store_name=name, scope='SHOP', site='', currencies=[],
                         children=[], counts=[0]*tier_count(target_currency), **{m: 0 for m in METRICS}) for key,name in stores.items()}
    for (key, site), group in sorted(groups.items()):
        prices = group.pop('prices')
        group['group_sku_count'] = len(prices)
        group['unclassified_sku_count'] = len(group.pop('seen')-prices.keys())
        counts = [0]*tier_count(target_currency)
        for price in prices.values(): counts[tier_index(price, target_currency)] += 1
        group['tiers'] = tiers(counts, target_currency)
        group['currencies'] = sorted(group['currencies'])
        group.update(node_id=node_id('SITE', key, site), scope='SITE')
        parent = parents[key]
        parent['children'].append(group)
        for m in METRICS: parent[m] += group[m]
        parent['counts'] = [a+b for a,b in zip(parent['counts'], counts)]
        parent['currencies'] = sorted(set(parent['currencies']) | set(group['currencies']))
    items = sorted(parents.values(), key=lambda g: (-g['group_sku_count'], g['store_name']))
    for parent in items: parent['tiers'] = tiers(parent.pop('counts'), target_currency)
    return dict(version=USD_VERSION if target_currency == 'USD' else VERSION, target_currency=target_currency,
                rate_field='rate_org' if target_currency == 'USD' else 'my_rate',
                items=items, shop_count=len(items), site_group_count=len(groups),
                total_sku_count=sum(p['group_sku_count'] for p in items), missing_currencies=sorted(missing_currencies),
                **{m: sum(p[m] for p in items) for m in METRICS if m != 'group_sku_count'})


def read_report(platform):
    from backend.repositories import listing_price_tier_repository as repo
    return repo.read_report(platform)


def refresh_report(platform):
    from backend.repositories import listing_price_tier_repository as repo
    return repo.rebuild(platform)
