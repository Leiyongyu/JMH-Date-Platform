import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import deps
from backend.api.v1 import internal_scheduler as api
from backend.repositories import amz_listing_raw_repository as repo
from backend.repositories import amz_owner_sku_repository as owner_repo
from backend.services import amz_listing_raw_sync_service as service
from backend.services import scheduler_service as scheduler


def row(sku='SKU-1', **extra):
    return {'sid': 1, 'seller_sku': sku, 'status': 1, 'is_delete': 0, 'listing_id': '', **extra}


def page(rows, total=None):
    return {'code': 0, 'total': len(rows) if total is None else total, 'data': rows,
            'request_id': 'trace', 'response_time': '2026-09-18', 'future_metadata': [1, 2]}


def setup_sync(monkeypatch, responses, sids=None):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = responses
    monkeypatch.setattr(service, 'LingXingClient', lambda **kwargs: client)
    monkeypatch.setattr(service.time, 'sleep', lambda delay: None)
    monkeypatch.setattr(repo, 'shop_sids', lambda: sids or ['1'])
    captured = []
    def replace(records, **kw):
        captured.extend(records)
        assert len(captured) == kw['expected_rows']
        return {'ods_rows': len(captured), 'inserted_rows': len(captured), 'deleted_rows': 9}
    mock = MagicMock(side_effect=replace)
    monkeypatch.setattr(repo, 'replace_snapshot', mock)
    return client, captured, mock


def test_all_fields_case_variants_deleted_unpaired_and_empty_listing_id_survive(monkeypatch):
    rows = [row('ABC-fba', future={'nested': [1, None]}, principal_info=[{'principal_uid': 7}]),
            row('ABC-FBA', status=0, is_delete=1)]
    client, captured, replace = setup_sync(monkeypatch, [page(rows)])
    result = service.sync_amz_listing_raw()
    assert result['extract_rows'] == result['ods_rows'] == 2
    assert [r['row'] for r in captured] == rows
    assert captured[0]['response_meta']['future_metadata'] == [1, 2]
    assert [r['row_no'] for r in captured] == [1, 2]
    client.post_signed_query_auth.assert_called_once_with(service.API, {'sid': '1', 'offset': 0, 'length': 1000})
    values = dict(zip(repo.FIELDS + repo.METADATA, repo.record_values(captured[0], 'batch', datetime.now())))
    assert json.loads(values['raw_json']) == rows[0]
    assert json.loads(values['principal_info']) == rows[0]['principal_info']
    assert values['listing_id'] == '' and values['local_sku'] is None
    replace.assert_called_once()


def test_full_pagination_and_multiple_shop_batches(monkeypatch):
    monkeypatch.setattr(service, 'PAGE_SIZE', 2)
    monkeypatch.setattr(service, 'SID_BATCH_SIZE', 1)
    client, captured, _ = setup_sync(monkeypatch,
        [page([row('A'), row('B')], 3), page([row('C')], 3), page([row('D', sid=2)])], ['1', '2'])
    service.sync_amz_listing_raw()
    assert [call.args[1] for call in client.post_signed_query_auth.call_args_list] == [
        {'sid': '1', 'offset': 0, 'length': 2}, {'sid': '1', 'offset': 2, 'length': 2},
        {'sid': '2', 'offset': 0, 'length': 2}]
    assert len(captured) == 4


@pytest.mark.parametrize('response', [
    {'code': 102, 'data': [], 'total': 0}, {'code': 0, 'data': {}, 'total': 1},
    page([row()], 2), page([row()], 'bad'), page([row(status=None)]),
    page([row(is_delete=3)]), page([row(sid=2)]), page([row(seller_sku='')]), page([]),
])
def test_bad_response_never_clears_previous_snapshot(monkeypatch, response):
    _, _, replace = setup_sync(monkeypatch, [response])
    with pytest.raises(service.AmzListingRawSyncError):
        service.sync_amz_listing_raw()
    replace.assert_not_called()


@pytest.mark.parametrize('second', [page([row('B')], 3), page([row('A')], 2)])
def test_changed_total_or_repeated_page_fails_before_replace(monkeypatch, second):
    monkeypatch.setattr(service, 'PAGE_SIZE', 1)
    _, _, replace = setup_sync(monkeypatch, [page([row('A')], 2), second])
    with pytest.raises(service.AmzListingRawSyncError):
        service.sync_amz_listing_raw()
    replace.assert_not_called()


def test_temporary_failure_retries_same_page(monkeypatch):
    client, captured, _ = setup_sync(monkeypatch, [TimeoutError('secret'), page([row()])])
    service.sync_amz_listing_raw()
    assert client.post_signed_query_auth.call_args_list[0] == client.post_signed_query_auth.call_args_list[1]
    assert len(captured) == 1


def test_retry_budget_and_sanitization(monkeypatch):
    client, _, replace = setup_sync(monkeypatch, [TimeoutError('token=do-not-print')] * 4)
    with pytest.raises(service.AmzListingRawSyncError) as error:
        service.sync_amz_listing_raw()
    assert client.post_signed_query_auth.call_count == 4
    assert 'do-not-print' not in str(error.value)
    replace.assert_not_called()


def context_connection(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(repo, 'db_connection', lambda: context)
    return connection, cursor


def record():
    return {'row': row(), 'row_no': 1, 'request_sids': '1', 'offset': 0,
            'row_in_page': 1, 'total': 1, 'response_meta': {'code': 0}}


def test_transaction_publishes_data_and_marker_together(monkeypatch):
    connection, cursor = context_connection(monkeypatch)
    cursor.fetchone.return_value = {'n': 1}
    result = repo.replace_snapshot(iter([record()]), expected_rows=1, batch_id='b', pulled_at=datetime.now(), shop_count=1)
    assert result['ods_rows'] == 1
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    statements = '\n'.join(c.args[0] for c in cursor.execute.call_args_list)
    assert repo.TABLE in statements and repo.STATE_TABLE in statements
    assert 'TRUNCATE' not in statements and 'amz_product_listing' not in statements


def test_insert_failure_rolls_back_and_never_publishes(monkeypatch):
    connection, cursor = context_connection(monkeypatch)
    cursor.executemany.side_effect = RuntimeError('write failed')
    with pytest.raises(RuntimeError):
        repo.replace_snapshot(iter([record()]), expected_rows=1, batch_id='b', pulled_at=datetime.now(), shop_count=1)
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    assert not any(repo.STATE_TABLE in c.args[0] for c in cursor.execute.call_args_list)


def test_count_mismatch_rolls_back(monkeypatch):
    connection, cursor = context_connection(monkeypatch)
    cursor.fetchone.return_value = {'n': 0}
    with pytest.raises(ValueError):
        repo.replace_snapshot(iter([record()]), expected_rows=1, batch_id='b', pulled_at=datetime.now(), shop_count=1)
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_schema_exposes_all_document_fields_and_has_no_business_unique_key():
    schema = (Path(__file__).parents[1] / 'migrations/20260918_amz_listing_raw.sql').read_text(encoding='utf-8')
    assert len(repo.FIELDS) == 58
    for field in repo.FIELDS:
        assert f'`{field}` ' in schema
    assert 'utf8mb4_bin' in schema and 'uk_source_row' in schema
    assert 'uk_sid_sku' not in schema and 'UNIQUE KEY uk_listing' not in schema


def test_scheduler_dispatch_holds_global_lock(monkeypatch):
    entered = []
    @contextmanager
    def lock(name):
        entered.append(name)
        yield True
    connection = MagicMock()
    @contextmanager
    def database():
        yield connection
    monkeypatch.setattr(scheduler.repo, 'named_lock', lock)
    monkeypatch.setattr(scheduler.repo, 'performance_connection', database)
    monkeypatch.setattr(scheduler.repo, 'insert_scheduler_run', MagicMock())
    sync = MagicMock(return_value={'extract_rows': 2, 'ods_rows': 2, 'sync_batch_id': 'b'})
    monkeypatch.setattr(scheduler, 'sync_amz_listing_raw', sync)
    result = scheduler.run_scheduler_task(service.TASK_CODE)
    assert result['status'] == 'completed'
    assert entered == ['lingxing:amz-listing-raw:replace']
    sync.assert_called_once()
    with pytest.raises(ValueError):
        scheduler.run_scheduler_task(service.TASK_CODE, stat_month='2026-01')


def test_endpoint_protected_and_registered(monkeypatch):
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-secret'))
    run = MagicMock(return_value={'status': 'completed'})
    monkeypatch.setattr(api, 'run_scheduler_task', run)
    app = FastAPI()
    @app.middleware('http')
    async def trace(request, call_next):
        request.state.request_id = 'test'
        return await call_next(request)
    app.include_router(api.router)
    with TestClient(app) as client:
        url = f'/api/v1/internal/scheduler/tasks/{service.TASK_CODE}/run'
        assert client.post(url, json={}).status_code == 401
        run.assert_not_called()
        assert client.post(url, json={}, headers={'X-Internal-Token': 'test-secret'}).status_code == 201
    assert service.TASK_CODE in scheduler.TASK_CODES


def test_missing_publication_never_uses_old_table(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = None
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(owner_repo, 'db_connection', lambda: context)
    result = owner_repo.load_source('2026-09')
    assert result['sync']['status'] == 'NOT_INITIALIZED'
    assert not any('amz_product_listing' in c.args[0] for c in cursor.execute.call_args_list)
