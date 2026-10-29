from datetime import datetime
from unittest.mock import MagicMock
from contextlib import contextmanager
import os,re
from pathlib import Path
from uuid import uuid4

import pymysql
import pytest
from backend.config import settings
from backend.sql_statements import split_sql_statements
from backend.repositories import ebay_mixed_sales_price_repository as repo
from backend.services import ebay_mixed_sales_price_sync_service as sync
from backend.services import scheduler_service as scheduler


def account(uid='a', count=1):
    return dict(userId=uid,username='seller-'+uid,shop_name='店铺-'+uid,row_count=count,published_at=datetime(2026,10,28))


def record(uid='a', item_id='1', sku='FRD-70327-0076', price='12.3400', currency='GBP', variants=None):
    return dict(seller=dict(userId=uid,username='seller-'+uid),item=dict(item_id=item_id,sku=sku,
        title='商品',site='UK',current_price=dict(value=price,currency=currency),
        buy_it_now_price=dict(value=None,currency=None),quantity=0,variations=variants or [],raw_xml='<Item/>'))


def test_sync_uses_independent_publisher_and_reports_accounts_without_authorization(monkeypatch):
    monkeypatch.setenv('EBAY_SELLER_ACCOUNTS_FILE','file.xlsx')
    monkeypatch.setattr(sync,'read_workbook_accounts',lambda:dict(missing_credentials=[{'source_row':3}]))
    extract=MagicMock(return_value={})
    monkeypatch.setattr(sync,'sync_ebay_store_listings',extract)
    result=sync.sync_prices()
    assert result['skipped_rows']==1 and result['missing_credentials']==[{'source_row':3}]
    extract.assert_called_once_with(publisher=repo.replace_snapshots)


def test_task_rejects_historical_labels_and_shares_the_seller_api_lock(monkeypatch):
    spec=scheduler.TASK_SPECS[sync.TASK_CODE]
    assert spec.lock_name(None)=='ebay:store-listing:replace'
    extract=MagicMock()
    monkeypatch.setattr(scheduler,'sync_ebay_mixed_prices',extract)
    with pytest.raises(ValueError,match='历史'): scheduler.run_scheduler_task(sync.TASK_CODE,stat_month='2026-09')
    extract.assert_not_called()


def test_clean_item_never_persists_repeated_xml_and_preserves_native_variant_prices():
    item=record(variants=[dict(sku='SKU',price=dict(value='0.0001',currency='EUR'),raw_xml='<Variation/>')])['item']
    clean=repo.clean_item(item)
    assert 'raw_xml' not in clean and 'raw_xml' not in clean['variations'][0]
    assert clean['variations'][0]['price']==dict(value='0.0001',currency='EUR')


@pytest.fixture
def isolated(monkeypatch):
    if os.getenv('RUN_MIXED_PRICE_MYSQL_TESTS')!='1': pytest.skip('opt-in isolated local MySQL test')
    assert settings.mysql_host in ('127.0.0.1','localhost')
    schema='codex_mixed_price_'+uuid4().hex[:12]
    assert re.fullmatch('codex_mixed_price_[0-9a-f]{12}',schema)
    def connect(db=None):
        return pymysql.connect(host=settings.mysql_host,port=settings.mysql_port,user=settings.mysql_user,
            password=settings.mysql_password,database=db,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
    admin=connect()
    try:
        with admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        @contextmanager
        def connection():
            conn=connect(schema)
            try: yield conn
            finally: conn.close()
        with connection() as conn,conn.cursor() as cur:
            path=Path(__file__).resolve().parents[1]/'migrations/20261028_ebay_mixed_sales_prices.sql'
            for sql in split_sql_statements(path.read_text(encoding='utf-8')):
                if 'CREATE TABLE' in sql: cur.execute(sql)
            conn.commit()
        monkeypatch.setattr(repo,'db_connection',connection)
        yield connection
    finally:
        with admin.cursor() as cur: cur.execute(f'DROP DATABASE `{schema}`')
        admin.close()


def test_monthly_store_overwrite_variants_empty_stores_and_rollback(isolated):
    for month in (9,10):
        repo.replace_snapshots([record(),record('b',price='99.50',currency='EUR')],[account(),account('b')],
            batch_id=f'batch-{month}',pulled_at=datetime(2026,month,3,7))
    # Same month only replaces requested store, preserving store b and September.
    repo.replace_snapshots([record(price='15.99')],[account()],batch_id='updated',pulled_at=datetime(2026,10,28))
    data=repo.list_prices(sku='FRD-70327-0076')
    assert data['months']==['2026-10','2026-09'] and data['total']==2
    assert {r['price'] for r in data['items']}=={'15.99','99.50'}
    assert {r['currency'] for r in data['items']}=={'GBP','EUR'}
    assert repo.list_prices(sku='FRD-70327-0076',stat_month='2026-09')['items'][0]['price']=='12.3400'
    with pytest.raises(ValueError):
        repo.replace_snapshots([], [account()],batch_id='bad',pulled_at=datetime(2026,10,28))
    assert repo.list_prices(sku='FRD-70327-0076')['total']==2
    # Empty store marker prevents stale listing fallback to an older month.
    repo.replace_snapshots([], [account(count=0)],batch_id='empty',pulled_at=datetime(2026,10,28))
    assert repo.list_prices(sku='FRD-70327-0076')['total']==1
    variant=dict(sku='FRD-70327-0076-YXR',price=dict(value='11.23456789',currency='USD'))
    repo.replace_snapshots([record(sku=None,variants=[variant])], [account()],batch_id='variant',pulled_at=datetime(2026,10,28))
    data=repo.list_prices(sku='FRD-70327-0076',site='英国')
    assert data['total']==2 and data['items'][0]['price']=='11.23456789'
    assert data['items'][0]['currency']=='USD'  # never parent's GBP
    assert repo.list_prices(sku='FRD-70327-0076',site='德国')['total']==0
    assert repo.list_prices(sku="x' OR 1=1 --")['total']==0
