from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import deps
from backend.api.v1 import amz_owner_sku, ebay_owner_sku
from backend.services import home_product_nature_service as s
from backend.repositories import home_product_nature_repository as r
from test_home_product_nature import NOW, EBAY, row, source, fake_transaction
from test_home_product_nature_repository import connection


@pytest.mark.parametrize('platform,segment', [('amz','EU'), ('amz','US'), ('ebay','德国')])
def test_owner_totals_equal_segment_not_platform_and_dedupe_stores(platform, segment):
    rows = [row(age=100), {**row(age=10), 'store_id':'2'}, row('ABC-2', age=10),
            {**row('JMH-1', age=100), 'store_id':'3'}, row(store='US1-甲店-US', age=10)]
    if platform == 'ebay':
        rows = [{**item, 'site':'德国' if i < 4 else '英国'} for i, item in enumerate(rows)]
    report, facts = s.build(platform, source(rows, EBAY if platform == 'ebay' else None), NOW)
    result = s.segment_owner_summary(report, facts, segment)
    expected = next(x for x in report['segments'] if x['segment_key'] == segment)
    assert result['state'] == 'READY' and result['reconciled']
    assert result['totals']['counts'] == expected['counts']
    assert sum(x['sku_count'] for x in result['items']) == expected['sku_count']
    if segment != 'US':
        assert any(x['principal_name'] == '未分配' for x in result['items'])


def test_amz_cross_owner_same_sku_is_counted_for_each_owner():
    report, facts = s.build('amz',source([row(age=100), row(store='EU-甲店-UK',age=5)]),NOW)
    result = s.segment_owner_summary(report,facts,'EU')
    assert result['totals']['sku_count'] == 2
    assert result['totals']['counts']['OLD'] == 2
    assert {x['principal_name'] for x in result['items']} == {'甲','吴清栩'}


def test_ebay_same_site_sku_multiple_owners_never_double_count():
    report, facts = s.build('ebay',source([row()],EBAY),NOW)
    facts.append({**facts[0], 'owner_key':'other', 'principal_name':'乙'})
    assert s.segment_owner_summary(report,facts,'DE')['state']=='OWNER_RECONCILIATION_FAILED'


@pytest.mark.parametrize('change', ['no_segments','old_detail','missing_rows','wrong_counts'])
def test_old_or_broken_snapshot_is_not_silently_recomputed(change):
    report, facts = s.build('amz',source(),NOW)
    if change=='no_segments': report.pop('segments')
    if change=='old_detail': facts[0].pop('segment_nature')
    if change=='missing_rows': facts=[]
    if change=='wrong_counts': report['segments'][0]['counts']['NEW']=900
    result=s.segment_owner_summary(report,facts,'EU')
    assert result['state'] in {'NO_SEGMENT_DETAIL','OWNER_RECONCILIATION_FAILED'}
    assert result['items']==[] and result['totals'] is None


def test_absent_site_is_real_zero_only_with_valid_saved_snapshot():
    report, facts = s.build('ebay',source([row()],EBAY),NOW)
    result=s.segment_owner_summary(report,facts,'法国')
    assert result['state']=='READY' and result['items']==[] and result['totals']['sku_count']==0


def test_historical_owner_route_only_uses_saved_batch_not_today_rules(monkeypatch):
    fake_transaction(monkeypatch); monkeypatch.setattr(s,'now',lambda:NOW)
    report, facts=s.build('amz',source(),NOW.replace(month=8))
    monkeypatch.setattr(r,'read_month_report',lambda *args:report)
    load=MagicMock(side_effect=AssertionError('must not read current source'))
    monkeypatch.setattr(r,'load_source',load)
    saved=MagicMock(return_value=facts); monkeypatch.setattr(r,'segment_owner_rows',saved)
    result=s.get_report('amz','2026-08','owners',segment_key='EU',batch_id=report['batch_id'])
    assert result['state']=='READY' and result['stat_month']=='2026-08'
    assert result['live'] is False
    assert saved.call_args.args[1:]==('amz','2026-08','MONTHLY',report['batch_id'])
    load.assert_not_called()


def test_stale_batch_returns_explicit_refresh_not_mixed_data(monkeypatch):
    fake_transaction(monkeypatch);monkeypatch.setattr(s,'now',lambda:NOW)
    report,_=s.build('amz',source(),NOW)
    monkeypatch.setattr(s,'_load',lambda *args:report)
    saved=MagicMock();monkeypatch.setattr(r,'segment_owner_rows',saved)
    result=s.get_report('amz',view='owners',segment_key='EU',batch_id='00000000-0000-0000-0000-000000000000')
    assert result['state']=='SNAPSHOT_CHANGED';saved.assert_not_called()


@pytest.mark.parametrize('filters', [dict(segment_key=''),dict(segment_key='CN'),
    dict(segment_key='EU',group_code='EU'),dict(segment_key='EU',batch_id='invalid')])
def test_invalid_filters_rejected_before_db(filters):
    with pytest.raises(ValueError):s.get_report('amz',view='owners',**filters)


def test_compact_saved_query_is_parameterized_and_batch_scoped():
    conn,cur=connection();cur.fetchall.return_value=[]
    r.segment_owner_rows(conn,'ebay','2026-08','FROZEN','batch')
    sql,args=cur.execute.call_args.args
    assert 'sync_batch_id=%s' in sql and 'JSON_EXTRACT' in sql
    assert args==('2026-08','ebay','FROZEN','batch')
    assert 'listing' not in sql and 'owner_rule' not in sql


@pytest.mark.parametrize('platform,router',[('amz',amz_owner_sku.router),('ebay',ebay_owner_sku.router)])
def test_owner_api_forwards_segment_batch_and_checks_auth(monkeypatch,platform,router):
    monkeypatch.setattr(deps,'settings',SimpleNamespace(python_internal_api_token='test'))
    call=MagicMock(return_value={'state':'READY','items':[]});monkeypatch.setattr(s,'get_report',call)
    app=FastAPI();app.include_router(router)
    batch='00000000-0000-0000-0000-000000000000'
    with TestClient(app) as client:
        url=f'/api/v1/finance/{platform}-owner-sku/nature/owners'
        assert client.get(url).status_code==401
        response=client.get(url,params=dict(month='2026-09',segment_key='EU',batch_id=batch),headers={'X-Internal-Token':'test'})
        assert response.status_code==200
    call.assert_called_once_with(platform,'2026-09','owners',group_code=None,segment_key='EU',batch_id=batch)
