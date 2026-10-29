from backend.services import mixed_sales_site_detail_service as service
import pytest


@pytest.fixture(autouse=True)
def no_age_database(monkeypatch):
    monkeypatch.setattr(service, 'attach_ages', lambda *a, **k: None)


def test_merge_keeps_inventory_and_quotes_on_one_row_and_paginates_after_join(monkeypatch):
    inventory = dict(sku='SKU',sid=1,storeName='店铺一',site='UK',currency='GBP',amzMinPrice=10,amzMaxPrice=20,fbaStock=0,fbaInbound=2,fbaTotalInventory=2,sales30d=0)
    monkeypatch.setattr(service,'list_store_inventory',lambda **_: [inventory])
    monkeypatch.setattr(service,'list_sales',lambda **_:dict(items=[inventory],total=1,calculationVersion='v'))
    quotes = [dict(site='UK',currency='GBP',amzMinPrice=10,amzMaxPrice=20,ebayMinPrice=5,ebayMaxPrice=30),
              dict(site='DE',currency='EUR',amzMinPrice=None,amzMaxPrice=None,ebayMinPrice=9,ebayMaxPrice=19)]
    monkeypatch.setattr(service,'list_price_ranges',lambda **_:dict(items=quotes,total=2,months=['2026-10'],statMonth='2026-10'))
    result=service.list_site_details(sku='SKU',sort_field='ebayMinPrice',sort_order='desc',page_size=1)
    assert result['total']==2 and len(result['items'])==1
    assert result['items'][0]['site']=='DE' and result['items'][0]['fbaStock'] is None
    second=service.list_site_details(sku='SKU',sort_field='ebayMinPrice',sort_order='desc',page_size=1,page=2)['items'][0]
    assert second['fbaStock']==0 and second['sales30d']==0
    assert second['ebayMinPrice']==5 and second['amzMaxPrice']==20


def test_inventory_without_quote_is_kept_and_unknown_sites_never_share_inventory(monkeypatch):
    own=[dict(sku='SKU',site='UK',fbaStock=10),dict(sku='SKU',site=None,fbaStock=7)]
    monkeypatch.setattr(service,'list_store_inventory',lambda **_: [dict(r,sid=1,storeName='店铺一',currency=None) for r in own])
    monkeypatch.setattr(service,'list_sales',lambda **_:dict(items=own,total=2))
    monkeypatch.setattr(service,'list_price_ranges',lambda **_:dict(items=[
        dict(site=None,currency='EUR',unmatchedPlatform='EBAY',ebayMinPrice=4)],total=1,months=[],statMonth=None))
    rows=service.list_site_details(sku='SKU')['items']
    assert len(rows)==3
    assert next(r for r in rows if r.get('currency')=='EUR')['fbaStock'] is None
    assert next(r for r in rows if r['site']=='UK')['ebayMinPrice'] is None
    assert next(r for r in rows if r['site'] is None and r.get('currency') is None)['fbaStock']==7


def test_fetches_every_page_and_pins_version_or_price_month():
    calls=[]
    def fetch(**params):
        calls.append(params)
        return dict(items=list(range(200)) if params['page']==1 else [200],total=201,
                    calculationVersion='saved',statMonth='2026-10')
    _,rows=service._all_pages(fetch,calculation_version=None,stat_month=None)
    assert len(rows)==201 and calls[1]['calculation_version']=='saved'
    assert calls[1]['stat_month']=='2026-10'


def test_ebay_joins_prices_inline_keeps_only_30_day_sales_and_forwards_site_month(monkeypatch):
    calls=[]
    own=dict(sku='SKU',site='UK',chengduInTransitQty=0,chengduSellableQty=1,
             overseasInTransitQty=2,overseasSellableQty=3,totalInventory=6,sales30d=4,sales7d=1,sales15d=2)
    def inventory(**params):
        calls.append(params)
        return dict(items=[own],total=1,calculationVersion='v')
    def prices(**params):
        assert params['site']=='英国' and params['stat_month']=='2026-10'
        return dict(items=[dict(site='UK',currency='GBP',ebayMinPrice=3,ebayMaxPrice=7,
                               amzMinPrice=5,amzMaxPrice=10)],total=1,months=['2026-10'],statMonth='2026-10')
    monkeypatch.setattr(service,'list_sales',inventory)
    monkeypatch.setattr(service,'list_price_ranges',prices)
    row=service.list_site_details(platform='ebay',sku='SKU',site='英国',stat_month='2026-10')['items'][0]
    assert calls[0]['platform']=='ebay' and calls[0]['site']=='英国'
    assert row['sales30d']==4 and row['totalInventory']==6 and row['chengduInTransitQty']==0
    assert row['ebayMinPrice']==3 and row['amzMaxPrice']==10 and row['currency']=='GBP'
    assert 'sales7d' not in row and 'sales15d' not in row


@pytest.mark.parametrize('platform', ['ebay'])
def test_both_platforms_share_site_sales_without_currency_matching_and_sort_all_rows(monkeypatch,platform):
    sources = {
        'amz': [dict(sku='SKU',site='UK',sales30d=0),dict(sku='SKU',site='DE',sales30d=12),
                dict(sku='SKU',site=None,sales30d=999)],
        'ebay': [dict(sku='SKU',site='UK',sales30d=3),dict(sku='SKU',site='FR',sales30d=7),
                 dict(sku='SKU',site=None,sales30d=888)]
    }
    calls=[]
    def inventory(**params):
        calls.append(params)
        rows=sources[params['platform']]
        return dict(items=rows,total=len(rows),calculationVersion='saved')
    quotes=[dict(site='UK',currency='GBP'),dict(site='UK',currency='USD')]
    monkeypatch.setattr(service,'list_sales',inventory)
    monkeypatch.setattr(service,'list_price_ranges',lambda **_:dict(items=quotes,total=2,months=[],statMonth=None))
    data=service.list_site_details(sku='SKU',platform=platform,sort_field='amzSales30d',sort_order='desc')
    assert calls[1]['calculation_version']=='saved'
    known=[r for r in data['items'] if r['site'] is not None]
    assert known[0]['site']=='DE' and known[0]['amzSales30d']==12
    uk=[r for r in data['items'] if r['site']=='UK']
    assert len(uk)==2 and all(r['amzSales30d']==0 and r['ebaySales30d']==3 for r in uk)
    france=next(r for r in data['items'] if r['site']=='FR')
    assert france['amzSales30d'] is None and france['ebaySales30d']==7
    unknown=next(r for r in data['items'] if r['site'] is None)
    peer_field='ebaySales30d' if platform=='amz' else 'amzSales30d'
    assert unknown[peer_field] is None
    second=service.list_site_details(sku='SKU',platform=platform,sort_field='amzSales30d',
                                     sort_order='desc',page_size=1,page=2)
    assert second['items']==data['items'][1:2] and second['total']==data['total']


def test_amz_store_prices_and_metrics_do_not_use_site_totals(monkeypatch):
    stores = [dict(sku='SKU',sid=1,storeName='店铺一',site='UK',currency='GBP',sales30d=5,fbaTotalInventory=12,amzMinPrice=10,amzMaxPrice=20),
              dict(sku='SKU',sid=2,storeName='店铺二',site='UK',currency='GBP',sales30d=6,fbaTotalInventory=8,amzMinPrice=90,amzMaxPrice=100)]
    monkeypatch.setattr(service,'list_store_inventory',lambda **kw: [r for r in stores if kw['sid'] is None or r['sid']==kw['sid']])
    monkeypatch.setattr(service,'list_sales',lambda **kw: dict(items=[dict(site='UK',sales30d=11 if kw['platform']=='amz' else 3)],total=1))
    quotes=[dict(site='UK',currency='GBP',amzMinPrice=10,amzMaxPrice=100,ebayMinPrice=5,ebayMaxPrice=40),
            dict(site='FR',currency='EUR',ebayMinPrice=70,ebayMaxPrice=80)]
    monkeypatch.setattr(service,'list_price_ranges',lambda **_:dict(items=quotes,total=2,months=[],statMonth=None))
    data=service.list_site_details(sku='SKU',sort_field='storeName',sort_order='asc')['items']
    actual={r['sid']:r for r in data if r['sid'] is not None}
    assert actual[1]['amzSales30d']==5 and actual[1]['amzMaxPrice']==20
    assert actual[2]['amzSales30d']==6 and actual[2]['amzMinPrice']==90
    assert all(r['ebaySales30d']==3 and r['ebayMaxPrice']==40 for r in actual.values())
    assert next(r for r in data if r['site']=='FR')['storeName'] is None
    filtered=service.list_site_details(sku='SKU',sid=1)['items']
    assert len(filtered)==1 and filtered[0]['sid']==1
