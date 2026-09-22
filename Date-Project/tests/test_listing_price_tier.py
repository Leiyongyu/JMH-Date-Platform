import copy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import deps
from backend.api.v1 import ebay_price_tier, amz_price_tier
from backend.services import listing_price_tier_service as service
from backend.repositories import listing_price_tier_repository as repo


def candidate(price='100', **kw):
    return dict(dict(store_key='store',store_name='shop',site='DE',currency='EUR',sku='SKU',price=price,missing_shop=False),**kw)


@pytest.mark.parametrize('price,index',[('0',0),('339.999999',0),('340',1),('679.999999',1),('680',2),('1019.999999',2),('1020',3),('1690',3),('1690.000001',4)])
def test_cny_boundaries(price,index):
    report=service.summarize([candidate(price)],{'EUR':'1'})
    parent=report['items'][0]
    assert parent['tiers'][index]['sku_count']==1
    assert parent['tiers'][index]['sku_percent']=='100.00'
    assert len(parent['tiers'])==5 and parent['tiers']==parent['children'][0]['tiers']


def test_rate_full_precision_not_rounding_native_price():
    group=service.summarize([candidate('44.73645')],{'EUR':'7.600066'})['items'][0]
    # 339.999??? falls below 340, whereas rounding native price to 44.74 flips it.
    assert Decimal('44.73645')*Decimal('7.600066')<340
    assert group['tiers'][0]['sku_count']==1


@pytest.mark.parametrize('rate',[None,'','bad','0','-1','NaN','Infinity'])
def test_missing_bad_rate_not_zero_or_fallback(rate):
    report=service.summarize([candidate()],{'EUR':rate})
    assert report['total_sku_count']==0 and report['unclassified_sku_count']==1
    assert report['missing_rate_rows']==1 and report['missing_currencies']==['EUR']


@pytest.mark.parametrize('price',[None,'','bad','-1','NaN','Infinity',True])
def test_invalid_price_not_counted(price):
    result=service.summarize([candidate(price)],{'EUR':'7.6'})
    assert result['total_sku_count']==0 and result['invalid_price_rows']==1


def test_lowest_cny_dedup_within_site_and_parent_adds_sites():
    rows=[candidate('100'),candidate('40'),candidate('bad'),candidate('50',currency='USD'),candidate('100',site='UK')]
    before=copy.deepcopy(rows)
    report=service.summarize(rows,{'EUR':'7.6','USD':'6.58'})
    parent=report['items'][0]
    assert rows==before and parent['group_sku_count']==2
    assert parent['tiers'][0]['sku_count']==1 and parent['tiers'][2]['sku_count']==1
    assert parent['tiers'][0]['sku_percent']=='50.00'
    assert all(sum(c['tiers'][i]['sku_count'] for c in parent['children'])==t['sku_count'] for i,t in enumerate(parent['tiers']))
    assert report['unclassified_sku_count']==0 and report['invalid_price_rows']==1


def test_separate_stores_missing_sku_full_sku_and_zero_rate_cny():
    rows=[candidate(sku=''),candidate(sku='2PC-A'),candidate(sku='A'),candidate(sku='a'),candidate(store_key='other')]
    report=service.summarize(rows,{'EUR':1})
    assert report['shop_count']==2 and report['total_sku_count']==4 and report['missing_sku_rows']==1
    assert service.summarize([candidate(currency='CNY')],{})['total_sku_count']==0


def test_amz_landed_price_not_other_price_status_and_store_merge():
    shops={'1':dict(store_name='EU-example-DE',country_code='DE'),'2':dict(store_name='EU-example-UK',country_code='UK')}
    base=dict(sid=1,marketplace='Germany',status=1,is_delete=0,seller_sku='x',local_sku='different',currency_code='EUR',landed_price='100',price='1')
    rows=[base,{**base,'sid':2},{**base,'status':0},{**base,'is_delete':1}]
    candidates=list(service.amz_candidates(rows,shops))
    assert len(candidates)==2 and candidates[0]['price']=='100' and candidates[0]['sku']=='x'
    assert candidates[0]['store_key']==candidates[1]['store_key'] and candidates[0]['store_name']=='EU-example'
    report=service.summarize(candidates,{'EUR':'7.6'})
    assert report['shop_count']==1 and report['total_sku_count']==2
    assert report['items'][0]['tiers'][2]['sku_count']==2
    assert service.amz_shop(1,{'1':dict(store_name='EU-example-UK',country_code='DE')})['store_name']=='EU-example-UK'
    assert service.amz_shop(9,shops)['missing_shop']


def test_ebay_variants_no_parent_double_count():
    row=dict(seller_user_id='a',seller_account='shop',sku='parent',site='DE',current_price='1',currency='EUR',normalized_json={'variations':[
        {'sku':'a','price':{'value':'100','currency':'EUR'}},{'sku':'b','price':{'value':'200','currency':'EUR'}}]})
    result=service.summarize(service.ebay_candidates([row]),{'EUR':'7.6'})
    assert result['total_sku_count']==2
    assert result['items'][0]['tiers'][2]['sku_count']==1 and result['items'][0]['tiers'][3]['sku_count']==1


@pytest.mark.parametrize('data',['bad',None,[],{'variations':{}},{'variations':[None]}])
def test_bad_variant_structure_fails(data):
    with pytest.raises(ValueError): list(service.ebay_candidates([{'normalized_json':data}]))


def mocks(monkeypatch):
    conn,cur=MagicMock(),MagicMock(); conn.cursor.return_value.__enter__.return_value=cur
    ctx=MagicMock();ctx.__enter__.return_value=conn
    monkeypatch.setattr(repo,'db_connection',lambda:ctx)
    cur.fetchone.return_value={'acquired':1}
    # 美元报表换算EUR时还要USD交叉汇率；缺了会被"缺当月汇率整份拒绝"挡在写库之前，
    # 那样ebay相关用例测到的就不是它们各自想测的分支了。
    monkeypatch.setattr(repo,'context',lambda *_:dict(rate_month='2026-09',rates={'EUR':'7.6','USD':'6.8'},
                                                     rate_months={'EUR':'2026-09','USD':'2026-09'}))
    monkeypatch.setattr(repo,'source',lambda *_:([candidate()],[],1))
    return conn,cur


def test_publish_platform_scoped_only_new_dws(monkeypatch):
    conn,cur=mocks(monkeypatch)
    result=repo.rebuild('amz')
    assert result['platform']=='amz' and result['rate_month']=='2026-09'
    conn.commit.assert_called_once()
    writes=[c for c in cur.execute.call_args_list if c.args[0].startswith(('DELETE','INSERT','UPDATE'))]
    assert all('dws_listing_cny_price' in c.args[0] for c in writes)
    assert writes[0].args[1]==('amz',) and 'WHERE platform=%s' in writes[0].args[0]
    assert len(cur.executemany.call_args.args[1])==10


def test_rollback_on_insert_failure_and_busy_lock(monkeypatch):
    conn,cur=mocks(monkeypatch);cur.executemany.side_effect=RuntimeError('fail')
    with pytest.raises(RuntimeError):repo.rebuild('ebay')
    conn.commit.assert_not_called(); assert conn.rollback.call_count==2
    assert 'RELEASE_LOCK' in cur.execute.call_args.args[0]
    conn,cur=mocks(monkeypatch);cur.fetchone.return_value={'acquired':0}
    with pytest.raises(repo.ReportBusy):repo.rebuild('amz')
    assert cur.execute.call_count==1


def test_source_amz_uses_exact_raw_table_and_active_filter():
    cur=MagicMock();cur.fetchall.side_effect=[[{'sync_batch_id':'b','n':20}],[]]
    repo.source(cur,'amz',dict(source={'sync_batch_id':'b','row_count':20},shops={}))
    sql=' '.join(c.args[0] for c in cur.execute.call_args_list)
    assert 'ods_lingxing_amz_listing_latest' in sql and 'landed_price' in sql
    assert 'status=1 AND is_delete=0' in sql and 'amz_product_listing' not in sql
    cur.fetchall.side_effect=[[{'sync_batch_id':'wrong','n':20}]]
    with pytest.raises(ValueError):repo.source(cur,'amz',dict(source={'sync_batch_id':'b','row_count':20},shops={}))


@pytest.mark.parametrize('platform,field', [('ebay','rate_org'), ('amz','my_rate')])
def test_month_context_falls_back_to_each_currency_latest_month(platform,field):
    """汇率按币种各取最新可用月份；当月没同步时回退，不再整份卡住。

    同时记录每个币种实际取自哪个月，页面才能说明用的是哪一版汇率。
    """
    cur=MagicMock()
    cur.fetchall.side_effect=[[{'currency_code':'EUR','rate_month':'2026-09','rate':Decimal('7.600066')},
                               {'currency_code':'USD','rate_month':'2026-08','rate':Decimal('6.8')}],[]]
    ctx=repo.context(cur,platform)
    assert ctx['rates']=={'EUR':'7.600066','USD':'6.8'}
    assert ctx['rate_months']=={'EUR':'2026-09','USD':'2026-08'}
    sql=cur.execute.call_args_list[0].args[0]
    assert f'c.{field} rate' in sql and 'MAX(x.rate_month)' in sql
    # 不取未来月份，且只在有正值的行里挑最新月份。
    assert sql.count('rate_month<=%s')==2
    assert f'{field} IS NOT NULL' in sql and f'{field}>0' in sql
    assert cur.execute.call_args_list[0].args[1]==(ctx['rate_month'],ctx['rate_month'])


@pytest.mark.parametrize('change',['month','rate','batch'])
def test_read_marks_changed_month_rate_or_source_stale(monkeypatch,change):
    conn,cur=mocks(monkeypatch)
    ctx=dict(rate_month='2026-09',rates={'EUR':'7.6'},source={'batch':'old'})
    report=service.summarize([candidate()],ctx['rates'])
    cur.fetchone.return_value=dict(report_id='r',summary_json={k:v for k,v in report.items() if k!='items'},source_context_json=ctx)
    rows=[]
    for node in [report['items'][0]]+report['items'][0]['children']:
        meta={k:v for k,v in node.items() if k not in ('tiers','children')}
        rows += [dict(node_id=node['node_id'],node_json=meta,tier_no=t['tier_no'],sku_count=t['sku_count'],sku_percent=t['sku_percent']) for t in node['tiers']]
    cur.fetchall.return_value=rows
    changed=copy.deepcopy(ctx)
    if change=='month':changed['rate_month']='2026-10'
    if change=='rate':changed['rates']['EUR']='8.0'
    if change=='batch':changed['source']['batch']='new'
    monkeypatch.setattr(repo,'context',lambda *_:changed)
    result=repo.read_report('amz')
    assert result['stale'] and result['total_sku_count']==1
    conn.commit.assert_not_called()


def test_no_source_rate_fallback_or_new_platform_injection(monkeypatch):
    conn,cur=mocks(monkeypatch)
    with pytest.raises(ValueError):repo.rebuild('unknown')
    cur.execute.assert_not_called()


@pytest.mark.parametrize('platform',['amz','ebay'])
def test_api_auth_and_correct_platform(monkeypatch,platform):
    monkeypatch.setattr(deps,'settings',SimpleNamespace(python_internal_api_token='test'))
    read,refresh=MagicMock(return_value={'platform':platform}),MagicMock(return_value={'platform':platform})
    monkeypatch.setattr(service,'read_report',read);monkeypatch.setattr(service,'refresh_report',refresh)
    app=FastAPI();app.include_router(amz_price_tier.router);app.include_router(ebay_price_tier.router)
    with TestClient(app) as client:
        base='/api/v1/finance/'+platform+'-price-tier'
        assert client.post(base+'/refresh').status_code==401
        assert client.get(base+'/summary').status_code==401
        read.assert_not_called();refresh.assert_not_called()
        headers={'X-Internal-Token':'test'}
        assert client.get(base+'/summary',headers=headers).json()['data']['platform']==platform
        assert client.post(base+'/refresh',headers=headers).status_code==200
        read.assert_called_once_with(platform);refresh.assert_called_once_with(platform)
        refresh.side_effect=repo.ReportBusy('busy')
        assert client.post(base+'/refresh',headers=headers).status_code==409


@pytest.mark.parametrize(('platform', 'rates', 'missing'), [
    # eBay美元：缺欧元汇率 → 该站点整批换算不出来
    ('ebay', {'USD': '6.7787'}, 'EUR'),
    # eBay美元：欧元有、但缺USD交叉汇率 → 除USD原价外全军覆没
    ('ebay', {'EUR': '7.8397'}, 'USD'),
    # AMZ人民币：缺欧元汇率
    ('amz', {}, 'EUR'),
])
def test_missing_month_rate_refuses_to_publish_instead_of_dropping_skus(
        monkeypatch, platform, rates, missing):
    """缺当月汇率必须整份拒绝，不能发布少掉一大批SKU却看着正常的报表。

    历史行为是把换不出来的商品静默排除、只留一行角标提示：例如缺EUR/GBP时
    eBay报表会从17050个SKU缩到只剩USD站点的5061个，图表照常渲染。
    与批次/行数校验一样按"保留旧报表"处理。
    """
    conn, cur = mocks(monkeypatch)
    monkeypatch.setattr(repo, 'context', lambda *_: dict(rate_month='2026-09', rates=rates,
                                                        rate_months={c: '2026-09' for c in rates}))
    with pytest.raises(ValueError) as failure:
        repo.rebuild(platform)
    message = str(failure.value)
    assert missing in message and '2026-09' in message
    assert ('rate_org' if platform == 'ebay' else 'my_rate') in message
    assert '保留上一次报表' in message
    # 拒绝必须发生在写库之前：旧报表一行都不能被删或被覆盖。
    conn.commit.assert_not_called()
    cur.executemany.assert_not_called()
    assert not [c for c in cur.execute.call_args_list
                if c.args[0].lstrip().startswith(('DELETE', 'INSERT', 'UPDATE'))]
    assert 'RELEASE_LOCK' in cur.execute.call_args.args[0]


def test_complete_rates_still_publish_normally(monkeypatch):
    """汇率齐全时行为不变，新增的校验不能误伤正常发布。"""
    conn, cur = mocks(monkeypatch)
    monkeypatch.setattr(repo, 'context',
                        lambda *_: dict(rate_month='2026-09', rates={'EUR': '7.8397', 'USD': '6.7787'},
                                        rate_months={'EUR': '2026-09', 'USD': '2026-09'}))
    result = repo.rebuild('ebay')
    assert result['state'] == 'READY' and result['missing_currencies'] == []
    conn.commit.assert_called_once()


def test_current_month_gap_falls_back_instead_of_blocking(monkeypatch):
    """当月还没同步汇率时照常出报表，用各币种最近有值的月份兜底。

    这是"缺汇率整份拒绝"的边界：拒绝只针对某币种任何月份都查不到汇率，
    不能因为当月任务还没跑就把报表卡住。
    """
    conn, cur = mocks(monkeypatch)
    monkeypatch.setattr(repo, 'context', lambda *_: dict(
        rate_month='2026-10',
        rates={'EUR': '7.8397', 'USD': '6.7787'},
        rate_months={'EUR': '2026-09', 'USD': '2026-08'}))
    result = repo.rebuild('ebay')
    assert result['state'] == 'READY' and result['missing_currencies'] == []
    # 统计月份仍是当月，但要如实记下每个币种实际用的是哪一版汇率。
    assert result['rate_month'] == '2026-10'
    assert result['rate_months'] == {'EUR': '2026-09', 'USD': '2026-08'}
    conn.commit.assert_called_once()
