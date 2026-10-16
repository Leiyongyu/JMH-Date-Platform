from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services import ebay_replenishment_read_model as model


def state(**updates):
    return dict(active_generation='a'*32,reference_date=date(2026,10,16),
                engine_version=model.ENGINE_VERSION,recently_checked=True,
                source_signature='source',daily_signature='daily',**updates)


def database(monkeypatch):
    calls=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def execute(self,sql,args=()): calls.append((sql,args))
        def fetchone(self): return {'acquired':1}
    class Connection:
        committed=0
        rolled_back=0
        def cursor(self): return Cursor()
        def begin(self): pass
        def commit(self): self.committed+=1
        def rollback(self): self.rolled_back+=1
    connection=Connection()
    @contextmanager
    def connect(): yield connection
    monkeypatch.setattr(model,'db_connection',connect)
    monkeypatch.setattr(model,'reference_today',lambda:date(2026,10,16))
    return connection,calls


def test_hot_read_does_not_read_sources_or_recalculate(monkeypatch):
    _,calls=database(monkeypatch)
    monkeypatch.setattr(model,'_state',lambda _:state())
    monkeypatch.setattr(model,'source_signatures',lambda *_:pytest.fail('hot read scanned sources'))
    assert model.ensure_generation()=='a'*32
    assert not calls


def test_expired_check_with_unchanged_sources_only_updates_check_time(monkeypatch):
    connection,calls=database(monkeypatch)
    current=state(); current['recently_checked']=False
    monkeypatch.setattr(model,'_state',lambda _:current)
    monkeypatch.setattr(model,'source_signatures',lambda *_:('daily','source',{}))
    monkeypatch.setattr(model,'build_items',lambda *_:pytest.fail('unchanged data rebuilt'))
    assert model.ensure_generation()=='a'*32
    assert connection.committed==1
    assert any('checked_at=UTC_TIMESTAMP' in sql for sql,_ in calls)
    assert not any('active_generation=%s' in sql for sql,_ in calls)
    assert any('RELEASE_LOCK' in sql for sql,_ in calls)


def test_failed_build_rolls_back_and_releases_cross_worker_lock(monkeypatch):
    connection,calls=database(monkeypatch)
    monkeypatch.setattr(model,'_state',lambda _:state())
    monkeypatch.setattr(model,'source_signatures',lambda *_:('changed','changed',{}))
    rebuilt=[]
    monkeypatch.setattr(model,'rebuild_daily',lambda _:rebuilt.append(True))
    def fail(*_): raise RuntimeError('calculation failed')
    monkeypatch.setattr(model,'build_items',fail)
    with pytest.raises(RuntimeError,match='calculation failed'):
        model.ensure_generation(True)
    assert rebuilt==[True]
    assert connection.committed==0 and connection.rolled_back>=2
    assert not any('active_generation=%s' in sql for sql,_ in calls)
    assert any('RELEASE_LOCK' in sql for sql,_ in calls)


def test_concurrent_refresh_cannot_hide_edit_after_other_build_snapshot(monkeypatch):
    _,calls=database(monkeypatch)
    old=state()
    newer=state(); newer['active_generation']='b'*32
    snapshots=iter((old,newer))
    monkeypatch.setattr(model,'_state',lambda _:next(snapshots))
    monkeypatch.setattr(model,'source_signatures',lambda *_:('daily','edited-after-build',{}))
    def build(*_): raise RuntimeError('newer input must be calculated')
    monkeypatch.setattr(model,'build_items',build)
    with pytest.raises(RuntimeError,match='newer input must be calculated'):
        model.ensure_generation(True)
    assert any('RELEASE_LOCK' in sql for sql,_ in calls)


def test_day_and_engine_changes_invalidate_even_recent_versions():
    assert model._fresh(state(),date(2026,10,16))
    assert not model._fresh(state(),date(2026,10,17))
    old=state(); old['engine_version']='previous-code'
    assert not model._fresh(old,date(2026,10,16))


def test_export_uses_requested_version_without_rebuilding(monkeypatch):
    monkeypatch.setattr(model,'ensure_generation',lambda *_:pytest.fail('pinned export rebuilt'))
    monkeypatch.setattr(model,'read_generation',lambda generation,**kw:{'version':generation,'paginate':kw['paginate']})
    assert model.query(calculation_version='b'*32,paginate=False)=={'version':'b'*32,'paginate':False}
    with pytest.raises(ValueError,match='无效计算版本'):
        model.query(calculation_version="x' OR 1=1")


def test_sql_sort_fields_are_exact_whitelist_and_cover_four_quantities():
    for front,field in [('safetyStockQty','safety_stock_quantity'),
                        ('suggestedReplenishmentQty','suggested_replenishment_quantity'),
                        ('safetyStockQty2','safety_stock_quantity_2'),
                        ('suggestedReplenishmentQty2','suggested_replenishment_quantity_2')]:
        assert model.SORT_FIELDS[front]==field
        assert model.SORT_FIELDS[field]==field
    assert 'sku;DROP TABLE' not in model.SORT_FIELDS


def test_api_forwards_refresh_exact_sku_and_pinned_export(monkeypatch):
    from backend.api.v1 import ebay_replenishment_v2 as api
    seen=[]
    monkeypatch.setattr(api.service,'list_replenishment',lambda **kw:seen.append(kw) or {})
    request=SimpleNamespace(state=SimpleNamespace(request_id='unit'))
    api.list_replenishment(request,refresh=True,exact_sku=True,principal_name='任雅婷')
    assert seen[-1]['use_read_model'] and seen[-1]['refresh'] and seen[-1]['exact_sku']
    assert seen[-1]['principal_name']=='任雅婷'
    api.export_replenishment_data(request,calculation_version='a'*32,principal_name='未分配')
    assert seen[-1]['calculation_version']=='a'*32
    assert seen[-1]['use_read_model'] and not seen[-1]['paginate']
    assert seen[-1]['principal_name']=='未分配'


def test_numeric_sort_keys_keep_precision_and_zero_denominator():
    row = dict(sales_qty_m1=Decimal('3000000'),return_qty_m1=Decimal('1'),
               gross_profit_amount_m1=Decimal('0.123456'),paid_amount_m1=Decimal('7'))
    values = model._source_sort_values(row)
    assert values['gross_profit_amount'] == Decimal('0.123456')
    assert values['profit_rate'] == Decimal('0.123456') / 7
    assert values['return_rate'] == Decimal(1) / 3000000
    assert model._source_sort_values({})['profit_rate'] is None
