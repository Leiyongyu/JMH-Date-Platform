from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import deps
from backend.api.v1 import ebay_owner_sku as api
from backend.repositories import ebay_owner_sku_repository as repo
from backend.services import ebay_owner_sku_service as service

RULES = {('', 'EBAY_BRAND', 'BMW'): '房伟', ('', 'EBAY_BRAND', 'DAS'): '方黎力',
         ('', 'EBAY_BRAND', 'FLL'): '不能覆盖固定规则'}


def row(msku='BMW-100-001', store=1, **kwargs):
    return {'msku': msku, 'store_id': store, 'local_sku': '', 'sync_time': datetime(2026, 9, 18), **kwargs}


def test_msku_brand_not_local_sku_or_truncated_sku_and_cross_shop_dedup():
    result = service.summarize([row(), row(' bmw-100-001 '), row(store=2),
                                row('BMW-100-002', local_sku='DAS-100-002')], RULES)
    assert result['items'] == [{'principal_name': '房伟', 'sku_count': 2, 'unassigned': False}]


def test_two_cl_mskus_across_six_shops_count_as_two():
    rows = [row(sku, store=store) for store in range(1, 7)
            for sku in ('CL-26327733-SY', 'CL-48255022-SY')]
    assert service.summarize(rows, RULES)['items'] == [
        {'principal_name': '未分配', 'sku_count': 2, 'unassigned': True}]


def test_cl_uses_current_rule_and_pc_prefix_is_excluded():
    rules = {**RULES, ('', 'EBAY_BRAND', 'CL'): '当月负责人'}
    result = service.summarize([row('CL-1'), row('2PC-CL-2'), row(' cl-1 ', store=2)], rules)
    assert result['items'] == [
        {'principal_name': '当月负责人', 'sku_count': 1, 'unassigned': False}]
    assert result['excluded_pc_rows'] == 1
    assert service.summarize([row('2PC-CL-2')], RULES)['unassigned_count'] == 0


def test_shared_performance_assignment_keeps_existing_cl_override():
    assert service._ebay_assignment('CL-1', {'CL': '当月负责人'})[0] == '陈丽'


def test_fixed_rules_pack_prefix_and_unassigned():
    result = service.summarize([row('2PC-BMW-100-001'), row('FLL-1'), row('LEJ-2'),
                               row('CL-3'), row('XYZ-4')], RULES)
    counts = {item['principal_name']: item['sku_count'] for item in result['items']}
    assert counts == {'方黎力': 2, '未分配': 2}
    assert result['unassigned_count'] == 2


@pytest.mark.parametrize('prefix', ['2PC', '4PC', '12PC', '999PC', '0PC', 'PC', '2pc'])
def test_pc_prefix_filtered_before_owner_matching(prefix):
    result = service.summarize([row(f' {prefix}-BMW-1 '), row('BMW-1')], RULES)
    assert result['total'] == 1 and result['excluded_pc_rows'] == 1
    assert result['missing_sku_rows'] == 0 and result['unassigned_count'] == 0


def test_pc_in_middle_or_suffix_is_not_excluded():
    result = service.summarize([row('BMW-2PC-1'), row('BMW-1-PC'), row('PCX-1')], RULES)
    assert result['total'] == 3 and result['excluded_pc_rows'] == 0


def test_empty_identity_skipped_and_different_suffix_preserved():
    result = service.summarize([row(''), row(store=0), row(store=None), row(), row('BMW-100-001-YXQ')], RULES)
    assert result['total'] == 2 and result['missing_sku_rows'] == 1


def test_missing_shop_does_not_discard_valid_msku():
    result = service.summarize([row('BMW-1', store=None), row('BMW-2', store=0)], RULES)
    assert result['total'] == 2 and result['missing_sku_rows'] == 0


def test_ambiguous_brand_rules_rejected():
    with pytest.raises(ValueError, match='配置冲突'):
        service.summarize([row()], {**RULES, ('EBAY', 'EBAY_BRAND', 'BMW'): '另一个人'})


@pytest.mark.parametrize('status', ['RUNNING', 'FAILED', 'PARTIAL', 'CANCELLED'])
def test_incomplete_source_does_not_show_partial_count(monkeypatch, status):
    monkeypatch.setattr(repo, 'load_source', lambda _: {'rows': [row()], 'rules': RULES, 'sync': {'status': status}})
    result = service.get_owner_sku_counts()
    assert result['state'] == 'SOURCE_NOT_READY' and result['total'] is None


def test_empty_rules_and_empty_rows_are_distinct(monkeypatch):
    source = {'rows': [], 'rules': {}, 'sync': {'status': 'SUCCESS'}}
    monkeypatch.setattr(repo, 'load_source', lambda _: source)
    assert service.get_owner_sku_counts()['state'] == 'MISSING_RULES'
    source['rules'] = RULES
    result = service.get_owner_sku_counts()
    assert result['state'] == 'EMPTY' and result['total'] == 0
    assert result['owner_count'] == 3 and len(result['items']) == 3
    assert all(i['sku_count'] == 0 for i in result['items'])


def test_current_roster_keeps_zero_owners_without_unrelated_rules(monkeypatch):
    rules = {**RULES, ('', 'EBAY_BRAND', 'CL'): '任雅婷',
             ('', 'EBAY_BRAND', 'FRD'): '任雅婷', ('', 'EBAY_BRAND', 'EMPTY'): '未分配',
             ('', 'STORE', 'NOT_A_BRAND'): '无关人员'}
    monkeypatch.setattr(repo, 'load_source', lambda _: {
        'rows': [row()], 'rules': rules, 'sync': {'status': 'SUCCESS'}})
    result = service.get_owner_sku_counts()
    assert [i for i in result['items'] if i['principal_name'] == '任雅婷'] == [
        {'principal_name': '任雅婷', 'sku_count': 0, 'unassigned': False}]
    assert result['owner_count'] == 4 and result['total'] == 1
    assert not any(i['principal_name'] in {'无关人员', '未分配'} for i in result['items'])


def test_current_month_ready_metadata_and_missing_log_warning(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            assert str(tz) == 'Asia/Shanghai'
            return datetime(2026, 9, 18, tzinfo=tz)
    monkeypatch.setattr(service, 'datetime', Clock)
    mock = MagicMock(return_value={'rows': [row()], 'rules': RULES, 'sync': None})
    monkeypatch.setattr(repo, 'load_source', mock)
    result = service.get_owner_sku_counts()
    mock.assert_called_once_with('2026-09')
    assert result['total'] == 1 and result['warnings']
    assert result['dedup_key'] == ['principal_name', 'msku']


def test_repository_active_filter_and_transaction(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = {'status': 'SUCCESS'}
    cursor.fetchall.return_value = [row()]
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(repo, 'db_connection', lambda: context)
    rules = MagicMock(return_value=RULES)
    monkeypatch.setattr(repo, 'get_owner_rules', rules)
    assert repo.load_source('2026-09')['rows'] == [row()]
    sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
    assert 'WHERE listing_status=1' in sql
    assert 'READ ONLY' in sql and 'CONSISTENT SNAPSHOT' in sql
    assert 'ebay_product_listing' in sql and 'ebay_product_dedup' not in sql
    assert "sync_type='ebay_listing'" in sql
    rules.assert_called_once_with(connection, 'ebay', '2026-09')
    connection.rollback.assert_called_once()


def test_api_token_guard_and_error_redaction(monkeypatch):
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-token'))
    mock = MagicMock(return_value={'total': 8})
    monkeypatch.setattr(api, 'get_owner_sku_counts', mock)
    app = FastAPI(); app.include_router(api.router)
    with TestClient(app) as client:
        url = '/api/v1/finance/ebay-owner-sku/summary'
        assert client.get(url).status_code == 401
        mock.assert_not_called()
        headers = {'X-Internal-Token': 'test-token'}
        assert client.get(url, headers=headers).json()['data']['total'] == 8
        mock.side_effect = RuntimeError('private-database-detail')
        response = client.get(url, headers=headers)
        assert response.status_code == 500
        assert 'private-database-detail' not in response.text
