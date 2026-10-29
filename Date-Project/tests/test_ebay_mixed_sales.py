from contextlib import contextmanager
import json

import pytest
from backend.services import ebay_mixed_sales_service as service


def database(monkeypatch):
    monkeypatch.setattr(service, 'attach_ages', lambda *a, **k: None)
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, args=()): calls.append((sql, args))
        def fetchone(self):
            if 'SELECT metadata' in calls[-1][0]:
                return {'metadata': json.dumps({'data_generation': 'b'*32, 'sites': ['英国'], 'reference_date': '2026-10-28'}), 'created_at': '2026-10-28 10:00:00'}
            return {'n': 1}
        def fetchall(self): return [{'sku': 'FRD-70327-0076', 'sales30d': 3}]
    class Connection:
        def cursor(self): return Cursor()
        def begin(self): pass
    @contextmanager
    def connect(): yield Connection()
    monkeypatch.setattr(service, 'db_connection', connect)
    return calls


def test_pinned_query_only_reads_saved_replenishment_version(monkeypatch):
    calls = database(monkeypatch)
    monkeypatch.setattr(service.model, 'ensure_generation', lambda: pytest.fail('pinned request rebuilt'))
    data = service.list_sales(calculation_version='a'*32, site='英国', sku='FRD-70327-0076-YXR')
    assert data['total'] == 1 and data['calculationVersion'] == 'a'*32
    assert data['referenceDate'] == '2026-10-28'
    select, params = calls[-1]
    assert 'GROUP BY base.sku' in select and 'SUM(base.sales_qty_30d)' in select
    assert 'dws_ebay_replenishment_result' in select
    assert 'dwd_ebay_sku_analysis_order' not in select
    assert params[:4] == ['b'*32, 'UK', 'UK', '%FRD-70327-0076%']


def test_parameters_are_bound_and_sort_is_whitelisted(monkeypatch):
    calls = database(monkeypatch)
    user_input = "x' OR 1=1 --"
    service.list_sales(calculation_version='a'*32, sku=user_input,
        product_name=user_input, sort_field='sku; DROP TABLE x', sort_order='evil', page=-1, page_size=999)
    sql, args = calls[-1]
    assert user_input not in sql and 'DROP TABLE' not in sql
    assert 'sales30d DESC' in sql and args[-2:] == [200, 0]
    service.list_sales(calculation_version='a'*32, sku='BMW-1-2', details=True)
    assert 'k.sku=%s' in calls[-1][0] and 'k.sku LIKE' not in calls[-1][0]


def test_invalid_version_or_missing_detail_sku_fails_before_any_query(monkeypatch):
    calls = database(monkeypatch)
    with pytest.raises(ValueError, match='SKU'):
        service.list_sales(details=True)
    with pytest.raises(ValueError, match='版本'):
        service.list_sales(calculation_version='invalid')
    assert not calls


@pytest.mark.parametrize('params', [dict(age_bucket=6,platform='amz'),dict(age_bucket=1),
    dict(age_operator='gt'),dict(age_days=180),dict(age_operator='gt',age_days=-1),
    dict(age_operator='OR 1=1',age_days=180),dict(age_operator='gt',age_days=180,platform='amz')])
def test_invalid_age_filters_are_rejected_before_queries(monkeypatch,params):
    calls=database(monkeypatch)
    with pytest.raises(ValueError,match='库龄'):
        service.list_sales(**params)
    assert not calls
