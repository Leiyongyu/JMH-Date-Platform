"""Read-only company/platform/group comparisons over uploaded monthly finance history."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.database import db_connection
from backend.services import sales_dashboard_service as source

MONEY = {'platform_income': '平台收入', 'platform_expense': '平台支出', 'gross_profit': '毛利润',
         'net_sales': '净收款', 'gross_sales': '销售总额', 'refund_amount': '退款金额'}
RATIOS = {'gross_margin': ('gross_profit', 'platform_income', '毛利率'),
          'refund_rate': ('refund_amount', 'gross_sales', '退款率')}
SPECIAL_FIELDS = {
    'ebay': {'transaction_fee': '成交费', 'advertising_fee': '广告费', 'listing_fee': '刊登／副标题',
             'penalty': '罚款', 'other_fee': '其它费用', 'compensation': '赔偿'},
    'amz': {'commission': '平台佣金', 'shipping_fee': '发货费', 'advertising_fee': '广告和推广费'},
}


def shift(month, count):
    year, value = map(int, month.split('-'))
    year, value = divmod(year * 12 + value - 1 + count, 12)
    return f'{year:04}-{value + 1:02}'


def months_between(start, end):
    result = []
    while start <= end:
        result.append(start)
        start = shift(start, 1)
    return result


def text(value):
    return str(value) if value is not None else None


def sum_present(values):
    values = [Decimal(v) for v in values if v is not None]
    return sum(values, Decimal(0)) if values else None


def analyze(platform, start_month, end_month, groups, granularity='month', today=None):
    if platform not in ('all', 'ebay', 'amz'):
        raise ValueError('平台仅支持 all、ebay、amz')
    if granularity not in ('month', 'quarter'):
        raise ValueError('统计粒度仅支持 month 或 quarter')
    start, end = source.month_key(start_month), source.month_key(end_month)
    if start > end:
        raise ValueError('开始月份不能晚于结束月份')
    if granularity == 'quarter':
        start = shift(start, -((int(start[-2:]) - 1) % 3))
        end = shift(end, 2 - ((int(end[-2:]) - 1) % 3))
    months = months_between(start, end)
    if len(months) > 120:
        raise ValueError('一次最多查询120个月')
    platforms = list(source.TABLES) if platform == 'all' else [platform]
    selected = list(dict.fromkeys(str(g).strip() for g in groups if str(g).strip()))
    if len(selected) > 100 or any(len(g) > 70 for g in selected):
        raise ValueError('组别筛选过多或过长')
    scope = {p: [] for p in platforms}
    for group in selected:
        if ':' in group:
            p, g = group.split(':', 1)
        elif platform != 'all':
            p, g = platform, group
        else:
            raise ValueError('全部平台的组别须使用 平台:组别 格式')
        if p not in scope or not g:
            raise ValueError('组别与所选平台不一致')
        scope[p].append(g.upper())
    if selected:
        scope = {p: list(dict.fromkeys(gs)) for p, gs in scope.items() if gs}
    step = 3 if granularity == 'quarter' else 1
    previous_start, previous_end = shift(start, -len(months)), shift(start, -1)
    year_start, year_end = shift(start, -12), shift(end, -12)
    # Includes whole-range comparisons and the prior period of each chart point.
    history_start = min(previous_start, year_start, shift(start, -step))
    rows, raw_details = [], {}
    for p, gs in scope.items():
        # The existing report remains the single source for uploaded original detail columns.
        raw_details[p] = source.report(p, start, end, gs)['details']
        params = [history_start, end]
        condition = ''
        if gs:
            condition = f" AND group_code IN ({','.join(['%s'] * len(gs))})"
            params.extend(gs)
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT stat_month,group_code,{source.METRICS[p]} net_sales,"
                        f"platform_income,platform_expense,gross_profit,gross_sales,refund_amount,{','.join(SPECIAL_FIELDS[p])} FROM {source.TABLES[p]} "
                        f"WHERE stat_month BETWEEN %s AND %s{condition} ORDER BY stat_month,group_code", params)
            rows.extend(dict(r, platform=p) for r in cur.fetchall())
    current_month = (today or datetime.now(timezone(timedelta(hours=8))).date()).strftime('%Y-%m')
    # Index once: all metric/date/dimension computations below reuse the same source read.
    index = {}
    for row in rows:
        index.setdefault((row['platform'], row['stat_month']), []).append(row)

    def aggregate(first, last, target_scope):
        period = months_between(first, last)
        period_rows, missing_scope = [], set()
        for p, gs in target_scope.items():
            for month in period:
                found = [r for r in index.get((p, month), []) if not gs or r['group_code'] in gs]
                period_rows.extend(found)
                if not found or (gs and set(gs) - {r['group_code'] for r in found}):
                    missing_scope.add(month)
        result = {}
        # Platform-specific fields never get summed into an ambiguous cross-platform metric.
        special = SPECIAL_FIELDS[next(iter(target_scope))] if len(target_scope) == 1 else {}
        for key in {**MONEY, **special}:
            missing = missing_scope | {r['stat_month'] for r in period_rows if r.get(key) is None}
            missing |= {m for m in period if m >= current_month}
            result[key] = {'value': text(sum_present([r.get(key) for r in period_rows])),
                           'complete': not missing, 'missing_months': sorted(missing), 'unit': 'CNY'}
        ratios = {**RATIOS, **{f'{key}_share': (key, 'gross_sales', '占销售总额比例') for key in special}}
        for key, (n, d, _) in ratios.items():
            numerator, denominator = result[n]['value'], result[d]['value']
            value = Decimal(numerator) / Decimal(denominator) if numerator is not None and denominator is not None and Decimal(denominator) else None
            result[key] = {'value': text(value), 'complete': result[n]['complete'] and result[d]['complete'],
                           'missing_months': sorted(set(result[n]['missing_months'] + result[d]['missing_months'])), 'unit': 'ratio',
                           'reason': 'zero_denominator' if denominator is not None and Decimal(denominator) == 0 else 'missing_data' if value is None else None}
        return result

    def compare(current, baseline, first, last):
        c, b = current['value'], baseline['value']
        difference = Decimal(c) - Decimal(b) if c is not None and b is not None else None
        reason = ('missing_current' if c is None else 'missing_baseline' if b is None else
                  'incomplete' if not current['complete'] or not baseline['complete'] else
                  'zero_baseline' if current['unit'] != 'ratio' and Decimal(b) == 0 else None)
        change = None if reason else difference if current['unit'] == 'ratio' else difference / abs(Decimal(b))
        return {'value': text(change), 'difference': text(difference), 'baseline': b,
                'start': first, 'end': last, 'reason': reason,
                'missing_current_months': current['missing_months'], 'missing_baseline_months': baseline['missing_months'],
                'unit': 'pp' if current['unit'] == 'ratio' else 'ratio'}

    def compared(first, last, target_scope):
        count = len(months_between(first, last))
        current = aggregate(first, last, target_scope)
        prev_first, prev_last = shift(first, -count), shift(first, -1)
        y_first, y_last = shift(first, -12), shift(last, -12)
        prev, year = aggregate(prev_first, prev_last, target_scope), aggregate(y_first, y_last, target_scope)
        return {key: dict(value, mom=compare(value, prev[key], prev_first, prev_last),
                         yoy=compare(value, year[key], y_first, y_last)) for key, value in current.items()}

    totals = compared(start, end, scope)
    platform_scopes = [(p.upper() if p == 'amz' else 'eBay', {p: gs}) for p, gs in scope.items()]
    group_scopes = []
    for p, gs in scope.items():
        current_groups = gs or sorted({r['group_code'] for r in rows if r['platform'] == p and start <= r['stat_month'] <= end})
        group_scopes.extend((f'{p.upper() if p == "amz" else "eBay"} / {g}', {p: [g]}) for g in current_groups)
    platform_rows = [{'name': name, 'metrics': compared(start, end, s)} for name, s in platform_scopes]
    group_rows = [{'name': name, 'metrics': compared(start, end, s)} for name, s in group_scopes]
    periods = [(m, shift(m, step - 1)) for m in months[::step]]
    points = [compared(a, b, scope) for a, b in periods]
    platform_points = [(name, [compared(a, b, s) for a, b in periods]) for name, s in platform_scopes]
    group_points = [(name, [compared(a, b, s) for a, b in periods]) for name, s in group_scopes]
    metrics = {}
    for key, label in {**MONEY, **{k: v[2] for k, v in RATIOS.items()}}.items():
        metrics[key] = {'label': label, 'unit': totals[key]['unit'], 'summary': totals[key],
                        'total': [v[key]['value'] for v in points],
                        'year_total': [v[key]['yoy']['baseline'] for v in points],
                        'point_comparisons': [v[key] for v in points],
                        'platform_series': [{'name': name, 'values': [v[key]['value'] for v in values], 'comparisons': [v[key] for v in values]} for name, values in platform_points],
                        'series': [{'name': name, 'values': [v[key]['value'] for v in values], 'comparisons': [v[key] for v in values]} for name, values in group_points]}
    specials = {}
    for position, p in enumerate(scope):
        special_metrics = {}
        current = platform_rows[position]['metrics']
        platform_values = platform_points[position][1]
        own_groups = [(name, values) for (name, values), (_, s) in zip(group_points, group_scopes) if p in s]
        for key, label in SPECIAL_FIELDS[p].items():
            special_metrics[key] = {
                'label': label, 'unit': 'CNY', 'summary': current[key], 'share': current[f'{key}_share'],
                'total': [v[key]['value'] for v in platform_values],
                'year_total': [v[key]['yoy']['baseline'] for v in platform_values],
                'point_comparisons': [v[key] for v in platform_values],
                'series': [{'name': name, 'values': [v[key]['value'] for v in values], 'comparisons': [v[key] for v in values]} for name, values in own_groups],
            }
        specials[p] = {'fields': [{'key': k, 'label': label} for k, label in SPECIAL_FIELDS[p].items()],
                       'metrics': special_metrics,
                       'groups': [r for r, (_, s) in zip(group_rows, group_scopes) if p in s]}

    # Attribution includes groups present only in a comparison period. Missing is never treated as zero.
    attribution_groups = []
    relevant = {'current': (start, end), 'mom': (previous_start, previous_end), 'yoy': (year_start, year_end)}
    for p, gs in scope.items():
        candidates = gs or sorted({r['group_code'] for r in rows if r['platform'] == p and
                                  any(a <= r['stat_month'] <= b for a, b in relevant.values())})
        for g in candidates:
            attribution_groups.append({'name': f'{"eBay" if p == "ebay" else "AMZ"} / {g}',
                                       'metrics': compared(start, end, {p: [g]}), 'explicit': bool(gs),
                                       'periods': [kind for kind, (a, b) in relevant.items() if any(
                                           r['platform'] == p and r['group_code'] == g and a <= r['stat_month'] <= b for r in rows)]})
    contributions = {}
    for key in MONEY:
        contributions[key] = {}
        for kind in ('mom', 'yoy'):
            contributions[key][kind] = {}
            for dimension, records in [('platform', platform_rows), ('group', attribution_groups)]:
                items, unavailable = [], []
                for record in records:
                    if dimension == 'group' and not record['explicit'] and not any(
                            period in record['periods'] for period in ('current', kind)):
                        continue
                    metric = record['metrics'][key]
                    comparison = metric[kind]
                    item = {'name': record['name'], 'current': metric['value'], 'baseline': comparison['baseline'],
                            'difference': comparison['difference'], 'reason': comparison['reason']}
                    (items if comparison['reason'] in (None, 'zero_baseline') else unavailable).append(item)
                covered = sum_present([r['difference'] for r in items])
                total = totals[key][kind]['difference']
                residual = Decimal(total) - (covered or Decimal(0)) if total is not None else None
                contributions[key][kind][dimension] = {
                    'items': items, 'unavailable': unavailable, 'covered_difference': text(covered),
                    'total_difference': total, 'residual': text(residual),
                    'reconciled': not unavailable and totals[key][kind]['reason'] in (None, 'zero_baseline') and residual == 0,
                }
    return {'platform': platform, 'granularity': granularity, 'start': start, 'end': end,
            'months': [f'{a[:4]} Q{(int(a[-2:]) - 1) // 3 + 1}' if step == 3 else a for a, _ in periods],
            'periods': [{'start': a, 'end': b} for a, b in periods], 'metrics': metrics,
            'comparisons': {'current': [start, end], 'mom': [previous_start, previous_end], 'yoy': [year_start, year_end]},
            'breakdown': {'platform': platform_rows, 'group': group_rows}, 'raw_details': raw_details,
            'specials': specials, 'contributions': contributions}
