import errno
import io
import json
import logging
import socket
import ssl
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.client import IncompleteRead, RemoteDisconnected
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
    wrapped(json.JSONDecodeError('invalid', 'not-json', 0)),
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
    monkeypatch.setattr(sync.repo, 'replace_snapshot_and_finish_export', insert)
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


# --------------------------------------------------------------------------
# 异常链诊断与扩充后的临时错误分类（2026-09-14）
# 背景：两次真实失败只记下 transport=RuntimeError，底层类型和错误码全部丢失。
# --------------------------------------------------------------------------


def bare_oserror(winerror=None, errno_value=None):
    """构造 errno 为空、只带 winerror 的裸 OSError。

    Windows 上 OSError(0, msg, None, 10054) 会自动变成 ConnectionResetError，
    走不到补丁要修的分支，所以这里显式赋值。
    """
    exc = OSError()
    if winerror is not None:
        exc.winerror = winerror
    if errno_value is not None:
        exc.errno = errno_value
    return exc


def context_wrapped(inner, suppress=False):
    """只通过 __context__ 关联（raise 时不写 from），可选 from None 抑制。"""
    try:
        try:
            raise inner
        except type(inner):
            if suppress:
                raise RuntimeError("RAW access_token=do-not-log") from None
            raise RuntimeError("RAW access_token=do-not-log")
    except RuntimeError as exc:
        return exc


@pytest.mark.parametrize("winerror", [10053, 10054, 10060])
def test_windows_bare_oserror_winerror_retried(winerror, no_sleep):
    """errno 为空、只有 Winsock 码的裸 OSError 必须重试。补丁前会被判为不可重试。"""
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [wrapped(bare_oserror(winerror=winerror)), ok()]
    assert call(client)["code"] == 0
    assert client.post_signed_query_auth.call_count == 2


def test_urlerror_wrapping_oserror_is_walked_and_retried(no_sleep, caplog):
    """RuntimeError -> URLError -> OSError(10054)：整条链要被走出来并重试。"""
    caplog.set_level(logging.WARNING)
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [
        wrapped(URLError(bare_oserror(winerror=10054))), ok(),
    ]
    assert call(client)["code"] == 0
    assert "exception_chain=RuntimeError->URLError->OSError" in caplog.text
    assert "winerror=10054" in caplog.text


@pytest.mark.parametrize("exc", [
    ssl.SSLEOFError(), ssl.SSLZeroReturnError(), RemoteDisconnected("closed"),
])
def test_tls_and_disconnect_failures_retried(exc, no_sleep):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [wrapped(exc), ok()]
    assert call(client)["code"] == 0
    assert client.post_signed_query_auth.call_count == 2


def test_incomplete_read_retried_and_partial_body_never_logged(no_sleep, caplog):
    """半截响应要重试，且只记字节数，绝不记 partial 内容。"""
    caplog.set_level(logging.WARNING)
    partial = b"<html>access_token=leak-me-please</html>"
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [wrapped(IncompleteRead(partial, 4096)), ok()]
    assert call(client)["code"] == 0
    assert f"partial_bytes={len(partial)}" in caplog.text
    assert "expected_remaining_bytes=4096" in caplog.text
    assert "leak-me-please" not in caplog.text


def test_context_only_chain_is_readable(no_sleep, caplog):
    """没写 from、仅靠 __context__ 关联时也要能读出底层类型。"""
    caplog.set_level(logging.WARNING)
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [
        context_wrapped(ConnectionResetError("reset")), ok(),
    ]
    assert call(client)["code"] == 0
    assert "exception_chain=RuntimeError->ConnectionResetError" in caplog.text


def test_suppressed_context_is_not_dug_out(no_sleep):
    """raise ... from None 明确抑制了上下文，不能绕过去把它挖出来。"""
    client = MagicMock()
    client.post_signed_query_auth.side_effect = context_wrapped(
        ConnectionResetError("reset"), suppress=True)
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    assert client.post_signed_query_auth.call_count == 1
    assert "exception_chain=RuntimeError" in str(excinfo.value)
    assert "ConnectionResetError" not in str(excinfo.value)


def test_certificate_failure_never_retried(no_sleep):
    """证书校验失败不能靠重试掩盖。"""
    client = MagicMock()
    client.post_signed_query_auth.side_effect = wrapped(
        ssl.SSLCertVerificationError("bad cert"))
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    assert client.post_signed_query_auth.call_count == 1
    assert "TLS证书校验失败" in str(excinfo.value)


@pytest.mark.parametrize("exc", [
    bare_oserror(errno_value=errno.ENOSPC),
    bare_oserror(winerror=1),
    RuntimeError("plain"),
    ssl.SSLError("generic"),
])
def test_unknown_failures_still_not_retried(exc, no_sleep):
    """没有证据证明是临时错误的，仍然一次就停。"""
    client = MagicMock()
    client.post_signed_query_auth.side_effect = exc if isinstance(exc, RuntimeError) else wrapped(exc)
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    assert client.post_signed_query_auth.call_count == 1
    assert "非明确临时错误" in str(excinfo.value)


def test_json_decode_reports_position_not_body(no_sleep, caplog):
    """解析失败要能定位，但不能输出响应正文。"""
    caplog.set_level(logging.ERROR)
    body = '<html>Bearer secret-token-value</html>'
    client = MagicMock()
    client.post_signed_query_auth.side_effect = wrapped(
        json.JSONDecodeError("Expecting value", body, 0))
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    message = str(excinfo.value)
    assert client.post_signed_query_auth.call_count == 1
    assert "json_line=1" in message and "json_position=0" in message
    assert f"response_chars={len(body)}" in message
    assert "secret-token-value" not in message and "secret-token-value" not in caplog.text
    assert "<html>" not in message


def test_cyclic_chain_terminates(no_sleep):
    first = RuntimeError("a")
    second = RuntimeError("b")
    first.__cause__ = second
    second.__cause__ = first
    client = MagicMock()
    client.post_signed_query_auth.side_effect = first
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    assert "exception_chain=RuntimeError->RuntimeError" in str(excinfo.value)


def test_chain_depth_is_bounded(no_sleep):
    deepest = ConnectionResetError("reset")
    current = deepest
    for _ in range(12):
        wrapper = RuntimeError("layer")
        wrapper.__cause__ = current
        current = wrapper
    client = MagicMock()
    client.post_signed_query_auth.side_effect = current
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    # 深度封顶 8 层，走不到最里面那个 ConnectionResetError，所以不重试。
    chain = [p for p in str(excinfo.value).split() if p.startswith("exception_chain=")][0]
    assert len(chain.split("->")) == api.MAX_CHAIN_DEPTH
    assert client.post_signed_query_auth.call_count == 1


def test_repeated_temporary_failures_still_bounded(no_sleep):
    """连续临时错误，总请求数仍受 MAX_ATTEMPTS 限制。"""
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [
        wrapped(bare_oserror(winerror=10054)) for _ in range(api.MAX_ATTEMPTS)
    ]
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    assert client.post_signed_query_auth.call_count == api.MAX_ATTEMPTS
    assert "重试次数耗尽" in str(excinfo.value)


def test_diagnostics_never_leak_secrets_from_raw_exception(no_sleep, caplog):
    """底层异常原文含 token/签名URL/产品ID 时，日志和最终异常都不得出现。"""
    caplog.set_level(logging.DEBUG)
    inner = bare_oserror(winerror=1)
    inner.strerror = "https://api.lingxing.com/x?access_token=SECRET&sku=BMW-30001-0001"
    client = MagicMock()
    client.post_signed_query_auth.side_effect = wrapped(inner)
    with pytest.raises(api.WeeklyRequestError) as excinfo:
        call(client)
    combined = str(excinfo.value) + caplog.text
    for leak in ("SECRET", "BMW-30001-0001", "api.lingxing.com", "do-not-log"):
        assert leak not in combined


@pytest.mark.parametrize("endpoint,body", [
    ("inventoryDetails", {"offset": 4800, "length": 800}),
    ("inventoryBinDetails", {"offset": 11000, "length": 500}),
    ("batchGetProductInfo", {"productIds": [123456789]}),
])
def test_json_eof_retries_identical_page_or_batch(endpoint, body, no_sleep, caplog):
    client = MagicMock()
    document = '{"code":0,"data":['
    client.post_signed_query_auth.side_effect = [
        wrapped(json.JSONDecodeError("Expecting value", document, len(document))), ok(),
    ]
    assert api.request_response(client, endpoint, body, batch="eof-test", page=23)["code"] == 0
    calls = client.post_signed_query_auth.call_args_list
    assert len(calls) == 2 and calls[0].args == calls[1].args
    assert calls[0].args[1] == body
    no_sleep.assert_called_once_with(2)
    assert "JSON响应末尾解析失败" in caplog.text
    assert document not in caplog.text and "123456789" not in caplog.text


def test_json_eof_exhaustion_stops_after_four_attempts(no_sleep):
    client = MagicMock()
    document = '{"code":'
    client.post_signed_query_auth.side_effect = wrapped(
        json.JSONDecodeError("Expecting value", document, len(document)))
    with pytest.raises(api.WeeklyRequestError, match="attempt=4/4.*重试次数耗尽"):
        call(client)
    assert client.post_signed_query_auth.call_count == 4
    assert [entry.args[0] for entry in no_sleep.call_args_list] == [2, 4, 8]


@pytest.mark.parametrize("document,position", [
    ("not-json", 0), ('{"a":1,}', 7), ('{"a":"incomplete', 5),
])
def test_json_non_eof_still_stops_immediately(document, position, no_sleep):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = wrapped(
        json.JSONDecodeError("invalid", document, position))
    with pytest.raises(api.WeeklyRequestError, match="JSON非末尾解析失败"):
        call(client)
    assert client.post_signed_query_auth.call_count == 1
    no_sleep.assert_not_called()


@pytest.mark.parametrize("headers,expected_type,expected_length", [
    ({"Content-Type": "application/json; secret=HEADER-SECRET", "Content-Length": "999"}, "application/json", 999),
    ({"Content-Type": "HEADER-SECRET", "Content-Length": "TOKEN-SECRET"}, "other", None),
    ({}, "unknown", None),
])
def test_json_parse_metadata_is_safe_and_preserves_client_behavior(
    monkeypatch, no_sleep, headers, expected_type, expected_length,
):
    client = transport.LingXingClient(endpoint="https://example.invalid", max_retries=0)
    document = '{"name":"产品-BODY-SECRET","data":['
    body = document.encode("utf-8")
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = body
    response.status = 200
    response.headers = headers
    request = MagicMock(return_value=response)
    monkeypatch.setattr(transport, "urlopen", request)
    with pytest.raises(RuntimeError) as caught:
        client._execute("POST", "read-only", body={})
    assert isinstance(caught.value.__cause__, json.JSONDecodeError)
    metadata = caught.value.__cause__.lingxing_response_metadata
    assert metadata["http_status"] == 200
    assert metadata["response_bytes"] == len(body) > len(document)
    assert metadata["content_type"] == expected_type
    assert metadata.get("content_length") == expected_length
    retryable, _, detail = api._transport_failure(caught.value, client)
    assert retryable
    assert "http_status=200" in detail and f"response_bytes={len(body)}" in detail
    for secret in ("BODY-SECRET", "HEADER-SECRET", "TOKEN-SECRET", "产品"):
        assert secret not in detail
    request.assert_called_once()
    no_sleep.assert_not_called()


def test_json_eof_failure_never_writes_partial_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(sync.repo, "require_bin_identity_schema", MagicMock())
    document = '{"data":['
    client = MagicMock()
    client.post_signed_query_auth.side_effect = wrapped(
        json.JSONDecodeError("Expecting value", document, len(document)))
    monkeypatch.setattr(sync, "LingXingClient", MagicMock(return_value=client))
    monkeypatch.setattr(export, "export_root", lambda: tmp_path)
    monkeypatch.setattr(sync.repo, "begin_export", MagicMock())
    finish, insert = MagicMock(), MagicMock()
    monkeypatch.setattr(sync.repo, "finish_export", finish)
    monkeypatch.setattr(sync.repo, "replace_snapshot_and_finish_export", insert)
    with pytest.raises(api.WeeklyRequestError, match="重试次数耗尽"):
        sync.sync_weekly_inventory()
    assert client.post_signed_query_auth.call_count == 4
    insert.assert_not_called()
    assert not list(tmp_path.glob("*.xlsx"))
    assert "JSON响应末尾解析失败" in finish.call_args.kwargs["error"]
