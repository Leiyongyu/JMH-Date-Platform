import io
import json
import logging
import socket
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest

from backend.integrations.lingxing import client as transport
from backend.services import weekly_inventory_api as api
from backend.services import weekly_inventory_sync_service as sync
from backend.services import weekly_inventory_export_service as export


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleep = MagicMock()
    monkeypatch.setattr(api.time, "sleep", sleep)
    monkeypatch.setattr(api.random, "uniform", lambda a, b: 0)
    return sleep


def call(client, **kwargs):
    return api.request_response(client, "inventoryBinDetails", {"offset": 500, "length": 500},
                                batch="batch-test", page=2, **kwargs)


def ok():
    return dict(code=0, message="success", data=[{}], total=1)


def wrapped(exc):
    outer = RuntimeError("RAW access_token=do-not-log")
    outer.__cause__ = exc
    return outer


def test_business_throttle_retries_exact_same_page(no_sleep, caplog):
    caplog.set_level(logging.INFO)
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [
        dict(code=0, total=3, data=[{}, {}]),
        dict(code=3001008, message="too frequently", data=None, request_id="upstream-id"),
        dict(code=0, total=3, data=[{}]),
    ]
    assert len(sync.fetch_pages(client, "inventoryBinDetails", 2, batch="b")) == 3
    calls = client.post_signed_query_auth.call_args_list
    assert calls[1].args == calls[2].args
    assert calls[1].args[1] == dict(offset=2, length=2)
    no_sleep.assert_called_once_with(2)
    assert "page=2 offset=2 length=2" in caplog.text
    assert "code=3001008" in caplog.text and "upstream-id" in caplog.text
    assert "attempt=2" in caplog.text


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_only_explicit_http_failures_retried(status, no_sleep):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [wrapped(transport.LingXingHttpError(status, '{}', '5')), ok()]
    assert call(client)["code"] == 0
    assert client.post_signed_query_auth.call_count == 2
    no_sleep.assert_called_once_with(5)


@pytest.mark.parametrize("exc", [TimeoutError(), ConnectionResetError(),
                                    wrapped(URLError(socket.gaierror(socket.EAI_AGAIN, 'temporary')))])
def test_temporary_connection_failures(exc, no_sleep):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [exc, ok()]
    assert call(client)["code"] == 0
    no_sleep.assert_called_once()


@pytest.mark.parametrize("failure", [
    dict(code=403, message="no permission", data=[]),
    dict(code=9999, message="too frequently (unknown code)", data=[]),
    dict(code=0, data={}), dict(code=0, data=[None]), [],
    transport.LingXingHttpError(401, '{}'), transport.LingXingHttpError(403, '{}'),
    transport.LingXingHttpError(400, '{}'), transport.LingXingHttpError(501, '{}'),
    wrapped(json.JSONDecodeError('invalid', '', 0)),
    URLError(socket.gaierror(socket.EAI_NONAME, 'invalid hostname')),
    ValueError('bad configuration access_token=SECRET'),
])
def test_permanent_errors_and_invalid_structure_never_retried(failure, no_sleep):
    client = MagicMock()
    if isinstance(failure, Exception):
        client.post_signed_query_auth.side_effect = failure
    else:
        client.post_signed_query_auth.return_value = failure
    with pytest.raises(api.WeeklyRequestError, match="page=2 offset=500 length=500"):
        call(client)
    assert client.post_signed_query_auth.call_count == 1
    no_sleep.assert_not_called()


def test_retry_exhaustion_is_bounded(no_sleep):
    client = MagicMock()
    client.post_signed_query_auth.return_value = dict(code="3001008", message="busy", data=None)
    with pytest.raises(api.WeeklyRequestError, match="attempt=4/4.*重试次数耗尽"):
        call(client)
    assert client.post_signed_query_auth.call_count == 4
    assert [c.args[0] for c in no_sleep.call_args_list] == [2, 4, 8]


def test_retry_after_bounds_and_http_date(no_sleep):
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
    assert 28 <= api._retry_delay(1, future) <= 30
    assert api._retry_delay(1, 'nonsense') == 2
    assert api._retry_delay(1, '-1') == 2
    client = MagicMock()
    client.post_signed_query_auth.side_effect = transport.LingXingHttpError(429, '{}', '120')
    with pytest.raises(api.WeeklyRequestError, match="Retry-After超过60秒"):
        call(client)
    assert client.post_signed_query_auth.call_count == 1
    no_sleep.assert_not_called()


def test_no_secrets_in_message_logs_or_traceback(caplog):
    client = MagicMock()
    client.app_id = "KNOWN-APP-ID"
    client.app_secret = "KNOWN-APP-SECRET"
    client._cached_token = dict(access_token="KNOWN-TOKEN")
    client.post_signed_query_auth.side_effect = wrapped(transport.LingXingHttpError(403, json.dumps({
        "code": 99,
        "message": 'KNOWN-APP-ID KNOWN-APP-SECRET KNOWN-TOKEN access_token=HIDDEN '
                   '"client_secret":"SPACE SECRET" https://host/path?sign=SIGNED '
                   'Authorization: Bearer BEARER-TOKEN\nforged-log-line',
        "request_id": "safe-id",
        "data": {"password": "RAW-BODY-SECRET"},
    })))
    with pytest.raises(api.WeeklyRequestError) as caught:
        call(client)
    rendered = ''.join(traceback.format_exception(caught.type, caught.value, caught.tb)) + caplog.text
    for secret in ('KNOWN-APP-ID', 'KNOWN-APP-SECRET', 'KNOWN-TOKEN', 'HIDDEN',
                   'SPACE SECRET', 'SIGNED', 'BEARER-TOKEN', 'RAW-BODY-SECRET', 'do-not-log'):
        assert secret not in rendered
    assert "safe-id" in rendered and "http_status=403" in rendered
    assert '\nforged-log-line' not in str(caught.value)


@pytest.mark.parametrize("responses", [
    [dict(code=0, total=3, data=[{}])],
    [dict(code=0, total=3, data=[{}, {}]), dict(code=0, total=4, data=[{}, {}])],
    [dict(code=0, total=0, data=[{}])], [dict(code=0, data=[])],
])
def test_integrity_failures_have_location_and_never_retry(responses, no_sleep):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = responses
    with pytest.raises(api.WeeklyRequestError, match="完整性校验失败.*inventoryBinDetails.*page=.*offset=.*length=2"):
        sync.fetch_pages(client, "inventoryBinDetails", 2, batch="batch-test")
    assert client.post_signed_query_auth.call_count == len(responses)
    no_sleep.assert_not_called()


@pytest.mark.parametrize('status', [429, 503])
def test_shared_transport_metadata_and_no_extra_retry(monkeypatch, no_sleep, status):
    client = transport.LingXingClient(endpoint="https://example.invalid", app_id="id", app_secret="secret", max_retries=0)
    request = MagicMock(side_effect=HTTPError('https://example.invalid', status, 'limited',
                                            {'Retry-After': '8'}, io.BytesIO(b'{"code":3001008}')))
    monkeypatch.setattr(transport, 'urlopen', request)
    with pytest.raises((transport.LingXingHttpError, RuntimeError)) as caught:
        client._execute('POST', 'read-only', body={})
    error = caught.value if status == 429 else caught.value.__cause__
    assert isinstance(error, ValueError)
    assert error.status == status and error.retry_after == '8'
    request.assert_called_once()
    no_sleep.assert_not_called()


def test_other_client_retry_behavior_unchanged(monkeypatch, no_sleep):
    client = transport.LingXingClient(endpoint='https://example.invalid', max_retries=2)
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"code":0,"data":[]}'
    request = MagicMock(side_effect=[
        HTTPError('https://example.invalid', 503, 'busy', {}, io.BytesIO(b'{}')),
        HTTPError('https://example.invalid', 503, 'busy', {}, io.BytesIO(b'{}')),
        response,
    ])
    monkeypatch.setattr(transport, 'urlopen', request)
    assert client._execute('POST', 'read-only', body={}) == dict(code=0, data=[])
    assert request.call_count == 3
    assert [c.args[0] for c in no_sleep.call_args_list] == [1, 2]


def test_scheduler_failure_record_preserves_safe_summary(monkeypatch):
    from contextlib import contextmanager
    from backend.services import scheduler_service as scheduler
    connection, logs = MagicMock(), []
    @contextmanager
    def connect():
        yield connection
    @contextmanager
    def locked(name):
        yield True
    monkeypatch.setattr(scheduler.repo, 'performance_connection', connect)
    monkeypatch.setattr(scheduler.repo, 'named_lock', locked)
    monkeypatch.setattr(scheduler.repo, 'insert_scheduler_run', lambda conn, row: logs.append(row))
    message = '接口=inventoryBinDetails batch=b page=2 offset=500 length=500 code=3001008'
    monkeypatch.setattr(scheduler, 'sync_weekly_inventory', MagicMock(side_effect=api.WeeklyRequestError(message)))
    with pytest.raises(api.WeeklyRequestError):
        scheduler.run_scheduler_task(sync.TASK_CODE, trigger_type='JOB', request_id='request-test')
    assert logs[-1]['status'] == 'failed'
    assert logs[-1]['error_message'] == message
    assert logs[-1]['request_id'] == 'request-test'


def test_failed_api_does_not_write_snapshot_and_keeps_safe_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sync.repo, 'require_bin_identity_schema', MagicMock())
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [dict(code=0, total=1, data=[dict(product_id=2)])] + [
        dict(code=3001008, message="limited", data=None)
    ] * 4
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(sync, 'LingXingClient', factory)
    monkeypatch.setattr(export, 'export_root', lambda: tmp_path)
    begin, finish, insert = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(sync.repo, 'begin_export', begin)
    monkeypatch.setattr(sync.repo, 'finish_export', finish)
    monkeypatch.setattr(sync.repo, 'insert_snapshot', insert)
    with pytest.raises(api.WeeklyRequestError):
        sync.sync_weekly_inventory()
    factory.assert_called_once_with(max_retries=0)
    insert.assert_not_called()
    assert not list(tmp_path.glob('*.xlsx'))
    message = finish.call_args.kwargs['error']
    assert 'inventoryBinDetails' in message and 'code=3001008' in message
    assert 'attempt=4/4' in message and 'page=1' in message


def test_product_batch_retries_same_ids_without_logging_them(no_sleep, caplog):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [dict(code=3001008, data=None), dict(code=0, data=[dict(id=123456789)])]
    api.request_response(client, 'batchGetProductInfo', {'productIds': [123456789]}, batch='b', page=3)
    calls = client.post_signed_query_auth.call_args_list
    assert calls[0].args == calls[1].args
    assert 'product_count=1' in caplog.text and 'page=3' in caplog.text
    assert '123456789' not in caplog.text
