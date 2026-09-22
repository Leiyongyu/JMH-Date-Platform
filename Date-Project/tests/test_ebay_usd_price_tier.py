import copy
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.services import listing_price_tier_service as service
from backend.repositories import listing_price_tier_repository as repo
from test_listing_price_tier import candidate, mocks


@pytest.mark.parametrize('price,index', [('0',0), ('49.999999',0), ('50',1), ('99.999999',1),
    ('100',2), ('149.999999',2), ('150',3), ('250',3), ('250.000001',4)])
def test_usd_original_ignores_missing_and_bad_rates(price,index):
    for rates in ({}, {'USD':'0'}, {'USD':'bad', 'EUR':'100'}):
        result=service.summarize([candidate(price,currency='USD')],rates,target_currency='USD')
        assert result['items'][0]['tiers'][index]['sku_count']==1
        assert result['missing_rate_rows']==0 and not result['missing_currencies']
        assert result['target_currency']=='USD' and result['rate_field']=='rate_org'
        assert result['version']==service.USD_VERSION


@pytest.mark.parametrize('boundary,index', [(50,1),(100,2),(150,3),(250,3)])
def test_cross_rate_exact_boundary_without_recurring_decimal_loss(boundary,index):
    # EUR 3 -> CNY 1 -> USD 1/7; multiplying by 7*boundary is exactly boundary.
    # Repeating-decimal intermediate rates would move some comparisons.
    rates={'EUR':'1','USD':'7'}
    rows=[candidate(str(boundary*7),sku='equal'),candidate(str(Decimal(boundary*7)-Decimal('.000000000000000000001')),sku='below')]
    report=service.summarize(rows,rates,target_currency='USD')
    counts=[t['sku_count'] for t in report['items'][0]['tiers']]
    assert counts[index]==(2 if boundary==250 else 1)
    assert counts[index-1]==(0 if boundary==250 else 1)


def test_fx_dedup_and_site_sum_use_usd_without_mutating_input():
    rows=[candidate('100',sku='A'),candidate('50',currency='USD',sku='A'),
          candidate('350',currency='CNY',sku='B'),candidate('100',site='UK',sku='A')]
    before=copy.deepcopy(rows)
    report=service.summarize(rows,{'EUR':'7.7','USD':'7'},target_currency='USD')
    parent=report['items'][0]
    assert rows==before and parent['group_sku_count']==3
    assert [t['sku_count'] for t in parent['tiers']]==[0,2,1,0,0]
    for i,t in enumerate(parent['tiers']):
        assert sum(c['tiers'][i]['sku_count'] for c in parent['children'])==t['sku_count']


@pytest.mark.parametrize('value',[None,'',0,'bad',-1,'NaN','Infinity'])
def test_foreign_currency_missing_usd_rate_excluded_but_usd_original_kept(value):
    report=service.summarize([candidate('100'),candidate('75',currency='USD',sku='USD')],
                             {'EUR':'7.7','USD':value},target_currency='USD')
    assert report['total_sku_count']==1 and report['unclassified_sku_count']==1
    assert report['missing_currencies']==['USD'] and report['missing_rate_rows']==1


def test_missing_original_rate_does_not_fallback_to_usd_rate():
    report=service.summarize([candidate()],{'USD':'7'},target_currency='USD')
    assert report['total_sku_count']==0 and report['missing_currencies']==['EUR']


def test_ebay_publish_only_new_usd_tables_and_read_reconstructs_usd(monkeypatch):
    conn,cur=mocks(monkeypatch)
    ctx=dict(rate_month='2026-09',rates={'EUR':'7.7','USD':'7'},
             rate_months={'EUR':'2026-09','USD':'2026-09'})
    monkeypatch.setattr(repo,'context',lambda *_:ctx)
    report=repo.rebuild('ebay')
    assert report['target_currency']=='USD' and report['items'][0]['tiers'][2]['sku_count']==1
    writes=[c.args[0] for c in cur.execute.call_args_list if c.args[0].startswith(('DELETE','INSERT','UPDATE'))]
    assert all('dws_ebay_usd_price_' in sql for sql in writes)
    assert 'dws_ebay_usd_price_tier' in cur.executemany.call_args.args[0]
    cur.fetchone.return_value=dict(report_id=report['report_id'],source_context_json=ctx,
                                  summary_json={k:v for k,v in report.items() if k!='items'})
    nodes=[report['items'][0]]+report['items'][0]['children']
    cur.fetchall.return_value=[dict(node_id=n['node_id'],node_json={k:v for k,v in n.items() if k not in ('tiers','children')},
        tier_no=t['tier_no'],sku_count=t['sku_count'],sku_percent=t['sku_percent']) for n in nodes for t in n['tiers']]
    read=repo.read_report('ebay')
    assert read['state']=='READY' and not read['stale']
    assert [t['range'] for t in read['items'][0]['tiers']]==list(service.USD_RANGES)
    ctx['rates']['USD']='8'
    # Stored context is immutable in real JSON; use an independent snapshot for test.
    cur.fetchone.return_value['source_context_json']={**ctx,'rates':{'EUR':'7.7','USD':'7'},
                                                     'rate_months':{'EUR':'2026-09','USD':'2026-09'}}
    assert repo.read_report('ebay')['stale']


def test_cny_version_never_relabelled_as_usd(monkeypatch):
    conn,cur=mocks(monkeypatch)
    cur.fetchone.return_value=dict(summary_json={'version':service.VERSION,'target_currency':'CNY'})
    report=repo.read_report('ebay')
    assert report['state']=='EMPTY' and report['stale']


def test_rate_org_read_not_my_rate_and_unusable_rows_excluded():
    """美元报表只读rate_org；rate_org为空或非正的月份由SQL过滤，不进rates。

    过滤后该币种要么回退到更早有值的月份，要么整个不出现——不出现即视为
    无可用汇率，由 rebuild 拒绝发布，不会被误当成0。
    """
    cur=MagicMock()
    cur.fetchall.side_effect=[[{'currency_code':'EUR','rate_month':'2026-09','rate':Decimal('7.7')}],[]]
    ctx=repo.context(cur,'ebay')
    assert ctx['rates']=={'EUR':'7.7'}
    assert ctx['rate_months']=={'EUR':'2026-09'}
    sql=cur.execute.call_args_list[0].args[0]
    assert 'rate_org' in sql and 'my_rate' not in sql
    # 空值与非正值在SQL层排除，不像过去那样以 None 留在 rates 里。
    assert 'rate_org IS NOT NULL' in sql and 'rate_org>0' in sql
