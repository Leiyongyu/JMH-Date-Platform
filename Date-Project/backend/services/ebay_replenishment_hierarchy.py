"""Paged hierarchy over a pinned replenishment generation, aggregated by MySQL.

Filters always select SKU leaves first. Parent quantities are leaf totals;
ratios use saved raw numerators. No source scan or formula rebuild on expand.
"""
import json
from decimal import Decimal

from backend.repositories import ebay_replenishment_review_repository as reviews

GROUP_SQL = "SUBSTRING_INDEX(base.sku,'-',2)"
SUM_FIELDS = (
    'sales_qty_7d', 'sales_qty_15d', 'sales_qty_30d', 'sales_qty',
    'gross_profit_amount', 'return_qty', 'return_amount',
    'warehouse_rent_amount_cny', 'forecast_sales_quantity',
    'forecast_sales_quantity_2', 'forecast_gross_profit_amount',
    'forecast_return_quantity', 'forecast_return_amount',
    'chengdu_in_transit_quantity', 'chengdu_sellable_quantity',
    'overseas_in_transit_quantity', 'overseas_sellable_quantity',
    'safety_stock_quantity', 'suggested_replenishment_quantity',
    'safety_stock_quantity_2', 'suggested_replenishment_quantity_2',
)
COMMON_FIELDS = ('product_name', 'principal_name', 'product_level', 'product_nature',
                 'chengdu_warehouse_to_warehouse_days', 'chengdu_qc_outbound_days',
                 'overseas_transit_to_listing_days')
RAW_FIELDS = ('sales_qty', 'gross_profit_amount', 'paid_amount', 'return_qty',
              'quality_return_qty', 'unclassified_return_qty')
MONTH_FIELDS = ('sales_qty', 'gross_profit_amount', 'return_qty', 'return_amount',
                'quality_return_qty', 'unclassified_return_qty')


def validate_parent(level, site, brand_core):
    if level not in ('site', 'product', 'sku'):
        raise ValueError('无效展示层级')
    if level in ('product', 'sku') and not str(site or '').strip():
        raise ValueError('展开时必须指定站点')
    if level == 'sku' and not str(brand_core or '').strip():
        raise ValueError('展开SKU时必须指定品牌和中间码')
    if level != 'sku' and brand_core:
        raise ValueError('此层级不接受品牌和中间码参数')


def node(item, kind, group=None, count=1):
    item = dict(item)
    site, sku = item['site'], item.get('sku', '')
    key = site if kind == 'site' else group if kind == 'product' else sku
    item.update(node_id=json.dumps([kind, site, key], ensure_ascii=False),
                node_kind=kind, brand_core=group,
                node_label=key, has_children=kind != 'sku', sku_count=count)
    return item


def _text(path):
    # Paths are constants from this module, never supplied by the client.
    return f"NULLIF(JSON_UNQUOTE(JSON_EXTRACT(base.payload,'$.{path}')),'null')"


def _number(path):
    return f'CAST({_text(path)} AS DECIMAL(38,10))'


def _sum(path, alias):
    value = _number(path)
    # Raw numerators must be complete for ratios; never infer missing values.
    return f'CASE WHEN COUNT({value})=COUNT(*) THEN SUM({value}) END AS `{alias}`'


def _ratio(top, bottom):
    if top is None or bottom is None or Decimal(bottom) == 0:
        return None
    return str(Decimal(top) / Decimal(bottom))


def aggregate_item(row, metadata, level):
    result = {key: row.get(key) for key in (*SUM_FIELDS, *COMMON_FIELDS)}
    result.update(site=row['site'], sku=row['group_key'] if level == 'product' else '',
                  overseas_inventory_age_days=row.get('overseas_inventory_age_days'),
                  sales_type=row.get('sales_type'))
    result['partial_fields'] = {key: int(row['sku_count']) - int(row.get('known_' + key, row['sku_count']))
                                for key in SUM_FIELDS
                                if int(row.get('known_' + key, row['sku_count'])) < int(row['sku_count'])}
    raw = {key: row.get('raw_' + key) for key in RAW_FIELDS}
    result['profit_rate'] = _ratio(raw['gross_profit_amount'], raw['paid_amount'])
    result['return_rate'] = _ratio(raw['return_qty'], raw['sales_qty'])
    result['sell_through_ratio'] = _ratio(
        None if raw['sales_qty'] is None else Decimal(raw['sales_qty']) / 3,
        result['overseas_sellable_quantity'] or 1)
    result['quality_return_summary'] = {
        key: raw[key] for key in ('return_qty', 'quality_return_qty', 'unclassified_return_qty')
    }
    result['quality_return_summary']['quality_return_rate'] = _ratio(raw['quality_return_qty'], raw['sales_qty'])
    result['monthly_metrics'] = []
    for i, month in enumerate(metadata.get('months', [])):
        metric = {key: row.get(f'm{i}_{key}') for key in MONTH_FIELDS}
        metric.update(month=month, quality_return_rate=_ratio(metric['quality_return_qty'], metric['sales_qty']))
        result['monthly_metrics'].append(metric)
    # Means use aggregated unrounded period values, avoiding sum-of-rounding.
    for output, metric in (
        ('forecast_sales_quantity', 'sales_qty'),
        ('forecast_gross_profit_amount', 'gross_profit_amount'),
        ('forecast_return_quantity', 'return_qty'),
        ('forecast_return_amount', 'return_amount'),
    ):
        values = [m[metric] for m in result['monthly_metrics']]
        result[output] = (str(sum(map(Decimal, values), Decimal(0)) / 3)
                          if len(values) == 3 and all(v is not None for v in values) else None)
    return node(result, level, row['group_key'] if level == 'product' else None, int(row['sku_count']))


def read_nodes(cursor, source, args, filters, metadata, page, size):
    from backend.services.ebay_replenishment_read_model import SORT_FIELDS, NUMERIC_FIELDS, _decode
    level = filters['hierarchy_level']
    args = list(args)
    if level == 'sku':
        source += f' AND {GROUP_SQL}=%s'
        args.append(filters['brand_core'].strip().upper())
        cursor.execute(f'SELECT COUNT(*) n {source}', args)
        total = int(cursor.fetchone()['n'])
        field = SORT_FIELDS.get(filters.get('sort_field'), 'sales_qty_30d')
        direction = 'ASC' if filters.get('sort_order') in ('asc', 'ascending') else 'DESC'
        cursor.execute(f"SELECT base.payload,COALESCE(sales_type.sales_type,'NORMAL') sales_type,{reviews.select_sql()} "
                       f'{source} ORDER BY base.{field} IS NULL,base.{field} {direction},base.sku LIMIT %s OFFSET %s',
                       [*args, size, (page-1)*size])
        items = []
        for row in cursor.fetchall():
            item = _decode(row['payload'])
            item.update(reviews.review_values(row), sales_type=row['sales_type'])
            items.append(node(item, 'sku', filters['brand_core']))
        return items, total

    grouping = 'base.site' if level == 'site' else f'base.site,{GROUP_SQL}'
    cursor.execute(f'SELECT COUNT(*) n FROM (SELECT 1 {source} GROUP BY {grouping}) groups_count', args)
    total = int(cursor.fetchone()['n'])
    columns = ['base.site', f"{GROUP_SQL} group_key" if level == 'product' else "'' group_key", 'COUNT(*) sku_count']
    # Same SUM semantics as the existing grade totals: sum computable SKU
    # values, retain NULL when none are known, expose missing counts to UI.
    columns += [f'SUM({_number(key)}) `{key}`' for key in SUM_FIELDS]
    columns += [f'COUNT({_number(key)}) `known_{key}`' for key in SUM_FIELDS]
    columns += [_sum('_aggregation_source.' + key, 'raw_' + key) for key in RAW_FIELDS]
    for key in COMMON_FIELDS:
        value = _text(key)
        columns.append(f'CASE WHEN COUNT({value})=COUNT(*) AND MIN({value})=MAX({value}) THEN MIN({value}) END `{key}`')
    columns.append(f"MAX({_number('overseas_inventory_age_days')}) overseas_inventory_age_days")
    columns.append("CASE WHEN MIN(COALESCE(sales_type.sales_type,'NORMAL'))=MAX(COALESCE(sales_type.sales_type,'NORMAL')) THEN MIN(COALESCE(sales_type.sales_type,'NORMAL')) END sales_type")
    for i in range(len(metadata.get('months', []))):
        columns += [_sum(f'monthly_metrics[{i}].{key}', f'm{i}_{key}') for key in MONTH_FIELDS]
    # Only singleton product groups need their leaf payload and live annotations.
    # MAX of a document is otherwise unnecessary for site/product summaries.
    if level == 'product':
        columns.append('CASE WHEN COUNT(*)=1 THEN MAX(CAST(base.payload AS CHAR)) END leaf_payload')
        columns += [f'MAX(review.{key}) {key}' for key in reviews.DEFAULTS]
    grouped = f"SELECT {','.join(columns)} {source} GROUP BY {grouping}"
    field = SORT_FIELDS.get(filters.get('sort_field'), 'sales_qty_30d')
    direction = 'ASC' if filters.get('sort_order') in ('asc', 'ascending') else 'DESC'
    if field in ('profit_rate', 'return_rate'):
        top, bottom = ('gross_profit_amount', 'paid_amount') if field == 'profit_rate' else ('return_qty', 'sales_qty')
        sort = f'(raw_{top}/NULLIF(raw_{bottom},0))'
    elif field == 'sku':
        sort = 'group_key'
    elif field in NUMERIC_FIELDS or field in ('site', 'product_name'):
        sort = field
    else:
        sort = 'sales_qty_30d'
    cursor.execute(f'SELECT * FROM ({grouped}) aggregated ORDER BY {sort} IS NULL,{sort} {direction},site,group_key LIMIT %s OFFSET %s',
                   [*args, size, (page-1)*size])
    items = []
    for row in cursor.fetchall():
        if level == 'product' and int(row['sku_count']) == 1:
            item = _decode(row['leaf_payload'])
            item.update(reviews.review_values(row), sales_type=row['sales_type'])
            items.append(node(item, 'sku', row['group_key']))
        else:
            items.append(aggregate_item(row, metadata, level))
    return items, total
