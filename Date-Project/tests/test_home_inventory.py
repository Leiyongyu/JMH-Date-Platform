from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.v1 import home_inventory as api
from backend.api.deps import require_internal_access
from backend.services import home_inventory_service as s


def test_money_uses_one_subtotal_and_warehouse_fields_no_ctu_double_count():
    totals = [dict(stat_month=m, **{f: Decimal(n) for f in s.TRANSIT+s.STOCK}) for m,n in [('2026-08', '20'),('2026-07','10')]]
    ages = [dict(pull_month=m, group_code=g, **{f: Decimal(n) for f in s.AGE}) for m,n in [('2026-09','10'),('2026-08','20')] for g in s.GROUPS]
    result = s.summarize_money(totals, ages, '2026-09')
    assert result['inventory_total']['value'] == '120.00'
    assert result['transit']['value'] == '60.00'
    assert result['inventory_total']['change_percent'] == '100.00'
    assert result['slow_total']['value'] == '120.00'
    assert result['slow_total']['change_percent'] == '-50.00'
    assert result['source_stat_month'] == '2026-08'


def test_missing_month_or_age_group_is_not_zero():
    result = s.summarize_money([], [], '2026-09')
    assert result['inventory_total']['value'] is None
    assert result['slow_total']['change_percent'] is None
    ages = [dict(pull_month='2026-09',group_code='EU', **{f: 10 for f in s.AGE})]
    assert s.summarize_money([], ages,'2026-09')['slow_total']['value'] is None


@pytest.mark.parametrize('value,previous,direction,pct', [('12','10','up','20.00'),('8','10','down','-20.00'),('0','0','flat',None),('3','0','up',None)])
def test_change_decimal_and_zero_denominator(value,previous,direction,pct):
    m = s.metric(Decimal(value),Decimal(previous))
    assert m['direction'] == direction and m['change_percent'] == pct


def test_count_delta_not_percent_and_missing_is_unknown():
    assert s.metric(Decimal(5),Decimal(3),count=True)['delta'] == 2
    assert s.metric(Decimal(5),None,count=True)['direction'] == 'unknown'
    assert s.shift('2026-01',-1) == '2025-12'


@pytest.mark.parametrize('month', ['2026-13', '2026-9', "2026-09'", None])
def test_reject_invalid_month(month):
    with pytest.raises(ValueError): s.valid_month(month)


def ready(total):
    return dict(state='READY', total=total, rule_month='2026-09', warnings=[], source_updated_at='2026-09-20')


def test_live_reuses_both_owner_services_without_new_dedup(monkeypatch):
    monkeypatch.setattr(s,'current_month',lambda:'2026-09')
    monkeypatch.setattr(s.amz_owner_sku_service,'get_owner_sku_counts',lambda:ready(10))
    monkeypatch.setattr(s.ebay_owner_sku_service,'get_owner_sku_counts',lambda:ready(20))
    assert s.live_sku()['total'] == 30
    monkeypatch.setattr(s.ebay_owner_sku_service,'get_owner_sku_counts',lambda:dict(ready(20),state='MISSING_RULES'))
    with pytest.raises(ValueError): s.live_sku()


def mock_db(monkeypatch):
    conn, cur = MagicMock(), MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    @contextmanager
    def db(): yield conn
    monkeypatch.setattr(s,'db_connection',db)
    return conn,cur


def test_snapshot_only_current_month_upsert_and_no_source_writes(monkeypatch):
    conn,cur = mock_db(monkeypatch)
    cur.fetchone.return_value={'acquired':1}
    monkeypatch.setattr(s,'current_month',lambda:'2026-09')
    monkeypatch.setattr(s,'live_sku',lambda:dict(stat_month='2026-09',total=30,platforms={'amz':{'total':10},'ebay':{'total':20}}))
    s.capture_sku()
    writes=[c for c in cur.execute.call_args_list if c.args[0].startswith('INSERT')]
    assert len(writes)==1 and s.SNAPSHOT_TABLE in writes[0].args[0]
    assert writes[0].args[1][0]=='2026-09' and 'ON DUPLICATE KEY UPDATE' in writes[0].args[0]
    conn.commit.assert_called_once()


def test_failed_capture_does_not_overwrite_previous_data(monkeypatch):
    conn,cur = mock_db(monkeypatch)
    cur.fetchone.return_value={'acquired':1}
    monkeypatch.setattr(s,'live_sku',lambda:(_ for _ in ()).throw(ValueError('not ready')))
    with pytest.raises(ValueError): s.capture_sku()
    conn.rollback.assert_called_once(); conn.commit.assert_not_called()
    assert not any('INSERT' in c.args[0] for c in cur.execute.call_args_list)
    assert 'RELEASE_LOCK' in cur.execute.call_args.args[0]


def test_history_does_not_use_live_data_or_fake_prior_month(monkeypatch):
    _,cur=mock_db(monkeypatch)
    cur.fetchall.return_value=[]
    monkeypatch.setattr(s,'current_month',lambda:'2026-09')
    monkeypatch.setattr(s,'live_sku',lambda:(_ for _ in ()).throw(AssertionError('historical live call')))
    result=s.sku_summary('2026-08')
    assert result['metric']['value'] is None and result['metric']['delta'] is None


def test_internal_routes_are_protected_and_get_does_not_save(monkeypatch):
    app=FastAPI();app.include_router(api.router)
    client=TestClient(app)
    assert client.get('/api/v1/finance/home-inventory/summary').status_code in (401,403)
    assert client.post('/api/v1/finance/home-inventory/sku-snapshot').status_code in (401,403)
    app.dependency_overrides[require_internal_access]=lambda:None
    monkeypatch.setattr(s,'inventory_summary',lambda m:dict(report_month=m))
    assert client.get('/api/v1/finance/home-inventory/summary?month=2026-09').json()['data']['report_month']=='2026-09'
    assert client.get('/api/v1/finance/home-inventory/sku-snapshot').status_code==405


def test_sku_history_month_and_version_alignment(monkeypatch):
    _,cur=mock_db(monkeypatch)
    monkeypatch.setattr(s,'current_month',lambda:'2026-10')
    cur.fetchall.return_value=[dict(stat_month=m,payload_json=dict(rule_version=v,total=n,platforms={}))
                              for m,v,n in [('2026-09',1,20),('2026-08',1,25)]]
    result=s.sku_summary('2026-09')
    assert result['metric']['delta']==-5 and result['metric']['direction']=='down'
    cur.fetchall.return_value[1]['payload_json']['rule_version']=0
    assert s.sku_summary('2026-09')['metric']['previous'] is None


def test_busy_or_month_boundary_never_writes_wrong_month(monkeypatch):
    conn,cur=mock_db(monkeypatch)
    cur.fetchone.return_value={'acquired':0}
    with pytest.raises(ValueError): s.capture_sku()
    conn.commit.assert_not_called()
    cur.fetchone.return_value={'acquired':1}
    monkeypatch.setattr(s,'live_sku',lambda:dict(stat_month='2026-09'))
    monkeypatch.setattr(s,'current_month',lambda:'2026-10')
    with pytest.raises(ValueError): s.capture_sku()
    assert not any('INSERT' in c.args[0] for c in cur.execute.call_args_list)
