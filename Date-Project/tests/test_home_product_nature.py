from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import deps
from backend.api.v1 import amz_owner_sku, ebay_owner_sku, home_inventory
from backend.services import home_product_nature_service as s
from backend.repositories import home_product_nature_repository as r

NOW = datetime(2026,9,23,12,tzinfo=ZoneInfo('Asia/Shanghai'))
RULES = {('EU','BRAND','ABC'):'甲',('EU','OTH_CODE','123'):'乙',
         ('US1','STORE','甲店'):'甲',('US2','STORE','乙店'):'乙',('US1','STORE','空店'):'零销量'}
EBAY = {('','EBAY_BRAND','ABC'):'甲',('','EBAY_BRAND','CL'):'任雅婷'}


def row(sku='ABC-1',store='EU-甲店-DE',age=30,**extra):
    return dict(seller_sku=sku,msku=sku,local_sku=sku,store_name=store,store_id='1',sid=1,site='DE',
                replenishment_regions=['EU'] if store and store.startswith('EU-') else ['US'] if store and store.startswith('US') else [],
                first_listing_date=None if age is None else (NOW-timedelta(days=age)).date(),sync_time=NOW,**extra)


def source(rows=None,rules=None):
    return dict(rows=[row()] if rows is None else rows,rules=RULES if rules is None else rules,
                ready=True,sync={'status':'SUCCESS'})


@pytest.mark.parametrize('threshold,age,expected',[(60,60,'NEW'),(60,61,'OLD'),(90,90,'NEW'),(90,91,'OLD')])
def test_boundaries(threshold,age,expected):
    assert s.classify(NOW.date()-timedelta(days=age),NOW.date(),threshold)[0]==expected


@pytest.mark.parametrize('value',[None,'','bad','2026-02-30'])
def test_missing_invalid_dates_are_unknown_not_old(value):
    assert s.classify(value,NOW.date(),60)==('UNKNOWN',None,None,'MISSING_LISTING_DATE')


def test_future_date_retains_existing_semantics_but_warns():
    assert s.classify('2026-09-24',NOW.date(),60)==('NEW','2026-09-24',-1,'FUTURE_LISTING_DATE')


@pytest.mark.parametrize('value,site,expected',[
    ('07/06/2024 14:55:53 BST','UK','2024-06-07'),
    ('07/06/2024 14:55:53 GMT','DE','2024-06-07'),
    ('1/9/2026','FR','2026-09-01'),
    ('2026-09-01T23:00:00 UTC','FR','2026-09-01'),
    ('2026-09-01 15:00:00 PDT','US','2026-09-01'),
    ('2026-09-01','NL','2026-09-01'),
    ('07/06/2024','UNKNOWN',None),('07/06/2024','US',None),
    ('31/02/2026','DE',None),('2026-02-30','US',None),('', 'UK',None),
])
def test_raw_open_date_site_formats(value,site,expected):
    result=s.amz_open_date(value,site)
    assert (result.isoformat() if result else None)==expected


def test_open_date_is_preserved_and_never_falls_back_to_display():
    rows=[{**row('ABC-1'),'first_listing_date':'07/06/2024 14:55:53 BST'},
          {**row('ABC-2'),'first_listing_date':None,'open_date_display':'2026-09-01'},
          {**row('ABC-3'),'first_listing_date':'31/02/2026','open_date_display':'2026-09-01'}]
    report,facts=s.build('amz',source(rows),NOW)
    assert report['counts']==dict(NEW=0,OLD=3,UNKNOWN=0,CONFLICT=0)
    assert report['audit']['missing_or_invalid_date_as_old_rows']==2
    assert report['period_kind']=='MONTHLY' and report['rule_version']==s.AMZ_VERSION
    assert facts[0]['first_listing_date']=='2024-06-07'
    assert facts[0]['variants'][0]['open_date_raw']=='07/06/2024 14:55:53 BST'
    assert facts[1]['reasons']==['MISSING_LISTING_DATE']
    assert facts[2]['reasons']==['INVALID_OPEN_DATE']
    assert all(f['nature_source']=='ods_lingxing_amz_listing_latest.open_date' for f in facts)


def test_source_and_rules_not_ready_not_zero():
    for changes,state in [({'ready':False},'SOURCE_NOT_READY'),({'rules':{}},'MISSING_RULES')]:
        result,facts=s.build('amz',{**source(),**changes},NOW)
        assert result['state']==state and result['sku_count'] is None and facts==[]


def test_empty_real_source_zero_roster_without_fake_facts():
    report,facts=s.build('amz',source(rows=[]),NOW)
    assert report['state']=='EMPTY' and report['sku_count']==0 and not facts
    assert all(i['sku_count']==0 for i in report['owners'])
    assert report['percentages']['NEW'] is None


def test_pc_and_missing_sku_match_homepage():
    rows=[row('PC-1'),row('123PC-ABC-1'),{**row(),'local_sku':'4PC-ABC'},row(''),row('ABC-PC-1')]
    report,facts=s.build('amz',source(rows),NOW)
    assert report['sku_count']==1 and report['audit']['excluded_pc_rows']==3
    assert report['audit']['missing_sku_rows']==1
    assert facts[0]['sku']=='ABC-PC-1'


def test_platform_group_and_details_grains_with_conflicts():
    rows=[row(age=20),{**row(age=100),'store_id':'2'},row(store='US1-甲店-US',age=20)]
    report,facts=s.build('amz',source(rows),NOW)
    assert report['sku_count']==1 and report['counts']['CONFLICT']==1
    assert report['group_attributed_count']==2 and report['cross_group_duplicate_count']==1
    assert report['detail_rows']==3
    assert all(f['platform_nature']=='CONFLICT' for f in facts)
    assert {i['group_code']:i['counts']['OLD'] for i in report['groups']}['EU']==1
    assert sum(i['sku_count'] for i in report['owners'])==report['group_attributed_count']


def test_same_grain_different_local_sku_and_date_preserves_variants():
    rows=[row(age=20),{**row(age=100),'local_sku':'ABC-2'},row(age=20)]
    report,facts=s.build('amz',source(rows),NOW)
    assert len(facts)==1 and len(facts[0]['variants'])==2
    assert facts[0]['nature']=='OLD' and facts[0]['age_days']==100
    assert facts[0]['local_sku'] is None
    assert report['sku_count']==1


def test_ebay_cl_difference_is_reported_legacy_unchanged():
    rows=[row('CL-1'),row('CL-2'),row('FLL-1'),row('JMH-1')]
    report,facts=s.build('ebay',source(rows,EBAY),NOW)
    assert {f['principal_name'] for f in facts if f['sku'].startswith('CL')}=={'陈丽'}
    assert report['reconciliation']['legacy_card_changed'] is False
    assert {d['principal_name']:d['delta'] for d in report['reconciliation']['owner_differences']}=={'任雅婷':-2,'陈丽':2}
    assert next(f for f in facts if f['sku']=='JMH-1')['principal_name']=='未分配'
    assert s.ebay_owner_sku_service.summarize(rows,EBAY)['items']!=[]


def test_group_and_owner_paths_reuse_performance():
    rows=[row('OTH-123-1'),row(store='EU-甲店-UK'),row(store='US3-新志楠-US'),row(store='US3-另一店-US'),row(store=None)]
    report,facts=s.build('amz',source(rows),NOW)
    assert facts[0]['principal_name']=='乙' and facts[0]['owner_match_source']=='AMAZON_OTH_CODE'
    assert facts[1]['principal_name']=='吴清栩'
    assert facts[2]['group_code']=='US2-MJ'
    assert facts[3]['group_code']=='US1-ZXY'
    assert facts[4]['group_code']=='UNKNOWN_GROUP' and facts[4]['nature']=='UNKNOWN'


def test_ambiguous_rules_fail_not_pick_first():
    with pytest.raises(ValueError,match='冲突'):
        s.build('amz',source(rules={**RULES,('US2','STORE','甲店'):'丙'}),NOW)
    with pytest.raises(ValueError,match='冲突'):
        s.build('ebay',source(rules={**EBAY,('EBAY-1','EBAY_BRAND','CL'):'丙'}),NOW)


def fake_transaction(monkeypatch):
    conn=MagicMock(); cur=MagicMock();conn.cursor.return_value.__enter__.return_value=cur
    @contextmanager
    def tx(**kwargs):
        try:
            yield conn
            if kwargs.get('write'): conn.commit()
        except Exception:
            conn.rollback();raise
    monkeypatch.setattr(r,'transaction',tx)
    return conn,cur


def test_frozen_query_never_reads_current_rules(monkeypatch):
    fake_transaction(monkeypatch);monkeypatch.setattr(s,'now',lambda:NOW)
    load=MagicMock(side_effect=AssertionError('no live reads'));monkeypatch.setattr(r,'load_source',load)
    monkeypatch.setattr(r,'read_report',lambda *a:None)
    assert s.get_report('amz','2026-08')['state']=='NO_SNAPSHOT'
    load.assert_not_called()


@pytest.mark.parametrize('month',['2026-13','2026-9',"2026-09'",'2026-10'])
def test_invalid_future_month_rejected(monkeypatch,month):
    monkeypatch.setattr(s,'now',lambda:NOW)
    with pytest.raises(ValueError):s.get_report('amz',month)


@pytest.mark.parametrize('options',[{'page_size':101},{'page':0},{'nature':'bad'},{'owner_key':'x'}])
def test_invalid_filters_rejected_before_db(monkeypatch,options):
    monkeypatch.setattr(s,'now',lambda:NOW)
    with pytest.raises(ValueError):s.get_report('amz',view='details',**options)


def test_cache_invalidation_and_same_day_reuse(monkeypatch):
    report,facts=s.build('amz',source(),NOW);report['cache_token']='same'
    monkeypatch.setattr(r,'source_token',lambda *a:'same')
    monkeypatch.setattr(r,'read_report',lambda *a:report)
    load=MagicMock(return_value=source());monkeypatch.setattr(r,'load_source',load)
    pub=MagicMock();monkeypatch.setattr(r,'publish',pub);monkeypatch.setattr(s,'now',lambda:NOW)
    assert s._load(None,'amz','2026-09',NOW) is report
    load.assert_not_called();pub.assert_not_called()
    monkeypatch.setattr(r,'source_token',lambda *a:'changed')
    assert s._load(None,'amz','2026-09',NOW)['cache_token']=='changed'
    pub.assert_called_once()
    assert pub.call_args.args[3]=='MONTHLY'


def test_past_amz_month_uses_saved_monthly_and_details_kind(monkeypatch):
    fake_transaction(monkeypatch);monkeypatch.setattr(s,'now',lambda:NOW)
    report,_=s.build('amz',source(),NOW.replace(month=8))
    read=MagicMock(return_value=report);monkeypatch.setattr(r,'read_report',read)
    monkeypatch.setattr(r,'load_source',MagicMock(side_effect=AssertionError('no current source')))
    details=MagicMock(return_value=dict(items=[],total=0));monkeypatch.setattr(r,'details',details)
    result=s.get_report('amz','2026-08',view='details')
    assert result['live'] is False
    assert read.call_args.args[3]=='MONTHLY' and details.call_args.args[3]=='MONTHLY'


def test_current_amz_history_provisional_ebay_not(monkeypatch):
    fake_transaction(monkeypatch);monkeypatch.setattr(s,'now',lambda:NOW)
    report,_=s.build('amz',source(),NOW)
    monkeypatch.setattr(r,'history',lambda *a:[report])
    assert s.get_history('amz')['items'][-1]['provisional'] is True
    assert s.get_history('ebay')['items'][-1]['provisional'] is False


def test_sql_pagination_and_literal_search_not_python_slice():
    conn,cur=MagicMock(),MagicMock();conn.cursor.return_value.__enter__.return_value=cur
    cur.fetchone.return_value={'total':30};cur.fetchall.return_value=[{'payload_json':'{"sku":"A"}'}]
    result=r.details(conn,'amz','2026-09','LIVE',group_code='EU',sku="a%'",nature='CONFLICT',page=2,page_size=10)
    assert result['total']==30 and len(result['items'])==1
    sql,args=cur.execute.call_args.args
    assert 'LIMIT %s OFFSET %s' in sql and args[-2:]==(10,10)
    assert 'group_nature=%s' in sql and "a%'" not in sql
    assert "A%'" in args


def test_month_end_amz_overwrite_ebay_freeze_in_one_transaction(monkeypatch):
    end=NOW.replace(day=30);monkeypatch.setattr(s,'now',lambda:end)
    conn,cur=fake_transaction(monkeypatch)
    monkeypatch.setattr(r,'read_report',lambda *a:None)
    monkeypatch.setattr(r,'load_source',lambda c,p,m:source(rules=RULES if p=='amz' else EBAY))
    pub=MagicMock();monkeypatch.setattr(r,'publish',pub)
    result=s.capture_monthly()
    assert pub.call_count==2 and conn.commit.call_count==1
    assert {c.args[1]['batch_id'] for c in pub.call_args_list}=={result['batch_id']}
    assert [c.args[3] for c in pub.call_args_list]==['MONTHLY','FROZEN']
    assert all(c.args[1]['live'] is False for c in pub.call_args_list)
    assert 'dws_home_inventory_sku_monthly' in cur.execute.call_args.args[0]


def test_month_end_second_platform_failure_rolls_back_everything(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW.replace(day=30))
    conn,_=fake_transaction(monkeypatch)
    monkeypatch.setattr(r,'read_report',lambda *a:None)
    monkeypatch.setattr(r,'load_source',lambda c,p,m:source(rules=RULES if p=='amz' else EBAY))
    pub=MagicMock(side_effect=[None,RuntimeError('write fail')]);monkeypatch.setattr(r,'publish',pub)
    with pytest.raises(RuntimeError):s.capture_monthly()
    conn.commit.assert_not_called();conn.rollback.assert_called_once()


def test_month_end_missing_source_writes_nothing(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW.replace(day=30))
    fake_transaction(monkeypatch);monkeypatch.setattr(r,'read_report',lambda *a:None)
    monkeypatch.setattr(r,'load_source',lambda c,p,m:{**source(), 'ready':p=='amz'})
    pub=MagicMock();monkeypatch.setattr(r,'publish',pub)
    with pytest.raises(ValueError,match='全部就绪'):s.capture_monthly()
    pub.assert_not_called()


def test_month_end_repeated_capture_updates_amz_not_frozen_ebay(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW)
    with pytest.raises(ValueError,match='月末'):s.capture_monthly()
    monkeypatch.setattr(s,'now',lambda:NOW.replace(day=30));fake_transaction(monkeypatch)
    existing,_=s.build('ebay',source(rules=EBAY),NOW)
    existing.update(period_kind='FROZEN',live=False)
    monkeypatch.setattr(r,'read_report',lambda *a:existing if a[1]=='ebay' else None)
    load=MagicMock(return_value=source());monkeypatch.setattr(r,'load_source',load)
    pub=MagicMock();monkeypatch.setattr(r,'publish',pub)
    assert s.capture_monthly()['ebay_already_frozen'] is True
    assert load.call_count==1 and load.call_args.args[1]=='amz'
    pub.assert_called_once()
    assert pub.call_args.args[3]=='MONTHLY'
    assert existing['period_kind']=='FROZEN' and existing['live'] is False


def test_month_switch_aborts_publication(monkeypatch):
    fake_transaction(monkeypatch);monkeypatch.setattr(r,'read_report',lambda *a:None)
    monkeypatch.setattr(r,'load_source',lambda c,p,m:source(rules=RULES if p=='amz' else EBAY))
    clock=iter([NOW.replace(day=30),NOW.replace(month=10,day=1)])
    monkeypatch.setattr(s,'now',lambda:next(clock))
    pub=MagicMock();monkeypatch.setattr(r,'publish',pub)
    with pytest.raises(ValueError,match='跨月'):s.capture_monthly()
    pub.assert_not_called()


def test_history_missing_month_and_versions(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW);fake_transaction(monkeypatch)
    monkeypatch.setattr(r,'history',lambda *a:[])
    assert all(i['sku_count'] is None for i in s.get_history('amz')['items'])
    monkeypatch.setattr(r,'read_report',lambda c,p,m,k:dict(rule_version=m))
    assert s.compare('amz','2026-07','2026-08')['state']=='VERSION_MISMATCH'


def test_compare_owner_added_and_removed(monkeypatch):
    monkeypatch.setattr(s,'now',lambda:NOW);fake_transaction(monkeypatch)
    a,_=s.build('amz',source([row()]),NOW)
    b,_=s.build('amz',source([row(),row('ABC-2')]),NOW)
    monkeypatch.setattr(r,'read_report',lambda c,p,m,k:a if m=='2026-07' else b)
    assert s.compare('amz','2026-07','2026-08')['items'][0]['delta_sku_count']==1


@pytest.mark.parametrize('platform,router',[('amz',amz_owner_sku.router),('ebay',ebay_owner_sku.router)])
@pytest.mark.parametrize('view',['summary','groups','owners','details','history','compare'])
def test_all_routes_internal_auth_and_invalid_query(monkeypatch,platform,router,view):
    monkeypatch.setattr(deps,'settings',SimpleNamespace(python_internal_api_token='test'))
    monkeypatch.setattr(s,'get_history',lambda p,*args:dict(platform=p,items=[]))
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        url=f'/api/v1/finance/{platform}-owner-sku/nature/{view}'
        assert client.get(url).status_code==401
        response=client.get(url+'?month=bad&page_size=101&base_month=bad&target_month=bad',headers={'X-Internal-Token':'test'})
        if view!='history':assert response.status_code in (400,422)


def test_api_error_redaction_and_capture_auth(monkeypatch):
    monkeypatch.setattr(deps,'settings',SimpleNamespace(python_internal_api_token='test'))
    monkeypatch.setattr(s,'get_report',MagicMock(side_effect=RuntimeError('db-password')))
    app=FastAPI();app.include_router(amz_owner_sku.router);app.include_router(home_inventory.router)
    with TestClient(app) as client:
        result=client.get('/api/v1/finance/amz-owner-sku/nature/summary',headers={'X-Internal-Token':'test'})
        assert result.status_code==500 and 'db-password' not in result.text
        assert client.post('/api/v1/finance/home-inventory/product-nature-snapshot').status_code==401


def test_repo_transaction_rollback_and_lock_release(monkeypatch):
    conn,cur=MagicMock(),MagicMock();conn.cursor.return_value.__enter__.return_value=cur
    cur.fetchone.return_value={'acquired':1}
    ctx=MagicMock();ctx.__enter__.return_value=conn;monkeypatch.setattr(r,'db_connection',lambda:ctx)
    with pytest.raises(RuntimeError):
        with r.transaction(write=True):raise RuntimeError('fail')
    conn.commit.assert_not_called();conn.rollback.assert_called_once()
    assert 'RELEASE_LOCK' in cur.execute.call_args.args[0]
