"""Opt-in MySQL fixtures. Mutations are confined to a fresh, disposable schema."""
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import pymysql
import pytest
from backend.config import settings
from backend.repositories import ebay_mixed_sales_price_repository as prices
from backend.services import ebay_mixed_sales_service as service
from backend.services import mixed_sales_price_service as comparison
from backend.services import mixed_sales_amz_store_service as store_service
from backend.services import mixed_sales_sql
from backend.services import mixed_sales_age_service as ages
from backend.services.mixed_sales_site_detail_service import list_site_details
from backend.sql_statements import split_sql_statements


@pytest.fixture
def isolated(monkeypatch):
    if os.getenv('RUN_MIXED_PRICE_MYSQL_TESTS') != '1':
        pytest.skip('opt-in local MySQL fixture')
    assert settings.mysql_host in ('localhost', '127.0.0.1')
    schema = 'codex_mixed_union_' + uuid4().hex[:12]
    assert re.fullmatch(r'codex_mixed_union_[0-9a-f]{12}', schema)
    def connect(db=None):
        return pymysql.connect(host=settings.mysql_host,port=settings.mysql_port,user=settings.mysql_user,
            password=settings.mysql_password,database=db,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
    admin = connect()
    created = False
    try:
        with admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            created = True
        @contextmanager
        def connection():
            conn = connect(schema)
            try: yield conn
            finally: conn.close()
        with connection() as conn,conn.cursor() as cur:
            definitions = [
                'warehouse(wid INT,name VARCHAR(100))',
                'amz_warehouse_inventory_detail(wid INT,sku VARCHAR(100),sync_time DATETIME)',
                'amz_product_listing(sid INT,seller_sku VARCHAR(100),local_sku VARCHAR(100),local_name VARCHAR(100),small_image_url VARCHAR(100),marketplace VARCHAR(30),sync_time DATETIME,price DECIMAL(20,8),currency_code VARCHAR(16),UNIQUE KEY(sid,seller_sku))',
                'amz_product_performance_inventory(sid INT,seller_sku VARCHAR(100),local_sku VARCHAR(100),fba_stock INT,fba_inbound INT,sync_time DATETIME,UNIQUE KEY(sid,seller_sku))',
                'amz_restock_summary(sid INT,msku VARCHAR(100),sales_30d INT,node_type INT,updated_at DATETIME)',
                'ods_lingxing_amz_listing_latest(sid BIGINT,seller_sku LONGTEXT COLLATE utf8mb4_bin,thirty_volume LONGTEXT,is_delete TINYINT DEFAULT 0,status TINYINT DEFAULT 1,sync_batch_id VARCHAR(64),pulled_at DATETIME,KEY idx_sid_seller(sid,seller_sku(191)))',
                'ods_lingxing_amz_listing_state(id TINYINT PRIMARY KEY,sync_batch_id VARCHAR(64),pulled_at DATETIME)',
                'shop_list(sid INT,store_name VARCHAR(100),platform_code VARCHAR(30),currency VARCHAR(16),country_code VARCHAR(16))',
                'dws_ebay_replenishment_generation(generation CHAR(32),metadata JSON,created_at DATETIME)',
                'dws_ebay_replenishment_result(generation CHAR(32),sku VARCHAR(100),site VARCHAR(30),product_name VARCHAR(100),sales_qty_7d DECIMAL(24,6),sales_qty_15d DECIMAL(24,6),sales_qty_30d DECIMAL(24,6),payload JSON)',
                'ods_lingxing_amz_fba_inventory_raw(pull_month VARCHAR(7),sku VARCHAR(100),sid VARCHAR(20),inv_age_0_to_90_days INT,inv_age_91_to_180_days INT,inv_age_181_to_270_days INT,inv_age_271_to_365_days INT,inv_age_365_plus_days INT,pulled_at DATETIME,seller_group_name VARCHAR(1000),share_type INT)',
                'ods_goodcang_inventory_age_latest(product_sku VARCHAR(100),warehouse_code VARCHAR(20),warehouse_age INT,iba_quantity INT,raw_json JSON,pulled_at DATETIME)',
                'ods_lingxing_product_procurement_monthly(snapshot_month VARCHAR(7),sku VARCHAR(100))',
            ]
            for ddl in definitions:
                cur.execute('CREATE TABLE ' + ddl)
            path = Path(__file__).resolve().parents[1]/'migrations/20261028_ebay_mixed_sales_prices.sql'
            for sql in split_sql_statements(path.read_text(encoding='utf-8')):
                if 'CREATE TABLE' in sql:
                    cur.execute(sql)
            cur.execute("INSERT INTO warehouse VALUES(1,'W1'),(2,'W2')")
            cur.execute("INSERT INTO amz_warehouse_inventory_detail VALUES(1,'SKU-BOTH',NOW()),(2,'SKU-BOTH',NOW()),(1,'SKU-AMZ',NOW()),(1,'SKU-ZERO',NOW())")
            cur.execute("INSERT INTO shop_list VALUES(1,'S1','10001','GBP','UK'),(2,'S2','10001','GBP','GB'),(3,'S3','10001','EUR','DE'),(4,'S4','10001','USD','US')")
            cur.execute("INSERT INTO amz_product_listing VALUES(1,'B1','SKU-BOTH','Both','img','英国',NOW(),20,'GBP'),(2,'B2','SKU-BOTH','Both','img','GB',NOW(),100,'GBP'),(3,'B3','SKU-BOTH','Both','img','德国',NOW(),50,'EUR'),(4,'B4','SKU-BOTH','Both','img','',NOW(),0,'USD'),(1,'A1','SKU-AMZ','Amazon','img','英国',NOW(),40,'GBP'),(1,'Z1','SKU-ZERO','Zero','img','英国',NOW(),0,'GBP'),(1,'UNKNOWN','SKU-BOTH','Both','img','未知站点',NOW(),7,'EUR')")
            cur.execute("INSERT INTO amz_product_performance_inventory VALUES(1,'B1','SKU-BOTH',10,2,NOW()),(2,'B2','SKU-BOTH',7,1,NOW()),(1,'Z1','SKU-ZERO',0,0,NOW())")
            # Old restock values deliberately disagree with the new listing source.
            cur.execute("INSERT INTO amz_restock_summary VALUES(1,'B1',999,1,NOW()),(1,'B1',777,2,NOW()),(2,'B2',888,3,NOW()),(1,'Z1',99,3,NOW())")
            cur.execute("INSERT INTO ods_lingxing_amz_listing_state VALUES(1,'published','2026-10-29 10:00:00')")
            cur.execute("""INSERT INTO ods_lingxing_amz_listing_latest VALUES
                (1,'B1','5',0,1,'published',NOW()),(1,'B1','3',0,1,'published',NOW()),
                (1,'B1','999',0,1,'old-batch',NOW()),(1,'B1','888',1,1,'published',NOW()),
                (2,'B2','6',0,0,'published',NOW()),(1,'Z1','0',0,1,'published',NOW())""")
            cur.execute('INSERT INTO dws_ebay_replenishment_generation VALUES(%s,%s,NOW())',('a'*32,json.dumps({'data_generation':'b'*32,'sites':['英国','德国']})))
            payload = json.dumps(dict.fromkeys(service.STOCK_FIELDS.values(),2))
            cur.execute("INSERT INTO dws_ebay_replenishment_result VALUES(%s,'SKU-BOTH','英国','Both',1,2,3,%s),(%s,'SKU-EBAY','德国','eBay',2,3,4,%s)",('b'*32,payload,'b'*32,payload))
            cur.execute("INSERT INTO dws_ebay_replenishment_result VALUES(%s,'SKU-ZERO','德国','Zero',0,0,0,%s),(%s,'SKU-WAREHOUSE','法国','Warehouse only',0,0,0,%s)",('b'*32,payload,'b'*32,payload))
            cur.execute("INSERT INTO amz_warehouse_inventory_detail VALUES(1,'SKU-WAREHOUSE',NOW())")
            conn.commit()
        for module in (service, comparison, prices, store_service, ages):
            monkeypatch.setattr(module, 'db_connection', connection)
        monkeypatch.setattr(mixed_sales_sql, '_source_database', lambda: schema)
        monkeypatch.setattr(ages, '_source_database', lambda: schema)
        monkeypatch.setattr(service.model, 'ensure_generation', lambda: 'a'*32)
        yield connection
    finally:
        if created:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE `{schema}`')
        admin.close()


def test_both_lists_contain_intersection_and_keep_own_metrics_and_sql_pagination(isolated):
    expected = {'SKU-BOTH','SKU-ZERO'}
    for platform in ('amz','ebay'):
        result = service.list_sales(platform=platform)
        assert result['total'] == 2 and {r['sku'] for r in result['items']} == expected
        rows = [service.list_sales(platform=platform,sort_field='sku',sort_order='asc',page_size=1,page=p)['items'][0]['sku'] for p in range(1,3)]
        assert rows == sorted(expected)
        assert service.list_sales(platform=platform,page_size=1,page=3)['items'] == []
        for absent in ('SKU-AMZ','SKU-EBAY','SKU-WAREHOUSE'):
            assert service.list_sales(platform=platform,sku=absent)['total'] == 0
            assert list_site_details(platform=platform,sku=absent)['total'] == 0
    amz = service.list_sales(platform='amz',sku='SKU-BOTH')['items'][0]
    assert amz['fbaTotalInventory'] == 20 and amz['sales30d'] == 11
    assert amz['salesSyncTime'] == datetime(2026,10,29,10)
    zero = service.list_sales(platform='amz',sku='SKU-ZERO')['items'][0]
    assert zero['fbaTotalInventory'] == 0 and zero['sales30d'] == 0
    assert service.list_sales(platform='amz',sid=1)['total'] == 2
    assert service.list_sales(platform='amz',sid=2)['total'] == 1
    assert service.list_sales(site='GB')['total'] == 2
    assert service.list_sales(product_name='eBay')['total'] == 0
    assert 'FR' not in service.list_sales()['sites']  # excluded warehouse-only SKU
    assert service.list_sales(sku="x' OR 1=1 --")['total'] == 0
    assert service.list_sales(sku='SKU-AMZ',details=True)['items'] == []
    detail = service.list_sales(platform='amz',sku='SKU-BOTH',details=True)['items']
    assert sum(r['sales30d'] or 0 for r in detail) == 11
    selected_detail = service.list_sales(platform='amz',sku='SKU-BOTH',site='英国',details=True)['items']
    assert {r['site'] for r in selected_detail} == {'UK'}


def test_listing_sales_for_shared_mskus_stay_with_each_sid_and_site(isolated):
    sku='PSA-60008-0128'
    sites={101:('DE',14),102:('FR',18),103:('ES',8),104:('IT',6),105:('BE',4),106:('NL',1),
           201:('DE',7),202:('FR',4),206:('NL',2),107:('UK',7)}
    with isolated() as conn,conn.cursor() as cur:
        cur.execute('INSERT INTO amz_warehouse_inventory_detail VALUES(1,%s,NOW())',(sku,))
        for sid,(site,sales) in sites.items():
            msku='PSA-B' if sid>=200 else 'PSA-A'
            currency='GBP' if site=='UK' else 'EUR'
            cur.execute("INSERT INTO shop_list VALUES(%s,%s,'10001',%s,%s)",(sid,'Store '+str(sid),currency,site))
            cur.execute('''INSERT INTO amz_product_listing(sid,seller_sku,local_sku,local_name,marketplace,price,currency_code)
                VALUES(%s,%s,%s,'Product',%s,10,%s)''',(sid,msku,sku,site,currency))
            cur.execute('INSERT INTO amz_restock_summary VALUES(%s,%s,%s,%s,NOW())',
                        (sid,msku,sales,3 if site=='UK' else 2))
            cur.execute('''INSERT INTO ods_lingxing_amz_listing_latest(sid,seller_sku,thirty_volume,sync_batch_id)
                VALUES(%s,%s,%s,'published')''',(sid,msku,str(sales)))
        cur.execute("INSERT INTO amz_restock_summary VALUES(101,'PSA-A',51,1,NOW()),(201,'PSA-B',13,1,NOW())")
        cur.execute("INSERT INTO dws_ebay_replenishment_result(generation,sku,site,product_name) VALUES(%s,%s,'英国','Product')",('b'*32,sku))
        conn.commit()
    expected={'DE':21,'FR':22,'ES':8,'IT':6,'BE':4,'NL':3,'UK':7}
    data=service.list_sales(platform='amz',sku=sku,details=True)
    assert {r['site']:r['sales30d'] for r in data['items']}==expected
    assert service.list_sales(platform='amz',sku=sku)['items'][0]['sales30d']==71
    for platform in ('amz','ebay'):
        displayed=list_site_details(platform=platform,sku=sku)['items']
        if platform == 'amz':
            summed = {}
            for row in displayed:
                summed[row['site']] = summed.get(row['site'], 0) + row['amzSales30d']
            assert summed == expected
            assert len(displayed) == 10
        else:
            assert {r['site']:r['amzSales30d'] for r in displayed}==expected
        assert all(r['ebaySales30d'] is None for r in displayed)


def test_listing_sales_cast_before_dedup_and_keep_invalid_or_unmatched_values_null(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.executemany('''INSERT INTO ods_lingxing_amz_listing_latest
            (sid,seller_sku,thirty_volume,sync_batch_id) VALUES(%s,%s,%s,'published')''', [
                (1,'B1','9'),(1,'B1',' 12 '),(1,'B1','invalid'),
                (1,'B1-YXR','999'),(1,'b1','999'),(999,'B1','999'),
                (3,'B3','bad'),(3,'B3','null'),(3,'B3','1e3'),
                (3,'B3','999999999999999999999999999999'),
                (4,'B4',None),(4,'B4','-1'),(1,'UNKNOWN',''),
            ])
        conn.commit()
    summary=service.list_sales(platform='amz',sku='SKU-BOTH')['items'][0]
    assert summary['sales30d']==18 and summary['salesMatchedCount']==2
    stores=store_service.list_store_inventory(sku='SKU-BOTH')
    assert sum(r['sales30d'] or 0 for r in stores)==18
    assert next(r for r in stores if r['sid']==1 and r['site']=='UK')['sales30d']==12
    assert all(r['sales30d'] is None for r in stores if r['site'] in ('DE','US',None))
    sorted_rows=list_site_details(platform='amz',sku='SKU-BOTH',sort_field='amzSales30d')['items']
    assert sorted_rows[0]['sid']==1 and sorted_rows[0]['amzSales30d']==12
    assert service.list_sales(platform='amz',sku='SKU-ZERO')['items'][0]['sales30d']==0


def test_unpublished_listing_snapshot_does_not_fall_back_to_restock_sales(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.execute('DELETE FROM ods_lingxing_amz_listing_state')
        conn.commit()
    summary=service.list_sales(platform='amz',sku='SKU-BOTH')['items'][0]
    assert summary['sales30d'] is None and summary['salesMatchedCount']==0
    assert summary['salesSyncTime'] is None and summary['fbaTotalInventory']==20
    assert all(r['amzSales30d'] is None for r in list_site_details(sku='SKU-BOTH')['items'])


def test_native_price_ranges_exact_site_currency_numeric_values_and_variants(isolated):
    now = datetime(2026,10,28)
    def record(item_id,price,currency='GBP',site='UK',sku='SKU-BOTH',variants=None):
        return dict(seller=dict(userId='a',username='seller'),item=dict(item_id=item_id,sku=sku,
            site=site,title='T',current_price=dict(value=price,currency=currency),
            buy_it_now_price=dict(value=None,currency=None),variations=variants or []))
    items = [record('1','100'),record('2','20',site='GB'),record('3','15','USD'),
             record('4','70','EUR','FR'),record('5','9','EUR','未知站点'),
             record('6','bad'),record('7','999',sku=None,variants=[dict(sku='SKU-BOTH-YXR',price=dict(value='5.12345678',currency='GBP'))]),
             record('8','0',sku='SKU-EBAY')]
    account = dict(userId='a',username='seller',row_count=len(items),published_at=now)
    prices.replace_snapshots(items,[account],batch_id='test',pulled_at=now)
    data = comparison.list_price_ranges(sku='SKU-BOTH')
    keyed = {(r['site'],r['currency'],r['unmatchedPlatform']):r for r in data['items']}
    uk = keyed['UK','GBP','']
    assert (uk['amzMinPrice'],uk['amzMaxPrice']) == (Decimal(20),Decimal(100))
    assert (uk['ebayMinPrice'],uk['ebayMaxPrice']) == (Decimal('5.12345678'),Decimal(100))
    assert keyed['UK','USD','']['amzMinPrice'] is None
    assert keyed['DE','EUR','']['ebayMinPrice'] is None  # FR EUR is not DE EUR
    assert keyed['FR','EUR','']['amzMinPrice'] is None
    assert keyed[None,'EUR','AMZ']['ebayMinPrice'] is None
    assert keyed[None,'EUR','EBAY']['amzMinPrice'] is None
    assert keyed['US','USD','']['amzMinPrice'] == 0  # country_code fallback
    assert len(comparison.list_price_ranges(sku='SKU-BOTH',site='英国')['items']) == 2
    assert comparison.list_price_ranges(sku='SKU-NONE')['total'] == 0
    assert comparison.list_price_ranges(sku='SKU-EBAY')['items'][0]['ebayMinPrice'] == 0
    old = comparison.list_price_ranges(sku='SKU-BOTH',stat_month='2026-09')
    assert all(r['ebayMinPrice'] is None for r in old['items'])
    assert comparison.list_price_ranges(sku='SKU-BOTH',page_size=2,page=2)['total'] == data['total']
    assert len(comparison.list_price_ranges(sku='SKU-BOTH',page_size=2,page=2)['items']) == 2
    inline = list_site_details(sku='SKU-BOTH',sort_field='site',sort_order='asc')
    uk_inline=next(r for r in inline['items'] if r['site']=='UK' and r['currency']=='GBP')
    assert uk_inline['sid']==1 and uk_inline['storeName']=='S1'
    assert uk_inline['fbaTotalInventory']==12 and uk_inline['sales30d']==5
    assert uk_inline['amzSales30d']==5 and uk_inline['ebaySales30d']==3
    assert uk_inline['ebayMinPrice']==Decimal('5.12345678') and uk_inline['amzMaxPrice']==20
    other=next(r for r in inline['items'] if r.get('sid')==2)
    assert other['fbaTotalInventory']==8 and other['amzSales30d']==6 and other['amzMinPrice']==100
    france=next(r for r in inline['items'] if r['site']=='FR')
    assert france['fbaStock'] is None and france['ebayMinPrice']==70
    inline_page=list_site_details(sku='SKU-BOTH',page_size=1,page=2,sort_field='site',sort_order='asc')
    assert inline_page['total']==inline['total'] and inline_page['items']==inline['items'][1:2]
    ebay_inline=list_site_details(platform='ebay',sku='SKU-BOTH',site='英国',stat_month='2026-10')
    assert {r['site'] for r in ebay_inline['items']}=={'UK'}
    row=next(r for r in ebay_inline['items'] if r['currency']=='GBP')
    assert row['totalInventory']==8 and row['sales30d']==3
    assert row['amzSales30d']==11 and row['ebaySales30d']==3
    assert row['ebayMinPrice']==Decimal('5.12345678') and row['amzMaxPrice']==100
    assert 'sales7d' not in row and 'sales15d' not in row
    ebay_no_price=list_site_details(platform='ebay',sku='SKU-EBAY',site='德国',stat_month='2026-10')
    assert ebay_no_price['total']==0 and ebay_no_price['items']==[]


def test_store_groups_multiple_mskus_without_warehouse_multiplication(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.execute("INSERT INTO amz_product_listing VALUES(1,'B1-SECOND','SKU-BOTH','Both','img','UK',NOW(),30,'GBP')")
        cur.execute("INSERT INTO amz_product_performance_inventory VALUES(1,'B1-SECOND','SKU-BOTH',1,2,NOW())")
        cur.execute("INSERT INTO amz_restock_summary VALUES(1,'B1-SECOND',4,2,NOW())")
        cur.execute("INSERT INTO ods_lingxing_amz_listing_latest(sid,seller_sku,thirty_volume,sync_batch_id) VALUES(1,'B1-SECOND','4','published')")
        conn.commit()
    rows=list_site_details(sku='SKU-BOTH',site='UK')['items']
    assert len(rows)==2
    keyed={r['sid']:r for r in rows}
    assert keyed[1]['sales30d']==9 and keyed[1]['fbaTotalInventory']==15
    assert keyed[1]['amzMinPrice']==20 and keyed[1]['amzMaxPrice']==30
    assert keyed[2]['sales30d']==6 and keyed[2]['fbaTotalInventory']==8
    assert sum(r['sales30d'] for r in rows)==15
    filtered=list_site_details(sku='SKU-BOTH',site='UK',sid=2)['items']
    assert len(filtered)==1 and filtered[0]['storeName']=='S2'
    assert list_site_details(sku='SKU-BOTH',site='UK',sid=999)['items']==[]


def test_age_uses_latest_snapshot_maximum_and_correct_shop_or_site(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.execute('''INSERT INTO ods_lingxing_amz_fba_inventory_raw
            (pull_month,sku,sid,inv_age_0_to_90_days,inv_age_91_to_180_days,inv_age_181_to_270_days,inv_age_271_to_365_days,inv_age_365_plus_days,pulled_at) VALUES
            ('2026-09','SKU-BOTH','1',0,0,0,0,99,NOW()),
            ('2026-10','SKU-BOTH','1',3,4,0,0,0,NOW()),
            ('2026-10','SKU-BOTH','2',0,0,0,7,0,NOW()),
            ('2026-10','SKU-BOTH','0',0,0,0,0,1,NOW()),
            ('2026-10','SKU-ZERO','1',0,0,0,0,0,NOW())''')
        for sku,site,age,qty,raw in [
            ('SKU-BOTH','UK',10,2,10),('SKU-BOTH-YXR','UK',80,1,80),
            ('SKU-BOTH','CZ',200,1,200),('SKU-BOTH','DE',900,0,900),
            ('SKU-BOTH','UK',0,2,None),('SKU-BOTH','UK',950,1,'bad'),
            ('OTHER-BOTH','UK',999,1,999),('SKU-ZERO','UK',0,1,0)]:
            cur.execute('INSERT INTO ods_goodcang_inventory_age_latest VALUES(%s,%s,%s,%s,%s,NOW())',
                        (sku,site,age,qty,json.dumps({'warehouse_age':raw})))
        conn.commit()
    amz=service.list_sales(platform='amz',sku='SKU-BOTH')['items'][0]
    assert amz['inventoryAge'] is None  # no cross-shop maximum
    assert amz['sales30d']==11 and amz['fbaTotalInventory']==20
    assert service.list_sales(platform='amz',sku='SKU-BOTH',sid=1)['items'][0]['inventoryAge'] is None
    assert service.list_sales(platform='amz',sku='SKU-ZERO')['items'][0]['inventoryAge'] is None
    ebay=service.list_sales(platform='ebay',sku='SKU-BOTH')['items'][0]
    assert ebay['inventoryAge']=='200天' and ebay['sales30d']==3
    assert service.list_sales(platform='ebay',sku='SKU-BOTH',site='UK')['items'][0]['inventoryAge']=='80天'
    assert service.list_sales(platform='ebay',sku='SKU-ZERO')['items'][0]['inventoryAge']=='0天'
    amz_details=list_site_details(platform='amz',sku='SKU-BOTH',site='UK')['items']
    assert {r['sid']:r['inventoryAge'] for r in amz_details}=={1:'91–180天',2:'271–365天'}
    ebay_details=list_site_details(platform='ebay',sku='SKU-BOTH')['items']
    assert {r['inventoryAge'] for r in ebay_details if r['site']=='UK'}=={'80天'}
    assert {r['inventoryAge'] for r in ebay_details if r['site']=='DE'}=={'200天'}


def test_ebay_jmh_age_maps_unique_full_tail_without_crossing_supplier_or_brand(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.execute('''INSERT INTO ods_lingxing_product_procurement_monthly VALUES
            ('2026-09','OLD-30057-0002'),
            ('2026-10','BMW-30057-0002'),('2026-10','BMW-30057-0002-YXR'),
            ('2026-10','BMW-30057-0099'),('2026-10','BMW-30063-2-0018'),
            ('2026-10','BMW-60000-0001'),('2026-10','FRD-60000-0001')''')
        for sku,site,age,qty in [
            ('JMH-30057-0002','UK',520,6),('JMH-30057-0002-YXR','UK',530,1),
            ('JMH-30057-0002','DE',80,1),('JMH-30057-0099','UK',900,1),
            ('JMH-30063-2-0018','UK',491,6),('JMH-60000-0001','UK',800,1),
            ('FRD-30057-0002','UK',999,1),('JMH-30057-0002','UK',999,0)]:
            cur.execute('INSERT INTO ods_goodcang_inventory_age_latest VALUES(%s,%s,%s,%s,%s,NOW())',
                        (sku,site,age,qty,json.dumps({'warehouse_age':age})))
        conn.commit()
    items=[dict(sku=sku,site=site) for sku,site in [
        ('BMW-30057-0002','UK'),('BMW-30057-0002','DE'),('BMW-30057-0002','US'),
        ('BMW-30063-2-0018','UK'),('BMW-60000-0001','UK'),('FRD-60000-0001','UK'),
        ('OLD-30057-0002','UK'),('BMW-30057-0003','UK')]]
    ages.attach_ages(items,platform='ebay',details=True)
    assert [r['inventoryAge'] for r in items]==['530天','80天',None,'491天',None,None,None,None]
    summary=[dict(sku='BMW-30057-0002')]
    ages.attach_ages(summary,platform='ebay')
    assert summary[0]['inventoryAge']=='530天'
    ages.attach_ages(summary,platform='ebay',site='DE')
    assert summary[0]['inventoryAge']=='80天'


def test_age_filters_apply_before_pagination_and_respect_shop_site_and_maximum(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.execute('''INSERT INTO ods_lingxing_amz_fba_inventory_raw VALUES
            ('2026-10','SKU-BOTH','1',2,3,0,0,0,NOW(),'',0),
            ('2026-10','SKU-BOTH','0',0,0,0,7,0,NOW(),'S2',2),
            ('2026-10','SKU-ZERO','999',0,0,0,0,9,NOW(),'',0),
            ('2026-09','SKU-ZERO','1',0,0,0,0,9,NOW(),'',0)''')
        for sku,site,age in [('SKU-BOTH','UK',180),('SKU-BOTH','DE',181),('SKU-ZERO','UK',0)]:
            cur.execute('INSERT INTO ods_goodcang_inventory_age_latest VALUES(%s,%s,%s,1,%s,NOW())',
                        (sku,site,age,json.dumps({'warehouse_age':age})))
        conn.commit()
    def found(**kw):
        result=service.list_sales(**kw)
        assert result['total']==len(result['items'])
        return {r['sku'] for r in result['items']}
    assert found(platform='amz',age_bucket=2)=={'SKU-BOTH'}
    assert found(platform='amz',age_bucket=4)=={'SKU-BOTH'}
    assert found(platform='amz',age_bucket=1)==set()  # highest bucket, not any positive bucket
    assert found(platform='amz',age_bucket=5)==set()  # orphan shop and older snapshot excluded
    assert found(platform='amz',age_bucket=4,sid=1)==set()
    assert found(platform='amz',age_bucket=4,sid=2)=={'SKU-BOTH'}
    assert found(platform='amz',age_bucket=4,sku='BOTH',product_name='Both')=={'SKU-BOTH'}
    assert found(platform='ebay',age_operator='gt',age_days=180)=={'SKU-BOTH'}
    assert found(platform='ebay',age_operator='gt',age_days=180,site='UK')==set()
    assert found(platform='ebay',age_operator='eq',age_days=180,site='UK')=={'SKU-BOTH'}
    assert found(platform='ebay',age_operator='gte',age_days=180,site='UK')=={'SKU-BOTH'}
    assert found(platform='ebay',age_operator='lte',age_days=180)=={'SKU-ZERO'}
    assert found(platform='ebay',age_operator='lt',age_days=1)=={'SKU-ZERO'}
    assert found(platform='ebay',age_operator='eq',age_days=0)=={'SKU-ZERO'}
    for platform,filter_args in [('amz',dict(age_bucket=4)),('ebay',dict(age_operator='gt',age_days=180))]:
        first=service.list_sales(platform=platform,page_size=1,**filter_args)
        second=service.list_sales(platform=platform,page_size=1,page=2,**filter_args)
        assert first['total']==second['total']==1 and second['items']==[]
        plain=service.list_sales(platform=platform,sku='SKU-BOTH')['items'][0]
        assert first['items'][0]==plain  # filtering never changes sales/inventory totals


def test_amazon_shared_age_matches_exact_shop_names_only_when_sid_missing(isolated):
    with isolated() as conn,conn.cursor() as cur:
        cur.execute("INSERT INTO shop_list VALUES(10,'S10','10001','GBP','UK'),(5,'Ambiguous','10001','EUR','DE'),(6,'Ambiguous','10001','EUR','FR')")
        cur.execute('''INSERT INTO ods_lingxing_amz_fba_inventory_raw VALUES
            ('2026-10','SKU-BOTH','1',0,3,0,0,0,NOW(),'S3',0),
            ('2026-10','SKU-BOTH','0',0,0,0,4,0,NOW(),' S2, S3,S2 ',2),
            ('2026-10','SKU-BOTH','0',0,0,0,0,9,NOW(),'S10',2),
            ('2026-10','SKU-BOTH','0',0,0,0,0,9,NOW(),'Ambiguous',2),
            ('2026-10','SKU-BOTH','999',0,0,0,0,9,NOW(),'S1',0),
            ('2026-10','SKU-BOTH','0',0,0,0,0,9,NOW(),'S1-extra',2),
            ('2026-10','OTHER-SKU','0',0,0,0,0,9,NOW(),'S1',2),
            ('2026-09','SKU-BOTH','0',0,0,0,0,9,NOW(),'S1',2)''')
        conn.commit()
    rows=[dict(sku='SKU-BOTH',sid=sid) for sid in (1,2,3,4,5,6,10,None)]
    ages.attach_ages(rows,platform='amz',details=True)
    keyed={r['sid']:r for r in rows}
    assert keyed[1]['inventoryAge']=='91–180天'
    assert not keyed[1]['inventoryAgeShared'] and not keyed[1]['inventoryAgeNameMatched']
    for sid in (2,3):
        assert keyed[sid]['inventoryAge']=='271–365天'
        assert keyed[sid]['inventoryAgeShared'] and keyed[sid]['inventoryAgeNameMatched']
    assert keyed[10]['inventoryAge']=='365天以上'
    assert all(keyed[sid]['inventoryAge'] is None for sid in (4,5,6,None))
    displayed={r['sid']:r for r in list_site_details(platform='amz',sku='SKU-BOTH',site='UK')['items']}
    assert displayed[1]['inventoryAge']=='91–180天' and displayed[2]['inventoryAge']=='271–365天'
    assert displayed[1]['sales30d']==5 and displayed[2]['sales30d']==6


def test_exact_sku_queries_preserve_listing_priority_and_inventory_fallback(isolated):
    with isolated() as conn,conn.cursor() as cur:
        # Whitespace/case normalization and a missing listing mapping still match.
        cur.execute("INSERT INTO amz_product_listing VALUES(1,'FALLBACK',NULL,'Both','img','UK',NOW(),13,'GBP')")
        cur.execute("INSERT INTO amz_product_performance_inventory VALUES(1,'FALLBACK',' sku-both ',2,3,NOW())")
        cur.execute("INSERT INTO amz_restock_summary VALUES(1,'FALLBACK',7,3,NOW())")
        cur.execute("INSERT INTO ods_lingxing_amz_listing_latest(sid,seller_sku,thirty_volume,sync_batch_id) VALUES(1,'FALLBACK','7','published')")
        # A conflicting inventory SKU must never override the listing mapping.
        cur.execute("INSERT INTO amz_product_listing VALUES(1,'CONFLICT','SKU-AMZ','Amazon','img','UK',NOW(),999,'GBP')")
        cur.execute("INSERT INTO amz_product_performance_inventory VALUES(1,'CONFLICT','SKU-BOTH',999,999,NOW())")
        cur.execute("INSERT INTO amz_restock_summary VALUES(1,'CONFLICT',999,3,NOW())")
        cur.execute("INSERT INTO ods_lingxing_amz_listing_latest(sid,seller_sku,thirty_volume,sync_batch_id) VALUES(1,'CONFLICT','999','published')")
        conn.commit()
    summary=service.list_sales(platform='amz',sku='SKU-BOTH')['items'][0]
    sites=service.list_sales(platform='amz',sku=' sku-both ',details=True)['items']
    stores=store_service.list_store_inventory(sku=' sku-both ')
    assert summary['sales30d']==18 and summary['fbaTotalInventory']==25
    assert sum(r['sales30d'] or 0 for r in sites)==summary['sales30d']
    assert sum(r['sales30d'] or 0 for r in stores)==summary['sales30d']
    quotes=comparison.list_price_ranges(sku=' sku-both ',site='UK')['items']
    assert quotes[0]['amzMinPrice']==13 and quotes[0]['amzMaxPrice']==100
