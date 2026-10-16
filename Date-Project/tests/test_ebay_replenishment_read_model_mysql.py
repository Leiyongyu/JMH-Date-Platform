"""Opt-in MySQL integration tests. Sources are read ONLY to clone small fixtures.

All mutations and cleanup target a newly created, uniquely named test database.
Run RUN_REPLENISHMENT_MYSQL_TESTS=1 with local MySQL access; never a deployment DB.
"""
import json
import os
import re
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pymysql
import pytest

from backend.config import settings
from backend.sql_statements import split_sql_statements
from backend.services import ebay_replenishment_read_model as model
from backend.services import ebay_replenishment_v2_service as legacy
from backend.services.ebay_replenishment_periods import rolling_periods

pytestmark=pytest.mark.skipif(os.getenv('RUN_REPLENISHMENT_MYSQL_TESTS')!='1',reason='opt-in isolated local MySQL tests')


@pytest.fixture
def isolated(monkeypatch):
    assert settings.mysql_host in ('localhost','127.0.0.1','::1')
    name='codex_repl_test_'+uuid4().hex[:12]
    assert re.fullmatch(r'codex_repl_test_[0-9a-f]{12}',name)
    source_db=legacy.repository._source_database()
    def connect(database):
        return pymysql.connect(host=settings.mysql_host,port=settings.mysql_port,user=settings.mysql_user,
            password=settings.mysql_password,database=database,charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,autocommit=False)
    admin=connect(settings.mysql_database)
    created=False
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            created=True
            sources={
                settings.mysql_database:{'dwd_ebay_sku_analysis_order':50,'ebay_sku_analysis_return_classification':10,
                    'dwd_performance_owner_rule':10000,'dwd_ebay_inventory_age_cost_snapshot':100,
                    'ods_goodcang_wh_inventory_storage_detail':100,'dim_lingxing_currency_month':10000},
                source_db:{'warehouse_inventory_detail':100,'ebay_product_listing':100,
                    'ebay_replenishment_v2_lead_time':100,'ebay_replenishment_v2_formula':100,
                    'ebay_replenishment_v2_forecast_rule':100,'ebay_replenishment_v2_level_rule':100,
                    'ebay_replenishment_v2_sales_type':100,'ebay_replenishment_v2_review':100}}
            for schema,tables in sources.items():
                for table,limit in tables.items():
                    cursor.execute(f'CREATE TABLE `{name}`.`{table}` LIKE `{schema}`.`{table}`')
                    order=' ORDER BY payment_time DESC' if table=='dwd_ebay_sku_analysis_order' else ''
                    cursor.execute(f'INSERT INTO `{name}`.`{table}` SELECT * FROM `{schema}`.`{table}`{order} LIMIT {limit}')
            admin.commit()
        @contextmanager
        def connection():
            c=connect(name)
            try: yield c
            finally: c.close()
        with connection() as c,c.cursor() as cur:
            migration=Path(__file__).resolve().parents[1]/'migrations/20261016_ebay_replenishment_read_model.sql'
            for sql in split_sql_statements(migration.read_text(encoding='utf-8')):
                if sql.strip(): cur.execute(sql)
            c.commit()
        for module in (model,legacy,legacy.repository,legacy.inventory_detail_repository,model.reviews,model.sales_types):
            monkeypatch.setattr(module,'db_connection',connection)
        for module in (legacy.repository,model.reviews,model.sales_types):
            monkeypatch.setattr(module,'_source_database',lambda:name)
        inventory=model.inventory_ctes
        monkeypatch.setattr(model,'inventory_ctes',lambda:inventory().replace('jmh_data_platform',f'`{name}`'))
        monkeypatch.setattr(legacy,'inventory_ctes',model.inventory_ctes)
        monkeypatch.setattr(legacy.sku_analysis_service,'_ensure_tables',lambda:None)
        monkeypatch.setattr(model,'reference_today',lambda:date(2026,10,16))
        monkeypatch.setattr(legacy,'rolling_periods',lambda:rolling_periods(date(2026,10,16)))
        yield connection
    finally:
        if created:
            # Only this fixture's exact newly-created database may be dropped.
            assert re.fullmatch(r'codex_repl_test_[0-9a-f]{12}',name)
            with admin.cursor() as cursor: cursor.execute(f'DROP DATABASE `{name}`')
        admin.close()


def execute(connection,sql,args=()):
    with connection() as c,c.cursor() as cursor:
        cursor.execute(sql,args)
        rows=cursor.fetchall() if cursor.description else []
        c.commit()
        return rows


def expire(connection):
    execute(connection,f'UPDATE {model.PREFIX}state SET checked_at=NULL WHERE state_id=1')


def assert_parity():
    old=legacy.list_replenishment(paginate=False,include_level_summary=True)
    new=model.query(paginate=False)
    assert old['level_summary']==new['level_summary']
    assert old['pagination']==new['pagination']
    lookup={(r['site'],r['sku']):r for r in new['items']}
    for row in old['items']:
        actual=lookup[(row['site'],row['sku'])]
        for field,value in row.items():
            assert actual[field]==value,(field,value,actual[field])
    return new


def test_parity_global_sort_filters_and_shared_result_storage(isolated):
    data=assert_parity()
    for field in ('safety_stock_quantity','suggested_replenishment_quantity','safety_stock_quantity_2','suggested_replenishment_quantity_2'):
        for direction in ('asc','desc'):
            expected=legacy._sort_derived_quantity(data['items'],field,direction.upper())[3:6]
            page=model.query(sort_field=field,sort_order=direction,page=2,page_size=3)
            assert [(r['site'],r['sku']) for r in page['items']]==[(r['site'],r['sku']) for r in expected]
    for level in ('S','A','B','C','--'):
        filtered=model.query(product_level=level,paginate=False)
        assert filtered['level_summary']==data['level_summary']
        assert all((r['product_level'] or '--')==level for r in filtered['items'])
    refreshed=model.query(refresh=True)
    assert refreshed['calculation_version']!=data['calculation_version']
    assert refreshed['data_generation']==data['data_generation']
    count=execute(isolated,f'SELECT COUNT(*) n FROM {model.PREFIX}result')[0]['n']
    assert count==len(data['items'])


def test_in_place_quantity_refund_and_delete_are_detected(isolated):
    first=assert_parity()
    execute(isolated,'UPDATE dwd_ebay_sku_analysis_order SET purchase_quantity=purchase_quantity+5,refund_quantity=refund_quantity+1 ORDER BY id LIMIT 1')
    expire(isolated)
    updated=assert_parity()
    assert updated['calculation_version']!=first['calculation_version']
    execute(isolated,'DELETE FROM dwd_ebay_sku_analysis_order ORDER BY id LIMIT 1')
    expire(isolated)
    deleted=assert_parity()
    assert deleted['calculation_version']!=updated['calculation_version']


def test_sort_uses_unrounded_rates_and_amounts(isolated):
    records = execute(isolated,'SELECT id FROM dwd_ebay_sku_analysis_order ORDER BY id LIMIT 2')
    for record,sku,profit in zip(records,('BMW-PRECISION-A','BMW-PRECISION-Z'),('1.000002','1.000001')):
        execute(isolated,"UPDATE dwd_ebay_sku_analysis_order SET inventory_sku=%s,site_name='德国',payment_time='2026-10-15',purchase_quantity=100,order_profit_cny=%s,paid_amount_cny=100,refund_quantity=0,refund_amount_cny=0 WHERE id=%s",
                (sku,profit,record['id']))
    for field in ('profitRate','grossProfitAmount'):
        for direction in ('asc','desc'):
            data = model.query(sku='BMW-PRECISION-',sort_field=field,sort_order=direction,paginate=False)
            old = legacy.list_replenishment(sku='BMW-PRECISION-',sort_field=field,sort_order=direction,paginate=False)
            assert [r['sku'] for r in data['items']] == [r['sku'] for r in old['items']]
            expected = ['BMW-PRECISION-Z','BMW-PRECISION-A']
            assert [r['sku'] for r in data['items']] == (expected if direction=='asc' else expected[::-1])
            assert all('_sort_values' not in r for r in data['items'])


def test_live_notes_confirmation_and_sales_type_do_not_rebuild_or_get_overwritten(isolated):
    data=model.query(paginate=False)
    row=data['items'][0]
    execute(isolated,f"INSERT INTO {model.reviews.TABLE}(site,sku,operations_note,operations_confirmed,operations_version) VALUES(%s,%s,'测试备注',1,1) ON DUPLICATE KEY UPDATE operations_note='测试备注',operations_confirmed=1,operations_version=operations_version+1",(row['site'],row['sku']))
    execute(isolated,f"INSERT INTO {model.sales_types.TABLE_NAME}(site,sku,sales_type) VALUES(%s,%s,'BRUSH') ON DUPLICATE KEY UPDATE sales_type='BRUSH'",(row['site'],row['sku']))
    filtered=model.query(site=row['site'],sku=row['sku'],exact_sku=True,operations_confirmed=True,sales_type='BRUSH')
    assert filtered['calculation_version']==data['calculation_version']
    assert filtered['items'][0]['operations_note']=='测试备注'
    refreshed=model.query(refresh=True,site=row['site'],sku=row['sku'],exact_sku=True)
    assert refreshed['items'][0]['operations_confirmed'] is True
    assert refreshed['items'][0]['operations_note']=='测试备注'


def test_failed_rebuild_keeps_previous_daily_and_generation(isolated,monkeypatch):
    old=model.query()
    before=execute(isolated,f'SELECT SUM(sales_qty) qty FROM {model.PREFIX}daily')
    execute(isolated,'UPDATE dwd_ebay_sku_analysis_order SET purchase_quantity=purchase_quantity+10 ORDER BY id LIMIT 1')
    original=model.build_items
    def fail(*_): raise RuntimeError('injected failure')
    monkeypatch.setattr(model,'build_items',fail)
    with pytest.raises(RuntimeError,match='injected failure'): model.query(refresh=True)
    assert execute(isolated,f'SELECT SUM(sales_qty) qty FROM {model.PREFIX}daily')==before
    assert execute(isolated,f'SELECT active_generation FROM {model.PREFIX}state')[0]['active_generation']==old['calculation_version']
    assert model.query(calculation_version=old['calculation_version'])['items']==old['items']
    monkeypatch.setattr(model,'build_items',original)
    expire(isolated)
    assert_parity()


def test_day_boundaries_used_sku_merge_and_excluded_prefixes(isolated):
    rows=execute(isolated,'SELECT id FROM dwd_ebay_sku_analysis_order ORDER BY id LIMIT 8')
    specs=[('BMW-TEST-001','德国',date(2026,10,15),2),
           ('BMW-TEST-001-YXR','德国',date(2026,10,15),3),
           ('BMW-TEST-001-RXY','英国',date(2026,10,15),7),
           ('BMW-TEST-001','德国',date(2026,10,16),100),
           ('BMW-TEST-001','德国',date(2026,7,18),11),
           ('BMW-TEST-001','德国',date(2026,7,17),100),
           ('AMZ-TEST-001','德国',date(2026,10,15),100),
           ('12PC-TEST-001','德国',date(2026,10,15),100)]
    for row,(sku,site,day,qty) in zip(rows,specs):
        execute(isolated,'UPDATE dwd_ebay_sku_analysis_order SET inventory_sku=%s,site_name=%s,payment_time=%s,purchase_quantity=%s WHERE id=%s',
                (sku,site,day,qty,row['id']))
    data=assert_parity()
    target={r['site']:r for r in data['items'] if r['sku']=='BMW-TEST-001'}
    assert target['德国']['sales_qty_7d']=='5'
    assert target['英国']['sales_qty_7d']=='7'
    assert sum(int(m['sales_qty']) for m in target['德国']['monthly_metrics'])==16
    assert not any(r['sku'].startswith(('AMZ','12PC')) for r in data['items'])


def test_rule_owner_lead_time_changes_and_retention(isolated):
    old=model.query(paginate=False)
    row=old['items'][0]
    execute(isolated,'INSERT INTO ebay_replenishment_v2_lead_time(site,sku,overseas_transit_to_listing_days) VALUES(%s,%s,123) ON DUPLICATE KEY UPDATE overseas_transit_to_listing_days=123',
            (row['site'],row['sku']))
    execute(isolated,"UPDATE dwd_performance_owner_rule SET principal_name='测试负责人' WHERE platform='ebay' AND stat_month='2026-10' AND rule_type='EBAY_BRAND' AND match_key=%s",(row['sku'].split('-')[0],))
    expire(isolated)
    new=assert_parity()
    assert new['calculation_version']!=old['calculation_version']
    assert next(r for r in new['items'] if (r['site'],r['sku'])==(row['site'],row['sku']))['overseas_transit_to_listing_days']==123
    for _ in range(21): model.query(refresh=True)
    assert execute(isolated,f'SELECT COUNT(*) n FROM {model.PREFIX}generation')[0]['n']==20
    with pytest.raises(ValueError,match='计算版本已过期'):
        model.query(calculation_version=old['calculation_version'])
    assert model.query()['pagination']['total']==new['pagination']['total']


def test_midnight_and_concurrent_refreshes(isolated,monkeypatch):
    old=model.query()
    barrier=Barrier(4)
    def refresh(_):
        barrier.wait()
        return model.query(refresh=True)['calculation_version']
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions=list(pool.map(refresh,range(4)))
    assert len(set(versions))==1
    assert versions[0]!=old['calculation_version']
    monkeypatch.setattr(model,'reference_today',lambda:date(2026,10,17))
    next_day=model.query()
    assert next_day['reference_date']=='2026-10-17'
    assert next_day['calculation_version']!=versions[0]
    assert model.query(calculation_version=old['calculation_version'])['reference_date']=='2026-10-16'


def test_owner_filter_options_totals_pagination_and_pinned_export(isolated):
    records=execute(isolated,'SELECT id FROM dwd_ebay_sku_analysis_order ORDER BY id LIMIT 3')
    for record,sku in zip(records,('FLL-TEST-001','CL-TEST-002','UNASSIGNED-TEST-003')):
        execute(isolated,"UPDATE dwd_ebay_sku_analysis_order SET inventory_sku=%s,site_name='德国',payment_time='2026-10-15' WHERE id=%s",(sku,record['id']))
    data=model.query(paginate=False)
    assert {'方黎力','陈丽','未分配'}.issubset(set(data['principals']))
    for principal in data['principals']:
        expected=[row for row in data['items'] if row['principal_name']==principal]
        exported=model.query(principal_name=principal,paginate=False,calculation_version=data['calculation_version'])
        assert exported['items']==expected
        assert exported['pagination']['total']==len(expected)
        assert exported['level_summary']==legacy._level_replenishment_summary(expected)
        page=model.query(principal_name=principal,page=2,page_size=1)
        assert page['items']==expected[1:2]
        assert page['principals']==data['principals']
        assert page['level_summary']==exported['level_summary']
        for grade in ('S','A','B','C','--'):
            selected=model.query(principal_name=principal,site='德国',product_level=grade,paginate=False)
            site_rows=[row for row in expected if row['site']=='德国']
            assert selected['level_summary']==legacy._level_replenishment_summary(site_rows)
            assert selected['items']==[row for row in site_rows if (row['product_level'] or '--')==grade]
    empty=model.query(principal_name="x' OR 1=1 --")
    assert empty['items']==[] and empty['pagination']['total']==0
    assert empty['principals']==data['principals']
