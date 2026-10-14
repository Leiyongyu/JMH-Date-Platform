"""Execute the read-only aggregation SQL against isolated synthetic snapshots.

SQLite supports the CTE/CASE SQL used here; adapt only placeholders and CONCAT.
No application database or remote APIs are touched.
"""
import sqlite3
from types import SimpleNamespace

import pytest

from backend.repositories import clearance_repository as repo
from backend.services import clearance_drilldown_service as service


FIELDS = [
    'inventory_0_90_qty', 'inventory_0_90_cost',
    'inventory_91_180_qty', 'inventory_91_180_cost',
    'inventory_181_plus_qty', 'inventory_181_plus_cost',
    'total_inventory_qty', 'total_inventory_cost',
]
AMZ = 'dwd_amz_fba_inventory_monthly_snapshot'
EBAY = 'dwd_ebay_inventory_age_cost_snapshot'


@pytest.fixture
def snapshots(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.create_function('CONCAT', -1, lambda *args: ''.join(str(x) for x in args))
    db.execute(f'CREATE TABLE {AMZ} (pull_month TEXT, group_code TEXT, sid TEXT, '
               'store_name TEXT, warehouse_name TEXT, seller_group_name TEXT, '
               + ','.join(f'{f} NUMERIC DEFAULT 0' for f in FIELDS) + ')')
    db.execute(f'CREATE TABLE {EBAY} (pull_month TEXT, warehouse_code TEXT, sku TEXT, source_product_sku TEXT, '
               'inventory_age_bucket TEXT, inventory_quantity NUMERIC, inventory_age_cost NUMERIC)')

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self):
            return self

        def execute(self, sql, params):
            assert sql.lstrip().startswith(('WITH', 'SELECT'))  # No mutation path.
            self.result = db.execute(sql.replace('%s', '?'), params)

        def fetchall(self):
            return [dict(row) for row in self.result.fetchall()]

    monkeypatch.setattr(repo, 'db_connection', Connection)

    def add(table, **values):
        db.execute(f'INSERT INTO {table} ({",".join(values)}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))

    yield add
    db.close()


def test_ebay_sites_merge_warehouses_and_keep_unknown_and_unpriced(snapshots):
    for warehouse, bucket, qty, cost in [
        ('USEA', '0_90', 3, 10), ('USWE', '91_180', 7, 20),
        ('DE', '181_PLUS', 4, 30), ('CZ', '181_PLUS', 5, 40),
        ('UK', '0_90', 6, None), ('OTHER', '91_180', 8, 50),
    ]:
        snapshots(EBAY, pull_month='2026-10', warehouse_code=warehouse,
                  inventory_age_bucket=bucket, inventory_quantity=qty, inventory_age_cost=cost)
    snapshots(EBAY, pull_month='2026-08', warehouse_code='USWE', inventory_quantity=999, inventory_age_cost=999)
    result = service.list_dimensions('2026-10', 'EBAY-1')
    rows = {row['dimension_key']: row for row in result['items']}
    assert result['dimension'] == 'SITE'
    assert rows['US']['total_inventory_qty'] == 10
    assert rows['US']['total_inventory_cost'] == 30  # Stored cost, no repricing/multiplier.
    assert rows['DE']['inventory_181_plus_cost'] == 70
    assert rows['UK']['total_inventory_qty'] == 6
    assert rows['UK']['total_inventory_cost'] == 0
    assert '未识别仓库：OTHER' in rows
    assert sum(row['total_inventory_qty'] for row in rows.values()) == 33
    assert sum(row['total_inventory_cost'] for row in rows.values()) == 150
    assert all(row['previous_month_91_180_cost'] is None for row in rows.values())


def test_amazon_merges_chinese_store_names_across_sids_and_shared_warehouse(snapshots):
    for sid, name, warehouse, qty, cost in [
        ('11', 'EU-同名店铺-UK', 'A', 2, 10), ('11', 'EU-同名店铺-UK', 'B', 3, 20),
        ('12', 'EU-同名店铺-DE', 'A', 4, 30), ('0', '共享仓', 'AMZ-EU-同名店铺欧洲仓', 5, 40),
        ('0', '共享仓', 'AMZ-EU-同名店铺欧洲仓', 6, 50),
    ]:
        snapshots(AMZ, pull_month='2026-10', group_code='EU', sid=sid, store_name=name,
                  warehouse_name=warehouse, seller_group_name='店铺甲,店铺乙' if qty == 5 else '店铺乙,店铺甲',
                  inventory_91_180_qty=qty, inventory_91_180_cost=cost,
                  total_inventory_qty=qty, total_inventory_cost=cost)
    snapshots(AMZ, pull_month='2026-10', group_code='US1', sid='11', total_inventory_cost=999)
    snapshots(AMZ, pull_month='2026-08', group_code='EU', sid='11', total_inventory_cost=999)
    result = service.list_dimensions('2026-10', 'EU')
    rows = {row['dimension_key']: row for row in result['items']}
    assert result['dimension'] == 'STORE'
    assert len(rows) == 1
    assert rows['STORE:同名店铺']['total_inventory_qty'] == 20
    assert rows['STORE:同名店铺']['dimension_name'] == '同名店铺'
    assert sum(row['total_inventory_cost'] for row in rows.values()) == 150


def test_previous_only_and_new_stores_reconcile_cost_difference_across_year(snapshots):
    for month, sid, cost in [('2025-12', '11', 40), ('2025-12', '12', 60), ('2026-01', '11', 20), ('2026-01', '13', 10)]:
        snapshots(AMZ, pull_month=month, group_code='US2-MJ', sid=sid, store_name=f'US3-店铺{sid}-US',
                  inventory_91_180_cost=cost, inventory_181_plus_cost=cost, total_inventory_cost=cost*2)
    rows = {r['dimension_key']: r for r in service.list_dimensions('2026-01', 'US2-MJ')['items']}
    assert rows['STORE:店铺12']['source_row_count'] == 0
    assert rows['STORE:店铺12']['total_inventory_cost'] == 0
    assert rows['STORE:店铺13']['previous_month_91_180_cost'] == 0
    assert rows['STORE:店铺13']['inventory_91_180_variance'] == -10
    assert sum(r['previous_month_91_180_cost'] for r in rows.values()) == 100
    assert sum(r['inventory_91_180_variance'] for r in rows.values()) == 70
    assert all(r['previous_cost_month'] == '2025-12' for r in rows.values())


def test_empty_snapshot_and_invalid_group(snapshots):
    assert service.list_dimensions('2026-10', 'EU')['items'] == []
    with pytest.raises(ValueError, match='不支持'):
        service.list_dimensions('2026-10', "EU' OR 1=1")


def test_api_validates_inputs_and_requires_internal_access(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import deps
    from backend.api.v1.finance import router

    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-internal'))
    calls = []
    def query(month, group, site):
        calls.append((month, group, site))
        return {'pull_month': month, 'items': [], 'total': 0}
    monkeypatch.setattr('backend.api.v1.finance.clearance_dimensions', query)
    app = FastAPI()
    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = 'unit-test'
        return await call_next(request)
    app.include_router(router)
    client = TestClient(app)
    url = '/api/v1/finance/slow-moving-clearance/dimensions'
    valid = {'pull_month': '2026-10', 'group_code': 'EBAY-1'}
    assert client.get(url, params=valid).status_code == 401
    headers = {'X-Internal-Token': 'test-internal'}
    for params in [{}, {**valid, 'pull_month': '2026-13'}, {**valid, 'group_code': 'ALL'}]:
        assert client.get(url, params=params, headers=headers).status_code == 422
    response = client.get(url, params=valid, headers=headers)
    assert response.status_code == 200
    assert response.json()['data']['pull_month'] == '2026-10'
    assert client.get(url, params={**valid, 'group_code': 'EU', 'site_code': 'US'}, headers=headers).status_code == 400
    response = client.get(url, params={**valid, 'site_code': 'US'}, headers=headers)
    assert response.status_code == 200
    assert calls == [('2026-10', 'EBAY-1', None), ('2026-10', 'EBAY-1', 'US')]


def test_ebay_owners_use_each_month_rules_and_reconcile_to_selected_site(snapshots, monkeypatch):
    for month, warehouse, sku, cost in [
        ('2026-09', 'USEA', 'FRD-1-2', 100), ('2026-10', 'USWE', 'FRD-1-2', 70),
        ('2026-10', 'USEA', 'JMH-3-4', 10), ('2026-10', 'USWE', 'UNKNOWN-1-2', 5),
        ('2026-10', 'DE', 'FRD-1-2', 900), ('2026-10', 'USWE', 'FLL-1-2', 3),
    ]:
        snapshots(EBAY, pull_month=month, warehouse_code=warehouse, sku=sku,
                  inventory_age_bucket='181_PLUS', inventory_quantity=2, inventory_age_cost=cost)
    read_months = []
    def rules(month, platform):
        read_months.append(month)
        return [{'rule_type': 'EBAY_BRAND', 'match_key': 'FRD', 'principal_name': '旧负责人' if month == '2026-09' else '新负责人'}]
    monkeypatch.setattr(service.owners, 'owner_rules', rules)
    monkeypatch.setattr(service.owners, 'ebay_product_sku_map', lambda month: {'3-4': 'FRD-3-4'})
    result = service.list_dimensions('2026-10', 'EBAY-1', 'US')
    rows = {r['dimension_name']: r for r in result['items']}
    assert result['dimension'] == 'OWNER'
    assert read_months == ['2026-09', '2026-10']
    assert rows['新负责人']['total_inventory_cost'] == 80
    assert rows['旧负责人']['total_inventory_cost'] == 0
    assert rows['旧负责人']['previous_month_181_plus_cost'] == 100
    assert rows['未分配']['total_inventory_cost'] == 5
    assert rows['方黎力']['total_inventory_cost'] == 3
    site = next(r for r in service.list_dimensions('2026-10', 'EBAY-1')['items'] if r['dimension_key'] == 'US')
    for field in FIELDS + ['previous_month_181_plus_cost', 'inventory_181_plus_variance']:
        assert sum(r[field] for r in rows.values()) == site[field]


def test_missing_owner_rules_stay_unassigned_with_warning(snapshots, monkeypatch):
    snapshots(EBAY, pull_month='2026-10', warehouse_code='CZ', sku='FRD-1-2',
              inventory_age_bucket='91_180', inventory_quantity=2, inventory_age_cost=20)
    monkeypatch.setattr(service.owners, 'owner_rules', lambda *args: [])
    monkeypatch.setattr(service.owners, 'ebay_product_sku_map', lambda month: {})
    result = service.list_dimensions('2026-10', 'EBAY-1', 'DE')
    assert result['items'][0]['dimension_name'] == '未分配'
    assert result['items'][0]['total_inventory_cost'] == 20
    assert result['warnings']


def test_monthly_owner_view_merges_all_sites_by_brand(snapshots, monkeypatch):
    for warehouse, sku, amount in [('USEA', 'FRD-1-2', 10), ('USWE', 'FRD-3-4', 20),
                                   ('UK', 'FRD-5-6', 30), ('DE', 'HME-7-8', 40),
                                   ('CZ', '2PC-FRD-1-2', 50), ('OTHER', 'CL-1-2', 60)]:
        snapshots(EBAY, pull_month='2026-10', warehouse_code=warehouse, sku=sku,
                  inventory_age_bucket='181_PLUS', inventory_quantity=1, inventory_age_cost=amount)
    monkeypatch.setattr(service.owners, 'owner_rules', lambda *args: [
        {'rule_type': 'EBAY_BRAND', 'match_key': brand, 'principal_name': '同一负责人'} for brand in ['FRD', 'HME']])
    monkeypatch.setattr(service.owners, 'ebay_product_sku_map', lambda month: {})
    all_sites = service.list_dimensions('2026-10', 'EBAY-1', dimension='OWNER')
    rows = {r['dimension_name']: r for r in all_sites['items']}
    assert rows['同一负责人']['total_inventory_cost'] == 150
    assert rows['同一负责人']['total_inventory_qty'] == 5
    assert rows['同一负责人']['brands'] == ['FRD', 'HME']
    assert rows['陈丽']['total_inventory_cost'] == 60
    assert all_sites['site_code'] is None
    assert set(all_sites['site_options']) == {'DE', 'UK', 'US', '未识别仓库：OTHER'}
    selected = service.list_dimensions('2026-10', 'EBAY-1', 'US', dimension='OWNER')
    assert len(selected['items']) == 1
    assert selected['items'][0]['dimension_name'] == '同一负责人'
    assert selected['items'][0]['total_inventory_cost'] == 30


def test_owner_page_api_defaults_to_all_sites_and_keeps_permissions(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import deps
    from backend.api.v1.finance import router
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-internal'))
    calls = []
    def query(month, group, site, *, dimension):
        calls.append((month, group, site, dimension))
        return {'items': []}
    monkeypatch.setattr('backend.api.v1.finance.clearance_dimensions', query)
    app = FastAPI()
    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = 'test'
        return await call_next(request)
    app.include_router(router)
    client = TestClient(app)
    url = '/api/v1/finance/slow-moving-clearance/owners'
    headers = {'X-Internal-Token': 'test-internal'}
    assert client.get(url, params={'pull_month': '2026-10'}).status_code == 401
    assert client.get(url, params={'pull_month': '2026-13'}, headers=headers).status_code == 422
    assert client.get(url, params={'pull_month': '2026-10'}, headers=headers).status_code == 200
    assert client.get(url, params={'pull_month': '2026-10', 'site_code': 'UK'}, headers=headers).status_code == 200
    assert calls == [('2026-10', 'EBAY-1', None, 'OWNER'), ('2026-10', 'EBAY-1', 'UK', 'OWNER')]


@pytest.mark.parametrize('raw,expected', [
    ('US1-刘予洋-US', '刘予洋'), ('US1-刘予洋-CA', '刘予洋'),
    ('US1-刘予洋-MX', '刘予洋'), ('US2-MJ-新志楠-US', '新志楠'),
    ('US1-店铺-分店-US', '店铺-分店'), ('中文店铺', '中文店铺'),
])
def test_chinese_store_name_normalization(raw, expected):
    assert service._shop_identity({'sid': '1', 'store_name': raw}) == ('STORE:' + expected, expected)
