"""Shared clearance aggregation. Costs remain the stored costs, never repriced."""
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import re
from backend.services.ebay_inventory_core_code import normalize_core_code

BUCKETS = ('0_90', '91_180', '181_270', '271_365', '365_plus')
AGE_LABELS = ('0–90天（健康）', '91–180天（关注）', '181–270天（预警）',
              '271–365天（紧急）', '365天以上（严重）')
PREFIXES = tuple('inventory_' + bucket for bucket in BUCKETS) + ('inventory_181_plus', 'total_inventory')
FIELDS = tuple(f'{prefix}_{suffix}' for prefix in PREFIXES for suffix in ('qty', 'cost'))
COUNT_FIELDS = tuple(f'{prefix}_sku_count' for prefix in PREFIXES)
GROUP_CODES = ('EBAY-1', 'EU', 'US1', 'US2', 'US2-MJ', 'US1-ZXY')
ZERO = Decimal(0)


def previous_month(month):
    return (datetime.strptime(month, '%Y-%m') - timedelta(days=1)).strftime('%Y-%m')


def sku_key(row):
    """Product identity is core only; brand, supplier and condition do not split it."""
    parts = str(row.get('sku') or row.get('source_product_sku') or '').strip().upper().split('-')
    parts = [part.strip() for part in parts]
    if parts and re.fullmatch(r'[0-9]+PC', parts[0]):
        parts = parts[1:]
    return (normalize_core_code(parts[1]) or '') if len(parts) >= 2 and parts[0] else ''


def aggregate(rows):
    """Deduplicate middle codes after summing their stock in each bucket/scope.

    SKU counts cannot be summed across stores/sites/owners or age buckets.
    Unrecognizable middle codes retain quantity/cost but do not invent products.
    """
    result = {field: ZERO for field in FIELDS}
    quantities = {prefix: defaultdict(lambda: ZERO) for prefix in PREFIXES}
    result['source_row_count'] = 0
    missing_skus = 0
    unbucketed_rows = 0
    for row in rows:
        key = sku_key(row)
        values = {field: value if isinstance(value := row.get(field), Decimal) else Decimal(str(value or 0)) for field in FIELDS}
        result['source_row_count'] += int(row.get('source_row_count', 1) or 0)
        if not key and values['total_inventory_qty'] > 0:
            missing_skus += 1
        if any(sum((values[f'inventory_{bucket}_{suffix}'] for bucket in BUCKETS), ZERO)
               != values[f'total_inventory_{suffix}'] for suffix in ('qty', 'cost')):
            unbucketed_rows += 1
        for field in FIELDS:
            result[field] += values[field]
        if key:
            for prefix in PREFIXES:
                quantities[prefix][key] += values[prefix + '_qty']
    result.update({prefix + '_sku_count': sum(qty > 0 for qty in values.values())
                   for prefix, values in quantities.items()})
    result['missing_sku_rows'] = missing_skus
    result['unbucketed_rows'] = unbucketed_rows
    return result


def compare(rows, month, identity, *, previous_available=None):
    previous = previous_month(month)
    groups = defaultdict(lambda: defaultdict(list))
    names = {}
    for row in rows:
        key, name = identity(row)
        names[key] = name
        groups[row['pull_month']][key].append(row)
    has_previous = bool(groups[previous]) if previous_available is None else previous_available
    result = []
    for key in sorted(groups[month].keys() | groups[previous].keys()):
        current_rows, old_rows = groups[month][key], groups[previous][key]
        current, old = aggregate(current_rows), aggregate(old_rows)
        current.update(dimension_key=key, dimension_name=names[key],
                       previous_cost_month=previous if has_previous else None,
                       brands=sorted({r['brand_code'] for r in current_rows if r.get('brand_code')}),
                       previous_brands=sorted({r['brand_code'] for r in old_rows if r.get('brand_code')}))
        attach_comparison(current, old, has_previous)
        result.append(current)
    return result


def attach_comparison(current, old, has_previous):
    for bucket in (*BUCKETS, '181_plus'):
        cost = old[f'inventory_{bucket}_cost'] if has_previous else None
        current[f'previous_month_{bucket}_cost'] = cost
        current[f'inventory_{bucket}_variance'] = None if cost is None else cost - current[f'inventory_{bucket}_cost']


def total_metrics(rows, month):
    previous = previous_month(month)
    current = aggregate([r for r in rows if r['pull_month'] == month])
    old_rows = [r for r in rows if r['pull_month'] == previous]
    attach_comparison(current, aggregate(old_rows), bool(old_rows))
    return current
