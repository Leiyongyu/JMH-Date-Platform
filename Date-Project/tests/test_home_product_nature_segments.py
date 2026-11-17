from datetime import datetime
from unittest.mock import MagicMock
from backend.services import home_product_nature_service as s
from backend.repositories import home_product_nature_repository as r
from test_home_product_nature import NOW, row, source, EBAY
from test_home_product_nature_repository import connection


def test_ebay_site_keeps_new_and_old_separate_at_60_day_boundary():
    rows=[{**row('ABC-1',age=60),'site':'英国'},
          {**row('ABC-1',age=60),'site':'英国','store_id':'2'},
          {**row('ABC-1',age=61),'site':'德国'}]
    report,facts=s.build('ebay',source(rows,EBAY),NOW)
    segments={x['segment_key']:x for x in report['segments']}
    assert report['segment_grain']=='site_msku'
    assert segments['英国']['sku_count']==1 and segments['英国']['counts']['NEW']==1
    assert segments['德国']['sku_count']==1 and segments['德国']['counts']['OLD']==1
    assert all(x['counts']['CONFLICT']==0 for x in segments.values())
    assert all(f['threshold_days']==60 for f in facts)


def test_amz_region_config_not_country_or_owner_group():
    rows=[{**row('ABC-1',age=70),'site':'UK','replenishment_regions':['EU']},
          {**row('ABC-2',store='US1-甲店-CA',age=70),'site':'CA','replenishment_regions':['US']},
          {**row('ABC-3',age=70),'site':'DE','replenishment_regions':['US']},
          {**row('ABC-4',age=70),'replenishment_regions':['US','EU']}]
    report,facts=s.build('amz',source(rows),NOW)
    segments={x['segment_key']:x for x in report['segments']}
    assert segments['EU']['counts']['NEW']==1
    assert segments['US']['counts']['OLD']==2
    assert segments['UNKNOWN_REGION']['counts']['UNKNOWN']==1
    assert facts[2]['group_code']=='EU' and facts[2]['segment_key']=='US'


def test_amz_same_region_uses_earliest_date():
    rows=[row(age=10),{**row(age=110),'store_id':'2','site':'FR'}]
    report,_=s.build('amz',source(rows),NOW)
    assert next(x for x in report['segments'] if x['segment_key']=='EU')['counts']==dict(NEW=0,OLD=1,UNKNOWN=0,CONFLICT=0)


def test_ebay_missing_owner_still_counted_in_site():
    report,_=s.build('ebay',source([{**row('JMH-1',age=70),'site':'德国'}],EBAY),NOW)
    assert report['segments'][0]['sku_count']==1 and report['segments'][0]['counts']['OLD']==1
    assert any(x['principal_name']=='未分配' for x in report['owners'])


def test_ebay_min_date_grouped_by_site_includes_inactive_and_normalizes_full_sku():
    conn,cur=connection();cur.fetchone.return_value={'status':'SUCCESS'}
    cur.fetchall.side_effect=[
        [dict(group_code='',rule_type='EBAY_BRAND',match_key='ABC',principal_name='甲')],
        [dict(msku=' abc-1 ',site_name='英国',first_date=datetime(2026,9,1)),
         dict(msku='ABC-1',site_name='英国',first_date=datetime(2026,1,1)),
         dict(msku='ABC-1',site_name='德国',first_date=datetime(2026,8,1))],
        [dict(msku='abc-1',site='英国'),dict(msku='ABC-1',site='德国')]]
    data=r.load_source(conn,'ebay','2026-09')
    assert data['rows'][0]['first_listing_date']==datetime(2026,1,1)
    assert data['rows'][1]['first_listing_date']==datetime(2026,8,1)
    query=next(c.args[0] for c in cur.execute.call_args_list if 'MIN(listing_start_time)' in c.args[0])
    assert 'listing_status' not in query and 'GROUP BY site_name,msku' in query


def test_amz_sql_preserves_population_and_uses_enabled_region_config():
    sql=r.amz_shops_sql('jmh_data_platform')
    assert 'LEFT JOIN' in sql and 'FIND_IN_SET(wh.name,fc.marketplaces)>0' in sql
    assert 'fc.enabled=1' in sql and "SUBSTRING_INDEX(TRIM(COALESCE(sl.store_name,'')),'-',1)" in sql
    assert 'GROUP_CONCAT(DISTINCT fc.region_group' in sql
