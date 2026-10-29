"""Versioned read model: one atomic build, SQL paging, live independent annotations.

MySQL named locks coordinate all workers. Source checksums detect replacements,
deletes and in-place edits (not just MAX(id)/MAX(updated_at)). Ordinary reads check
at most every five seconds; explicit refresh bypasses that interval. No upstream
APIs, and no writes to source or manual-input tables.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from pymysql.err import ProgrammingError

from backend.database import db_connection
from backend.repositories import ebay_replenishment_v2_repository as repo
from backend.repositories import ebay_replenishment_review_repository as reviews
from backend.repositories import ebay_replenishment_sales_type_repository as sales_types
from backend.repositories import ebay_inventory_detail_repository as inventory_repo
from backend.services.ebay_order_product_key import product_orders_cte, product_sku
from backend.services.ebay_inventory_shared import inventory_ctes
from backend.services.ebay_replenishment_periods import rolling_periods, reference_today
from backend.services.ebay_replenishment_sales_type_service import normalize_filter

ENGINE_VERSION = 'rolling-read-model-v3'
PREFIX = 'dws_ebay_replenishment_'
NUMERIC_FIELDS = ('sales_qty_7d', 'sales_qty_15d', 'sales_qty_30d', 'sales_qty',
                  'gross_profit_amount', 'profit_rate', 'return_qty', 'return_rate',
                  'return_amount', 'forecast_sales_quantity_2', 'safety_stock_quantity',
                  'suggested_replenishment_quantity', 'safety_stock_quantity_2',
                  'suggested_replenishment_quantity_2')
SORT_FIELDS = dict(zip(
    ('site', 'sku', 'productName', 'salesQty7d', 'salesQty15d', 'salesQty30d', 'salesQty',
     'grossProfitAmount', 'profitRate', 'returnQty', 'returnRate', 'returnAmount',
     'forecastSalesQuantity2', 'safetyStockQty', 'suggestedReplenishmentQty',
     'safetyStockQty2', 'suggestedReplenishmentQty2'),
    ('site', 'sku', 'product_name', *NUMERIC_FIELDS)))
SORT_FIELDS.update({name: name for name in SORT_FIELDS.values()})
METRICS = ('sales_qty', 'gross_profit_amount', 'paid_amount', 'return_qty',
           'return_amount', 'quality_return_qty', 'unclassified_return_qty')
OWNER_SQL = "COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(base.payload,'$.principal_name')),''),'未分配')"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _decode(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _table_signature(cursor, table, columns, where='', params=()):
    # Aggregate 60-bit SHA-256 prefixes, count and xor. All identifiers are constants.
    cursor.execute(f'''SELECT COUNT(*) n,SUM(h) s,BIT_XOR(h) x FROM (
        SELECT CAST(CONV(SUBSTRING(SHA2(CAST(JSON_ARRAY({columns}) AS CHAR),256),1,15),16,10)
          AS UNSIGNED) h FROM {table} {where}) source_hash''', params)
    return cursor.fetchone()


def source_signatures(cursor, today, connection):
    order = _table_signature(cursor, 'dwd_ebay_sku_analysis_order',
        'id,site_name,inventory_sku,payment_time,platform_order_no,product_name_cn,purchase_quantity,'
        'paid_amount_cny,order_profit_cny,refund_quantity,refund_amount_cny,shipping_status')
    classification = _table_signature(cursor, 'ebay_sku_analysis_return_classification',
                                     'platform_order_no,big_category')
    daily = _digest([ENGINE_VERSION, order, classification])
    inventory_signature = _table_signature(cursor, f'`{repo._source_database()}`.warehouse_inventory_detail',
        'wid,sku,quantity_receive,product_valid_num,product_onway',
        'WHERE wid IN (18674,18675,18676,18699,18700,18701,18702)')
    # Hash the effective input projections, not all raw listing/rent rows. These
    # projections are also reused by the build in the same transaction.
    cursor.execute("SELECT match_key,principal_name,rule_type FROM dwd_performance_owner_rule WHERE platform='ebay' AND stat_month=%s AND rule_type='EBAY_BRAND' ORDER BY group_code,match_key",
                   (today.strftime('%Y-%m'),))
    inputs = dict(owners=cursor.fetchall(),
        lead_times=repo.lead_time_rows(connection=connection),
        formulas=repo.formula_by_level(connection=connection),
        listing=repo.first_listing_date_by_sku(connection=connection),
        ages=repo.overseas_inventory_age_by_sku(connection=connection),
        forecast=repo.forecast_rules(connection=connection),
        levels=repo.list_level_rules(allow_missing=True,connection=connection),
        rent=inventory_repo.read_rent_snapshot(connection=connection))
    signatures = [daily,inventory_signature]
    for value in inputs.values():
        signatures.append(sorted(value.items()) if isinstance(value,dict) else value)
    return daily, _digest([today, ENGINE_VERSION, signatures]), inputs


def rebuild_daily(cursor):
    # Only this derived table is replaced. Both replacement and generation publish
    # happen inside one transaction; failed builds leave the old version intact.
    cursor.execute(f'DELETE FROM {PREFIX}daily')
    cursor.execute(f'''WITH {product_orders_cte()}, ranked AS (
          SELECT product_orders.*,DATE(payment_time) sales_date,
            ROW_NUMBER() OVER (PARTITION BY DATE(payment_time),site_name,inventory_sku
                              ORDER BY payment_time DESC,id DESC) rn
          FROM product_orders WHERE payment_time IS NOT NULL)
        SELECT sales_date,site_name site,inventory_sku sku,
          SUM(COALESCE(purchase_quantity,0)) sales_qty,
          SUM(COALESCE(order_profit_cny,0)) gross_profit_amount,
          SUM(COALESCE(paid_amount_cny,0))-SUM(CASE WHEN shipping_status LIKE '%%已退款%%' THEN COALESCE(refund_amount_cny,0) ELSE 0 END) paid_amount,
          SUM(COALESCE(refund_quantity,0)) return_qty,
          SUM(CASE WHEN shipping_status LIKE '%%已退款%%' THEN COALESCE(refund_amount_cny,0) ELSE 0 END) return_amount,
          SUM(CASE WHEN TRIM(assignment.big_category)='产品质量问题' THEN COALESCE(refund_quantity,0) ELSE 0 END) quality_return_qty,
          SUM(CASE WHEN assignment.platform_order_no IS NULL THEN COALESCE(refund_quantity,0) ELSE 0 END) unclassified_return_qty,
          MAX(payment_time) latest_payment_time,MAX(CASE WHEN rn=1 THEN id END) latest_order_id,
          MAX(CASE WHEN rn=1 THEN product_name_cn END) product_name
        FROM ranked LEFT JOIN ebay_sku_analysis_return_classification assignment
          ON assignment.platform_order_no=ranked.platform_order_no
        GROUP BY sales_date,site_name,inventory_sku''')
    columns = ('sales_date','site','sku',*METRICS,'latest_payment_time','latest_order_id','product_name')
    daily_rows = [tuple(row[column] for column in columns) for row in cursor.fetchall()]
    for offset in range(0,len(daily_rows),200):
        cursor.executemany(f"INSERT INTO {PREFIX}daily ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))})", daily_rows[offset:offset+200])


def read_daily_rows(cursor, periods):
    columns, params = [], []
    for index, period in enumerate(periods, 1):
        for metric in METRICS:
            columns.append(f'SUM(CASE WHEN sales_date >= %s AND sales_date < %s THEN {metric} ELSE 0 END) {metric}_m{index}')
            params.extend([period['start_date'], period['end_date']])
    for days in (7, 15, 30):
        columns.append(f'SUM(CASE WHEN sales_date >= %s THEN sales_qty ELSE 0 END) sales_qty_{days}d')
        params.append(periods[0]['end_date'] - timedelta(days=days))
    params.extend([periods[-1]['start_date'], periods[0]['end_date']])
    cursor.execute(f'''WITH base AS (
        SELECT site,sku,{','.join(columns)} FROM {PREFIX}daily
        WHERE sales_date >= %s AND sales_date < %s GROUP BY site,sku
      ), latest AS (
        SELECT d.site,d.sku,d.product_name,
          ROW_NUMBER() OVER (PARTITION BY d.site,d.sku ORDER BY latest_payment_time DESC,latest_order_id DESC) rn
        FROM {PREFIX}daily d JOIN base b ON d.site=b.site AND d.sku=b.sku
      ), {inventory_ctes()}
      SELECT base.*,latest.product_name,
        COALESCE(i.chengdu_in_transit_quantity,0) chengdu_in_transit_quantity,
        COALESCE(i.chengdu_sellable_quantity,0) chengdu_sellable_quantity,
        COALESCE(i.overseas_in_transit_quantity,0) overseas_in_transit_quantity,
        COALESCE(i.overseas_sellable_quantity,0) overseas_sellable_quantity
      FROM base LEFT JOIN latest ON latest.site=base.site AND latest.sku=base.sku AND latest.rn=1
      LEFT JOIN inventory_summary i ON i.site COLLATE utf8mb4_unicode_ci=base.site
        AND i.sku COLLATE utf8mb4_unicode_ci=base.sku''', params)
    return cursor.fetchall()


def build_items(connection, periods, inputs):
    from backend.services import ebay_replenishment_v2_service as service
    with connection.cursor() as cursor:
        rows = read_daily_rows(cursor, periods)
    owners = service._ebay_rule_map(inputs['owners'])
    raw_lead_times = inputs['lead_times']
    lead_times = {key: (Decimal(row.get('chengdu_warehouse_to_warehouse_days') or 0)
                       +Decimal(row.get('chengdu_qc_outbound_days') or 0)
                       +Decimal(row['overseas_transit_to_listing_days'] if row.get('overseas_transit_to_listing_days') is not None
                                else repo.default_overseas_transit_days(key[0]) or 0))
                  for key,row in raw_lead_times.items()}
    items = service._assemble_items(rows, periods,
        lead_time_days=lead_times,formula_configs=inputs['formulas'],first_listing_dates=inputs['listing'],
        inventory_ages=inputs['ages'],forecast_rules=service.prepare_rules(inputs['forecast']),
        level_rules=service.level_service.prepare_levels(inputs['levels']))
    rent_rows, rates, rate_month, source_count = inputs['rent']
    rent, errors, _ = service.inventory_detail_service._rent_totals(rent_rows, rates, rate_month)
    for item, source_row in zip(items, rows):
        # Store unformatted numeric sort keys separately from the displayed
        # payload. Rounding prices/rates for display must not change their order.
        item['_sort_values'] = _source_sort_values(source_row)
        # Preserve exact numerators/denominators for grouped ratios. Rounded
        # displayed percentages must never be averaged or reverse-engineered.
        item['_aggregation_source'] = {
            metric: str(sum((Decimal(source_row.get(f'{metric}_m{i}') or 0)
                             for i in range(1, 4)), Decimal(0)))
            for metric in METRICS
        }
        key = item['site'], item['sku']
        lead = raw_lead_times.get(key, {})
        item['chengdu_warehouse_to_warehouse_days'] = lead.get('chengdu_warehouse_to_warehouse_days')
        item['chengdu_qc_outbound_days'] = lead.get('chengdu_qc_outbound_days')
        item['overseas_transit_to_listing_days'] = (lead['overseas_transit_to_listing_days']
            if lead.get('overseas_transit_to_listing_days') is not None else repo.default_overseas_transit_days(item['site']))
        item['principal_name'], item['owner_match_source'] = service._ebay_assignment(item['sku'], owners)
        rent_key = item['site'], service.inventory_detail_service.rent_sku_key(item['sku'])
        amount = None if not source_count or rent_key in errors else rent.get(rent_key, Decimal(0))
        item['warehouse_rent_amount_cny'] = None if amount is None else str(amount)
        for field in (*reviews.DEFAULTS, 'sales_type'):
            item.pop(field, None)
    return items


def _source_sort_values(row):
    values = {field: row.get(field) for field in ('sales_qty_7d','sales_qty_15d','sales_qty_30d')}
    values.update({field: row.get(f'{field}_m1') for field in
                   ('sales_qty','gross_profit_amount','return_qty','return_amount')})
    for field,numerator,denominator in (('profit_rate','gross_profit_amount','paid_amount'),
                                       ('return_rate','return_qty','sales_qty')):
        top = sum((Decimal(row.get(f'{numerator}_m{i}') or 0) for i in range(1,4)),Decimal(0))
        bottom = sum((Decimal(row.get(f'{denominator}_m{i}') or 0) for i in range(1,4)),Decimal(0))
        values[field] = top / bottom if bottom else None
    return values


def _state(cursor):
    cursor.execute(f'''SELECT s.*,g.reference_date,g.engine_version,g.source_signature,
        (s.checked_at > UTC_TIMESTAMP(6)-INTERVAL 5 SECOND) recently_checked
        FROM {PREFIX}state s LEFT JOIN {PREFIX}generation g ON g.generation=s.active_generation
        WHERE s.state_id=1''')
    state = cursor.fetchone()
    if not state:
        raise ValueError('补货2.0计算状态未初始化，请执行20261016_ebay_replenishment_read_model.sql')
    return state


def ensure_generation(force=False):
    today = reference_today()
    with db_connection() as connection, connection.cursor() as cursor:
        state = _state(cursor)
        if not force and _fresh(state, today) and state['recently_checked']:
            return state['active_generation']
        observed = state['active_generation']
        connection.rollback()
        cursor.execute("SELECT GET_LOCK(CONCAT(DATABASE(),':ebay-replenishment-build'),30) acquired")
        if cursor.fetchone()['acquired'] != 1:
            raise ValueError('补货数据正在重新计算，请稍后刷新')
        try:
            today = reference_today()
            # Fresh consistent read across both application databases. Do not call
            # helpers that commit independently while publishing this generation.
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            connection.begin()
            state = _state(cursor)
            if not force and _fresh(state, today) and state['recently_checked']:
                return state['active_generation']
            daily_sig, source_sig, inputs = source_signatures(cursor, today, connection)
            # A concurrent refresh may have completed while this caller waited.
            # Reuse it only after checking for edits committed after its snapshot.
            reuse_build = not force or state['active_generation'] != observed
            if reuse_build and _fresh(state, today) and state['source_signature'] == source_sig:
                cursor.execute(f'UPDATE {PREFIX}state SET checked_at=UTC_TIMESTAMP(6) WHERE state_id=1')
                connection.commit()
                return state['active_generation']
            if state['daily_signature'] != daily_sig:
                rebuild_daily(cursor)
            periods = rolling_periods(today)
            items = build_items(connection, periods, inputs)
            generation = uuid4().hex
            # Content-addressed rows are shared by identical refreshed versions.
            # Each refresh still calculates afresh and publishes its own timestamp.
            items.sort(key=lambda row:(row['site'],row['sku']))
            data_generation = _digest(items)[:32]
            metadata = dict(months=[p['month'] for p in periods], latest_complete_month=periods[0]['month'],
                reference_date=today.isoformat(), owner_rule_month=today.strftime('%Y-%m'),
                periods=[dict(label=p['month'],start_date=p['start_date'].isoformat(),end_date_exclusive=p['end_date'].isoformat()) for p in periods],
                sites=sorted({r['site'] for r in items}), source_check_interval_seconds=5,data_generation=data_generation)
            cursor.execute(f'INSERT INTO {PREFIX}generation VALUES(%s,%s,%s,%s,UTC_TIMESTAMP(6),%s)',
                           (generation, today, source_sig, ENGINE_VERSION, _json(metadata)))
            columns = ('generation','site','sku','product_name','product_level','product_nature',*NUMERIC_FIELDS,'payload')
            values = [(data_generation, r['site'],r['sku'],r['product_name'],r['product_level'],r['product_nature'],
                       *[r['_sort_values'].get(field,r.get(field)) for field in NUMERIC_FIELDS],
                       _json({key:value for key,value in r.items() if key!='_sort_values'})) for r in items]
            cursor.execute(f'SELECT 1 FROM {PREFIX}result WHERE generation=%s LIMIT 1',(data_generation,))
            if cursor.fetchone() is None:
                for offset in range(0, len(values), 200):
                    cursor.executemany(f"INSERT INTO {PREFIX}result ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))})", values[offset:offset+200])
            cursor.execute(f'UPDATE {PREFIX}state SET active_generation=%s,daily_signature=%s,checked_at=UTC_TIMESTAMP(6) WHERE state_id=1',
                           (generation,daily_sig))
            # Retain 20 full versions for page/export consistency. Only generated
            # data in these new tables is eligible for cleanup, never source data.
            cursor.execute(f'SELECT generation,metadata FROM {PREFIX}generation ORDER BY created_at DESC,generation DESC LIMIT 100000 OFFSET 20')
            for expired in cursor.fetchall():
                cursor.execute(f'DELETE FROM {PREFIX}generation WHERE generation=%s', (expired['generation'],))
                data_key = _decode(expired['metadata']).get('data_generation',expired['generation'])
                cursor.execute(f"SELECT 1 FROM {PREFIX}generation WHERE COALESCE(JSON_UNQUOTE(JSON_EXTRACT(metadata,'$.data_generation')),generation)=%s LIMIT 1",(data_key,))
                if cursor.fetchone() is None:
                    cursor.execute(f'DELETE FROM {PREFIX}result WHERE generation=%s', (data_key,))
            connection.commit()
            return generation
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.rollback()
            cursor.execute("SELECT RELEASE_LOCK(CONCAT(DATABASE(),':ebay-replenishment-build'))")


def _fresh(state, today):
    return state['active_generation'] and state['reference_date'] == today and state['engine_version'] == ENGINE_VERSION


def query(*, site=None, sku=None, product_name=None, product_level=None, product_nature=None,
          sales_type=None, operations_confirmed=None, page=1, page_size=50, sort_field=None,
          sort_order=None, paginate=True, include_level_summary=True, refresh=False,
          calculation_version=None, exact_sku=False, principal_name=None,
          hierarchy_level=None, brand_core=None, allowed_principals=None,
          operations_note_filled=None, development_note_filled=None):
    reviews.note_presence_filters(operations_note_filled, development_note_filled)
    if hierarchy_level is not None:
        from backend.services.ebay_replenishment_hierarchy import validate_parent
        validate_parent(hierarchy_level, site, brand_core)
    if calculation_version and not re.fullmatch(r'[0-9a-f]{32}', calculation_version):
        raise ValueError('无效计算版本，请刷新页面')
    sales_type = normalize_filter(sales_type)
    try:
        generation = calculation_version or ensure_generation(refresh)
        return read_generation(generation, site=site,sku=sku,product_name=product_name,
            product_level=product_level,product_nature=product_nature,sales_type=sales_type,
            operations_confirmed=operations_confirmed,page=page,page_size=page_size,
            operations_note_filled=operations_note_filled, development_note_filled=development_note_filled,
            sort_field=sort_field,sort_order=sort_order,paginate=paginate,
            include_level_summary=include_level_summary,exact_sku=exact_sku,principal_name=principal_name,
            hierarchy_level=hierarchy_level,brand_core=brand_core,allowed_principals=allowed_principals)
    except ProgrammingError as exc:
        if exc.args[0] == 1146 and PREFIX in str(exc):
            raise ValueError('补货2.0优化表未部署，请执行20261016_ebay_replenishment_read_model.sql') from exc
        raise


def read_generation(generation, **filters):
    page, size = max(int(filters['page']),1), min(max(int(filters['page_size']),1),200)
    clauses, args = ['base.generation=%s'], [generation]
    from backend.services.replenishment_data_scope import owner_predicate
    scope_sql, scope_args = owner_predicate(OWNER_SQL, filters.get('allowed_principals'))
    clauses.append(scope_sql)
    args.extend(scope_args)
    principal = (filters.get('principal_name') or '').strip()
    if principal:
        clauses.append(f'{OWNER_SQL}=%s')
        args.append(principal)
    for field in ('site','product_nature'):
        value = (filters.get(field) or '').strip()
        if value:
            clauses.append(f'base.{field}=%s')
            args.append(value)
    for field, value in [('sku',product_sku(filters.get('sku'))),('product_name',(filters.get('product_name') or '').strip())]:
        if value:
            exact = field=='sku' and filters['exact_sku']
            clauses.append(f'base.{field} ' + ('=%s' if exact else 'LIKE %s'))
            args.append(value if exact else f'%{value}%')
    if filters.get('sales_type'):
        clauses.append("COALESCE(sales_type.sales_type,'NORMAL')=%s")
        args.append(filters['sales_type'])
    if filters.get('operations_confirmed') is not None:
        clauses.append('COALESCE(review.operations_confirmed,0)=%s')
        args.append(int(filters['operations_confirmed']))
    note_clauses, note_args = reviews.note_presence_filters(
        filters.get('operations_note_filled'), filters.get('development_note_filled'))
    clauses.extend(note_clauses)
    args.extend(note_args)
    joins = sales_types.join_sql()+' '+reviews.join_sql()
    source = f'FROM {PREFIX}result base {joins} WHERE '+ ' AND '.join(clauses)
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        connection.begin()
        cursor.execute(f'SELECT metadata,created_at FROM {PREFIX}generation WHERE generation=%s', (generation,))
        header = cursor.fetchone()
        if header is None:
            raise ValueError('计算版本已过期，请刷新页面后重试导出')
        result = _decode(header['metadata'])
        args[0] = result.get('data_generation',generation)
        # Options cover the complete saved version, not the current page/filter.
        # Read from payload so existing generations need no migration or rebuild.
        cursor.execute(f'''SELECT DISTINCT {OWNER_SQL} principal_name
            FROM {PREFIX}result base WHERE base.generation=%s AND {scope_sql} ORDER BY principal_name''', (args[0], *scope_args))
        result['principals'] = [row['principal_name'] for row in cursor.fetchall()]
        if filters.get('allowed_principals') is not None:
            cursor.execute(f'SELECT DISTINCT base.site FROM {PREFIX}result base WHERE base.generation=%s AND {scope_sql} ORDER BY base.site', (args[0], *scope_args))
            result['sites'] = [row['site'] for row in cursor.fetchall()]
        # The summary and returned page use the same consistent DB snapshot;
        # live confirmation/type filters are applied before the grade filter.
        cursor.execute(f'''SELECT COALESCE(NULLIF(base.product_level,''),'--') grade,COUNT(*) n,
            SUM(base.suggested_replenishment_quantity) q1,SUM(base.suggested_replenishment_quantity_2) q2
            {source} GROUP BY base.product_level''', args)
        summary = {g:dict(suggested_replenishment_quantity='0',suggested_replenishment_quantity_2='0') for g in ('ALL','S','A','B','C','--')}
        counts = {}
        for row in cursor.fetchall():
            grade = row['grade']
            counts[grade] = int(row['n'])
            for key,value in [('suggested_replenishment_quantity',row['q1']),('suggested_replenishment_quantity_2',row['q2'])]:
                summary.setdefault(grade,{})[key] = format(Decimal(value or 0),'.0f')
                summary['ALL'][key] = format(Decimal(summary['ALL'][key])+Decimal(value or 0),'.0f')
        level = (filters.get('product_level') or '').strip().upper()
        total = counts.get(level,0) if level else sum(counts.values())
        if level:
            source += " AND COALESCE(NULLIF(base.product_level,''),'--')=%s"
            args.append(level)
        if filters.get('hierarchy_level'):
            from backend.services.ebay_replenishment_hierarchy import read_nodes
            items, node_total = read_nodes(cursor, source, args, filters, result, page, size)
            result.update(items=items, calculation_version=generation,
                calculated_at=str(header['created_at']), level_summary=summary,
                sales_type_available=True, review_available=True,
                pagination=dict(page=page, page_size=size, total=node_total),
                matched_sku_count=total)
            return result
        field = SORT_FIELDS.get(filters.get('sort_field') or '', 'sales_qty_30d')
        direction = 'ASC' if str(filters.get('sort_order') or '').lower() in ('asc','ascending') else 'DESC'
        order = f'base.{field} {direction},base.site,base.sku'
        if field in NUMERIC_FIELDS[9:]:
            order = f'base.{field} IS NULL,'+order
        limit = ' LIMIT %s OFFSET %s' if filters['paginate'] else ''
        parameters = [*args,size,(page-1)*size] if limit else args
        cursor.execute(f"SELECT base.payload,COALESCE(sales_type.sales_type,'NORMAL') sales_type,{reviews.select_sql()} {source} ORDER BY {order}{limit}", parameters)
        items = []
        for row in cursor.fetchall():
            item = _decode(row['payload'])
            item.update(reviews.review_values(row))
            item['sales_type'] = row['sales_type']
            items.append(item)
    result.update(items=items,calculation_version=generation,calculated_at=str(header['created_at']),
        level_summary=summary if filters['include_level_summary'] else None,
        sales_type_available=True,review_available=True,
        pagination=dict(page=page if filters['paginate'] else 1,page_size=size if filters['paginate'] else total,total=total))
    return result
