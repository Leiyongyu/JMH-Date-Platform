from datetime import datetime
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1 import amz_owner_sku as api
from backend.services import amz_owner_sku_service as service
from backend.repositories import amz_owner_sku_repository as repo
from backend.api import deps


RULES = {('EU', 'BRAND', 'ABC'): '品牌负责人', ('EU', 'OTH_CODE', '123'): 'OTH负责人',
         ('US1', 'STORE', '甲店'): '店铺负责人', ('US2', 'STORE', '邱存帅'): '旧负责人'}


def row(sid='1', sku='ABC-100-001', store='EU-甲店-DE'):
    return dict(sid=sid, local_sku=sku, seller_sku=sku, store_name=store, sync_time=datetime(2026, 9, 17, 12))


def counts(rows, rules=RULES):
    return {item['principal_name']: item['sku_count'] for item in service.summarize(rows, rules)['items']}


def test_dedup_uses_full_seller_sku_across_shops_not_local_sku_or_middle_code():
    rows = [row(), row(sku=' abc-100-001 '), row(sid='2'), row(sku='ABC-100-002')]
    rows.append({**row(), 'seller_sku': 'ABC-100-001-YXQ'})
    assert counts(rows) == {'品牌负责人': 3}


def test_same_seller_sku_different_local_skus_same_owner_counts_once():
    rows = [row(), {**row(sid='2', sku='ABC-OTHER'), 'seller_sku': 'ABC-100-001'}]
    assert counts(rows) == {'品牌负责人': 1}


def test_store_assignment_does_not_require_local_sku_but_eu_brand_does():
    rows = [{**row(sku=None, store='US1-甲店-US'), 'seller_sku': 'SELLER-1'},
            {**row(sku=None), 'seller_sku': 'SELLER-2'}]
    result = service.summarize(rows, RULES)
    assert {i['principal_name']: i['sku_count'] for i in result['items']} == {'店铺负责人': 1, '未分配': 1}
    assert result['missing_sku_rows'] == 0


def test_missing_seller_sku_does_not_fall_back_to_local_sku():
    result = service.summarize([{**row(), 'seller_sku': None}], RULES)
    assert result['total'] == 0 and result['missing_sku_rows'] == 1


@pytest.mark.parametrize('prefix', ['2PC', '4PC', '12PC', '999PC', '0PC', 'PC', '2pc'])
@pytest.mark.parametrize('field', ['local_sku', 'seller_sku'])
def test_pc_prefix_filtered_in_local_or_seller_sku(prefix, field):
    excluded = {**row(sid='2'), field: f' {prefix}-ABC-1 '}
    result = service.summarize([row(), excluded], RULES)
    assert result['total'] == 1 and result['excluded_pc_rows'] == 1
    assert result['missing_sku_rows'] == 0 and result['unassigned_count'] == 0


def test_pc_in_middle_or_suffix_is_not_excluded():
    result = service.summarize([row(sku='ABC-2PC-1'), row(sku='ABC-1-PC')], RULES)
    assert result['total'] == 2 and result['excluded_pc_rows'] == 0


def test_performance_branches_and_same_sku_different_owners():
    rows = [row(), row(sid='2', store='EU-甲店-UK'), row(sid='3', sku='OTH-123-001'),
            row(sid='4', store='US3-甲店-US'), row(sid='5', store='US1-重庆茁凯-US')]
    assert counts(rows) == {'品牌负责人': 1, '吴清栩': 1, 'OTH负责人': 1, '店铺负责人': 1, '旧负责人': 1}
    rules = {**RULES, ('US1', 'STORE', '重庆茁凯'): '新负责人'}
    assert counts([rows[-1]], rules) == {'新负责人': 1}


def test_missing_shop_unmatched_sku_and_missing_identity():
    result = service.summarize([row(store=None), row(sku='XYZ-123'), row(sku=None), row(sid=None)], RULES)
    assert result['unassigned_count'] == 2
    assert result['missing_sku_rows'] == 1
    assert result['missing_shop_count'] == 1
    assert result['total'] == 3


def test_conflicting_store_rules_fail_explicitly():
    with pytest.raises(ValueError, match='配置冲突'):
        service.summarize([row()], {**RULES, ('US2', 'STORE', '甲店'): '冲突负责人'})


def source(monkeypatch, rows=None, rules=None, sync=None):
    value = {'rows': [row()] if rows is None else rows, 'rules': RULES if rules is None else rules,
             'sync': {'status': 'SUCCESS'} if sync is None else sync}
    mock = MagicMock(return_value=value)
    monkeypatch.setattr(repo, 'load_source', mock)
    return mock


def test_current_china_month_and_sorted_integer_counts(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            assert str(tz) == 'Asia/Shanghai'
            return datetime(2026, 9, 18, tzinfo=tz)
    monkeypatch.setattr(service, 'datetime', Clock)
    mock = source(monkeypatch, rows=[row(), row(sid='2'), row(sid='3', sku='XYZ-1')])
    result = service.get_owner_sku_counts()
    mock.assert_called_once_with('2026-09')
    assert result['total'] == 2
    assert [item['sku_count'] for item in result['items']] == [1, 1, 0, 0, 0]
    assert result['dedup_key'] == ['principal_name', 'seller_sku']
    assert result['listing_status'] == 1 and result['is_delete'] == 0
    assert result['source_table'] == 'ods_lingxing_amz_listing_latest'
    assert result['source_updated_at'] == '2026-09-17 12:00:00'
    assert result['state'] == 'READY'


@pytest.mark.parametrize('status', ['RUNNING', 'FAILED', 'PARTIAL', 'CANCELLED'])
def test_incomplete_source_never_shows_partial_counts(monkeypatch, status):
    source(monkeypatch, sync={'status': status})
    result = service.get_owner_sku_counts()
    assert result['state'] == 'SOURCE_NOT_READY'
    assert result['items'] == [] and result['total'] is None


def test_missing_rules_not_silently_unassigned(monkeypatch):
    source(monkeypatch, rules={})
    result = service.get_owner_sku_counts()
    assert result['state'] == 'MISSING_RULES' and result['total'] is None


def test_empty_source_is_distinct_from_failed_source(monkeypatch):
    source(monkeypatch, rows=[])
    result = service.get_owner_sku_counts()
    assert result['state'] == 'EMPTY' and result['total'] == 0
    assert result['owner_count'] == 4
    assert len(result['items']) == 4
    assert all(item['sku_count'] == 0 for item in result['items'])


def test_current_roster_includes_zero_owners_once_without_placeholder_names(monkeypatch):
    rules = {**RULES, ('US1', 'STORE', '新店'): '张生敏',
             ('US1', 'STORE', '另一店'): '张生敏', ('US1', 'STORE', '未配置'): '未分配',
             ('US1', 'STORE', '停用店'): '注销'}
    source(monkeypatch, rules=rules)
    result = service.get_owner_sku_counts()
    assert [i for i in result['items'] if i['principal_name'] == '张生敏'] == [
        {'principal_name': '张生敏', 'sku_count': 0, 'unassigned': False}]
    assert result['owner_count'] == 5 and result['total'] == 1
    assert not any(i['unassigned'] for i in result['items'])
    assert not any(i['principal_name'] == '注销' for i in result['items'])


def test_only_pc_listings_still_show_configured_people_as_zero(monkeypatch):
    source(monkeypatch, rows=[row(sku='2PC-ABC-1')])
    result = service.get_owner_sku_counts()
    assert result['total'] == 0 and result['excluded_pc_rows'] == 1
    assert len(result['items']) == 4 and all(i['sku_count'] == 0 for i in result['items'])


def test_no_publication_blocks_old_source_fallback(monkeypatch):
    monkeypatch.setattr(repo, 'load_source', lambda month: {'rows': [row()], 'rules': RULES, 'sync': None})
    result = service.get_owner_sku_counts()
    assert result['state'] == 'SOURCE_NOT_READY' and result['total'] is None


def test_repository_filters_active_rows_and_reads_in_one_read_only_snapshot(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = {'status': 'SUCCESS'}
    cursor.fetchall.side_effect = [[{'sid': '001', 'store_name': row()['store_name']}], [row()]]
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(repo, 'db_connection', lambda: context)
    rules = MagicMock(return_value=RULES)
    monkeypatch.setattr(repo, 'get_owner_rules', rules)
    result = repo.load_source('2026-09')
    sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
    assert 'READ ONLY' in sql and 'CONSISTENT SNAPSHOT' in sql
    assert 'WHERE pl.status=1 AND pl.is_delete=0' in sql
    assert 'pl.seller_sku' in sql  # PC exclusion also checks the listing SKU.
    assert 'ods_lingxing_amz_listing_state' in sql
    assert 'ods_lingxing_amz_listing_latest' in sql
    assert 'data_sync_log' not in sql and '`.amz_product_listing' not in sql
    assert 'principal_name' not in sql  # Never use native listing owner.
    assert 'replenishment' not in sql
    rules.assert_called_once_with(connection, 'amazon', '2026-09')
    connection.rollback.assert_called_once()
    assert result['rows'] == [row()]


def test_endpoint_requires_token_and_returns_data(monkeypatch):
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-internal-token'))
    mock = MagicMock(return_value={'state': 'READY', 'total': 3})
    monkeypatch.setattr(api, 'get_owner_sku_counts', mock)
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        url = '/api/v1/finance/amz-owner-sku/summary'
        assert client.get(url).status_code == 401
        mock.assert_not_called()
        response = client.get(url, headers={'X-Internal-Token': 'test-internal-token'})
        assert response.status_code == 200
        assert response.json()['data']['total'] == 3
        assert client.post(url).status_code == 405


def test_ambiguous_shop_name_fails_and_rolls_back(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = {'status': 'SUCCESS'}
    cursor.fetchall.return_value = [{'sid': 1, 'store_name': 'US1-甲-US'},
                                   {'sid': '001', 'store_name': 'US2-乙-US'}]
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(repo, 'db_connection', lambda: context)
    monkeypatch.setattr(repo, 'get_owner_rules', lambda *args: RULES)
    with pytest.raises(ValueError, match='同sid不同店铺名称'):
        repo.load_source('2026-09')
    connection.rollback.assert_called_once()


def test_endpoint_sanitizes_unexpected_failure(monkeypatch):
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token=''))
    monkeypatch.setattr(api, 'get_owner_sku_counts', MagicMock(side_effect=RuntimeError('secret-db-detail')))
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        response = client.get('/api/v1/finance/amz-owner-sku/summary')
    assert response.status_code == 500
    assert 'secret-db-detail' not in response.text
