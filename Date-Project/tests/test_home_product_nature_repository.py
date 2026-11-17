from unittest.mock import MagicMock
import pytest
from backend.repositories import home_product_nature_repository as r


def connection():
    conn,cur=MagicMock(),MagicMock()
    conn.cursor.return_value.__enter__.return_value=cur
    return conn,cur


def test_amz_reads_actual_population_and_raw_date_not_replenishment_population():
    conn,cur=connection()
    cur.fetchone.return_value={'sync_batch_id':'batch'}
    cur.fetchall.side_effect=[
        [dict(group_code='EU',rule_type='BRAND',match_key='ABC',principal_name='甲')],
        [dict(sid='1',store_name='EU-甲店-DE',country_code='DE')],
        [dict(sid=1,seller_sku='ABC-1',local_sku='ABC-1',marketplace='DE',open_date='2026-09-01',open_date_display='2025-01-01')]]
    result=r.load_source(conn,'amz','2026-09')
    assert result['rows'][0]['first_listing_date']=='2026-09-01'
    assert result['rows'][0]['store_name']=='EU-甲店-DE'
    sql='\n'.join(call.args[0] for call in cur.execute.call_args_list)
    assert 'WHERE status=1 AND is_delete=0' in sql
    assert 'ods_lingxing_amz_listing_latest' in sql
    assert 'amz_replenishment_us_snapshot' not in sql
    assert 'amz_product_listing' not in sql and 'open_date_display' not in sql


def test_ebay_first_date_all_listings_but_population_active_only():
    conn,cur=connection()
    cur.fetchone.return_value={'status':'SUCCESS'}
    cur.fetchall.side_effect=[
        [dict(group_code='',rule_type='EBAY_BRAND',match_key='ABC',principal_name='甲')],
        [dict(msku='ABC-1',site_name='英国',first_date='2026-01-01')],
        [dict(msku='ABC-1',site='英国')]]
    result=r.load_source(conn,'ebay','2026-09')
    assert result['rows'][0]['first_listing_date']=='2026-01-01'
    sqls=[call.args[0] for call in cur.execute.call_args_list]
    minimum=next(q for q in sqls if 'MIN(listing_start_time)' in q)
    assert 'listing_status' not in minimum
    assert any('WHERE listing_status=1' in q for q in sqls)


def test_duplicate_conflicting_rule_rows_not_silently_overwritten():
    conn,cur=connection()
    cur.fetchall.return_value=[dict(group_code='EU',rule_type='BRAND',match_key='ABC',principal_name=p) for p in ('甲','乙')]
    with pytest.raises(ValueError,match='冲突'):r.load_source(conn,'amz','2026-09')


def test_existing_frozen_publish_rejected_before_delete(monkeypatch):
    conn,cur=connection();monkeypatch.setattr(r,'read_report',lambda *args:dict(batch_id='old'))
    with pytest.raises(ValueError,match='不允许覆盖'):
        r.publish(conn,dict(platform='amz',stat_month='2026-09'),[],'FROZEN')
    cur.execute.assert_not_called()


def test_new_report_publish_touches_only_report_tables():
    conn,cur=connection()
    report=dict(platform='amz',stat_month='2026-09',groups=[],owners=[],counts={k:0 for k in ('NEW','OLD','UNKNOWN','CONFLICT')},
                rule_version='v1',sku_count=0,batch_id='batch',source_fingerprint='fingerprint',captured_at='2026-09-23 00:00:00')
    r.publish(conn,report,[],'LIVE')
    queries=[call.args[0] for call in cur.execute.call_args_list+cur.executemany.call_args_list]
    assert all(r.SUMMARY in q or r.DETAIL in q for q in queries)
    assert not any('TRUNCATE' in q or 'ALTER' in q for q in queries)
    assert all('period_kind' in q for q in queries)


def test_live_freshness_includes_rules_and_source_publication_not_month_only():
    conn,cur=connection();cur.fetchone.return_value={'sync_batch_id':'first'};cur.fetchall.return_value=[]
    first=r.source_token(conn,'amz','2026-09','2026-09-23','v1')
    cur.fetchone.return_value={'sync_batch_id':'second'}
    assert r.source_token(conn,'amz','2026-09','2026-09-23','v1')!=first
    sql='\n'.join(call.args[0] for call in cur.execute.call_args_list)
    assert 'amz_product_listing' not in sql
    cur.fetchone.return_value={'sync_batch_id':'first'};cur.fetchall.return_value=[{'principal_name':'new-owner'}]
    assert r.source_token(conn,'amz','2026-09','2026-09-23','v1')!=first


def test_amz_monthly_replace_only_target_month_and_platform():
    conn,cur=connection()
    report=dict(platform='amz',stat_month='2026-09',groups=[],owners=[],counts={k:0 for k in ('NEW','OLD','UNKNOWN','CONFLICT')},
                rule_version='v2',sku_count=0,batch_id='new',source_fingerprint='fingerprint',captured_at='2026-09-23 00:00:00')
    r.publish(conn,report,[],'MONTHLY')
    assert cur.execute.call_count==2
    for call in cur.execute.call_args_list:
        assert call.args[0].endswith('WHERE stat_month=%s AND platform=%s')
        assert call.args[1]==('2026-09','amz')
    assert cur.executemany.call_args.args[1][0][2]=='MONTHLY'


def test_monthly_overwrite_forbidden_for_ebay():
    conn,cur=connection()
    with pytest.raises(ValueError,match='仅适用于AMZ'):
        r.publish(conn,dict(platform='ebay',stat_month='2026-09'),[],'MONTHLY')
    cur.execute.assert_not_called()


def test_legacy_amz_history_fallback_never_rebuilds(monkeypatch):
    read=MagicMock(side_effect=[None,{'rule_version':'performance-nature-v1'}])
    monkeypatch.setattr(r,'read_report',read)
    assert r.read_month_report(None,'amz','2026-08')['rule_version']=='performance-nature-v1'
    assert [call.args[3] for call in read.call_args_list]==['MONTHLY','FROZEN']
