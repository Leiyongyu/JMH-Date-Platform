"""Offline regression cases; never call GoodCang or a database."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.integrations.goodcang import client as api
from backend.services import goodcang_storage_sync_service as service


def test_inclusive_window_uses_china_time():
    start, end = service.recent_window(datetime(2026, 9, 14, 23, tzinfo=timezone.utc))
    assert start == datetime(2026, 8, 17)
    assert end == datetime(2026, 9, 15, 7)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e18", "0.0000000000001", True, 1.2])
def test_decimal_rejects_lossy_or_invalid_values(value):
    with pytest.raises(ValueError):
        service._decimal(value, "is_amount")


def test_precision_and_null_preserved():
    assert service._decimal(None, "is_amount") is None
    value = "999999999999999999.999999999999"
    assert service._decimal(value, "is_amount") == Decimal(value)
    assert api.source_json({"number": Decimal("0.123456789012")}) == '{"number":0.123456789012}'


def configured_client(handler):
    config = SimpleNamespace(
        goodcang_endpoint="https://oms.goodcang.net/public_open",
        goodcang_app_token="test-token", goodcang_app_key="test-key",
        goodcang_max_retries=1, goodcang_min_request_interval_sec=0,
        goodcang_request_timeout_sec=1,
    )
    return api.GoodcangClient(config, transport=httpx.MockTransport(handler))


def test_client_uses_correct_headers_and_page_size():
    import json

    def handler(request):
        assert request.headers["app-token"] == "test-token"
        assert request.headers["app-key"] == "test-key"
        assert json.loads(request.content) == {
            "dateFrom": "from", "dateTo": "to", "page": 3, "pageSize": 200,
        }
        return httpx.Response(200, content=b'{"ask":"Success","count":0,"data":[]}')

    with configured_client(handler) as client:
        assert client.fetch_storage_page("from", "to", 3)["ask"] == "Success"


def test_auth_error_not_retried_and_body_not_exposed():
    handler = Mock(return_value=httpx.Response(401, text="test-token secret-error"))
    with configured_client(handler) as client:
        with pytest.raises(api.GoodcangRequestError) as error:
            client.fetch_storage_page("from", "to", 1)
    assert handler.call_count == 1
    assert "test-token" not in str(error.value)
    assert "secret-error" not in str(error.value)


def mocked_sync(monkeypatch, responses):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.fetch_storage_page.side_effect = responses
    monkeypatch.setattr(service, "GoodcangClient", lambda: client)
    writer = Mock(return_value={"ods_rows": 0, "inserted_rows": 0, "deleted_rows": 0})
    monkeypatch.setattr(service.repo, "replace_storage_rows", writer)
    return client, writer


def test_complete_paging_before_replacement(monkeypatch):
    first = [{"wis_code": str(i), "is_amount": "0.123456789012"} for i in range(200)]
    client, writer = mocked_sync(monkeypatch, [
        {"ask": "Success", "count": 201, "data": first},
        {"ask": "Success", "count": 201, "data": [{"wis_code": "200"}]},
    ])
    result = service.sync_goodcang_storage()
    assert result["extract_rows"] == 201
    assert result["page_count"] == 2
    calls = client.fetch_storage_page.call_args_list
    assert calls[0].args[:2] == calls[1].args[:2]
    assert [c.args[2] for c in calls] == [1, 2]
    writer.assert_called_once()
    assert len(writer.call_args.args[0]) == 201
    assert writer.call_args.args[0][0]["is_amount"] == Decimal("0.123456789012")


@pytest.mark.parametrize("response", [
    {"code": 0, "count": 0, "data": []},
    {"ask": "Success", "count": 2, "data": [{"wis_code": "a"}]},
    {"ask": "Success", "count": 0, "data": {}},
    {"ask": "Error", "count": 0, "data": []},
])
def test_invalid_pages_never_delete_old_data(monkeypatch, response):
    _, writer = mocked_sync(monkeypatch, [response])
    with pytest.raises(service.GoodcangStorageSyncError) as error:
        service.sync_goodcang_storage()
    assert error.value.stage == "EXTRACT"
    writer.assert_not_called()


def test_confirmed_empty_replaces_with_empty(monkeypatch):
    _, writer = mocked_sync(monkeypatch, [{"ask": "Success", "count": 0, "data": []}])
    service.sync_goodcang_storage()
    writer.assert_called_once_with([])

