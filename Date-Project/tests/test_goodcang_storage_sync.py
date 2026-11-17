"""Offline regression cases; never call GoodCang or a database."""
import json
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


@pytest.mark.parametrize("now,expected_start", [
    (datetime(2026, 1, 1, 12), datetime(2025, 12, 3)),
    (datetime(2024, 3, 1, 1), datetime(2024, 2, 1)),
])
def test_inclusive_window_crosses_month_or_year(now, expected_start):
    start, end = service.recent_window(now)
    assert start == expected_start
    assert end == now


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
    def handler(request):
        assert request.url.path == "/public_open/finance/get_wh_inventory_storage"
        assert request.headers["app-token"] == "test-token"
        assert request.headers["app-key"] == "test-key"
        assert json.loads(request.content) == {
            "dateFrom": "from", "dateTo": "to", "page": 3, "pageSize": 200,
        }
        return httpx.Response(200, content=b'{"ask":"Success","count":0,"data":[]}')

    with configured_client(handler) as client:
        assert client.fetch_storage_page("from", "to", 3)["ask"] == "Success"


def test_detail_client_uses_documented_snake_case_paging_and_exact_decimal():
    def handler(request):
        assert request.url.path == "/public_open/finance/get_wh_inventory_storage_detail"
        assert request.headers["app-token"] == "test-token"
        assert request.headers["app-key"] == "test-key"
        assert json.loads(request.content) == {
            "wis_code": "WTG-TEST", "page_index": 4, "page_size": 200,
        }
        return httpx.Response(
            200,
            content=b'{"ask":"Success","count":1,"data":[{"bill_amount":0.123456789012}]}',
        )

    with configured_client(handler) as client:
        response = client.fetch_storage_detail_page("WTG-TEST", 4)
    assert response["data"][0]["bill_amount"] == Decimal("0.123456789012")


@pytest.mark.parametrize("detail", [False, True])
def test_auth_error_not_retried_and_body_not_exposed(detail):
    handler = Mock(return_value=httpx.Response(401, text="test-token secret-error"))
    with configured_client(handler) as client:
        with pytest.raises(api.GoodcangRequestError) as error:
            if detail:
                client.fetch_storage_detail_page("WTG-TEST", 1)
            else:
                client.fetch_storage_page("from", "to", 1)
    assert handler.call_count == 1
    assert "test-token" not in str(error.value)
    assert "secret-error" not in str(error.value)


@pytest.mark.parametrize("status", [429, 503])
def test_detail_client_retries_same_bill_and_page_with_bounded_budget(monkeypatch, status):
    monkeypatch.setattr(api.time, "sleep", lambda _seconds: None)
    requests = []

    def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        if len(requests) == 1:
            return httpx.Response(status, text="private-response-body")
        return httpx.Response(200, json={"ask": "Success", "count": 0, "data": []})

    with configured_client(handler) as client:
        assert client.fetch_storage_detail_page("WTG-TEST", 2)["count"] == 0
    assert len(requests) == 2
    assert requests[0] == requests[1]


def test_detail_client_exhausted_retries_never_exposes_response(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda _seconds: None)
    handler = Mock(return_value=httpx.Response(503, text="test-key private-response-body"))
    with configured_client(handler) as client:
        with pytest.raises(api.GoodcangRequestError) as error:
            client.fetch_storage_detail_page("WTG-TEST", 1)
    assert handler.call_count == 2
    assert "test-key" not in str(error.value)
    assert "private-response-body" not in str(error.value)


def mocked_sync(monkeypatch, responses, detail_responses=None):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.fetch_storage_page.side_effect = responses
    if detail_responses is None:
        client.fetch_storage_detail_page.return_value = {"ask": "Success", "count": 0, "data": []}
    else:
        client.fetch_storage_detail_page.side_effect = detail_responses
    monkeypatch.setattr(service, "GoodcangClient", lambda: client)
    captured = {}

    def replace(summary_rows, detail_rows):
        # Detail rows may stream from a temporary spool. Consume while it is open,
        # exactly as the real transactional writer does, not after sync returns.
        captured["summary"] = list(summary_rows)
        captured["detail"] = list(detail_rows)
        size = len(captured["summary"]) + len(captured["detail"])
        return {"ods_rows": size, "inserted_rows": size, "deleted_rows": 0}

    writer = Mock(side_effect=replace)
    monkeypatch.setattr(service.repo, "replace_storage_snapshot", writer)
    return client, writer, captured


def summary(*bill_codes):
    return {
        "ask": "Success", "count": len(bill_codes),
        "data": [{"wis_code": code} for code in bill_codes],
    }


def test_complete_summary_paging_before_replacement(monkeypatch):
    first = [{"wis_code": str(i), "is_amount": "0.123456789012"} for i in range(200)]
    client, writer, captured = mocked_sync(monkeypatch, [
        {"ask": "Success", "count": 201, "data": first},
        {"ask": "Success", "count": 201, "data": [{"wis_code": "200"}]},
    ])
    result = service.sync_goodcang_storage()
    assert result["extract_rows"] == 201
    assert result["summary_rows"] == 201
    assert result["detail_rows"] == 0
    assert result["page_count"] == 2
    assert result["detail_page_count"] == 201
    assert result["bill_count"] == result["completed_bills"] == result["empty_detail_bills"] == 201
    calls = client.fetch_storage_page.call_args_list
    assert calls[0].args[:2] == calls[1].args[:2]
    assert [c.args[2] for c in calls] == [1, 2]
    writer.assert_called_once()
    assert len(captured["summary"]) == 201
    assert captured["summary"][0]["is_amount"] == Decimal("0.123456789012")


def test_detail_paging_uses_each_distinct_trimmed_bill_only_once(monkeypatch):
    first = [
        {"wis_code": "WTG-A", "product_sku": str(i), "bill_amount": "0.123456789012"}
        for i in range(200)
    ]
    client, writer, captured = mocked_sync(monkeypatch, [summary("WTG-A", " WTG-A ", "WTG-B")], [
        {"ask": "Success", "count": 201, "data": first},
        {"ask": "Success", "count": 201, "data": [{"wis_code": "WTG-A", "product_sku": "200"}]},
        {"ask": "Success", "count": 1, "data": [{"wis_code": "WTG-B", "product_sku": "B"}]},
    ])
    result = service.sync_goodcang_storage()
    assert [call.args for call in client.fetch_storage_detail_page.call_args_list] == [
        ("WTG-A", 1), ("WTG-A", 2), ("WTG-B", 1),
    ]
    assert result["summary_rows"] == 3
    assert result["detail_rows"] == 202
    assert result["extract_rows"] == result["ods_rows"] == 205
    assert result["bill_count"] == result["completed_bills"] == 2
    assert result["detail_page_count"] == 3
    assert result["empty_detail_bills"] == 0
    writer.assert_called_once()
    assert len(captured["summary"]) == 3  # Dedup applies to requests, never raw source rows.
    assert len(captured["detail"]) == 202
    assert captured["detail"][0]["bill_amount"] == Decimal("0.123456789012")
    assert captured["detail"][200]["source_page"] == 2
    assert captured["detail"][200]["source_row_no"] == 1
    assert captured["detail"][200]["request_wis_code"] == "WTG-A"
    all_rows = captured["summary"] + captured["detail"]
    for field in ["sync_batch_id", "pulled_at", "request_date_from", "request_date_to"]:
        assert len({row[field] for row in all_rows}) == 1


@pytest.mark.parametrize("response", [
    {"code": 0, "count": 0, "data": []},
    {"ask": "Success", "count": 2, "data": [{"wis_code": "a"}]},
    {"ask": "Success", "count": 0, "data": {}},
    {"ask": "Error", "count": 0, "data": []},
])
def test_invalid_summary_pages_never_delete_old_data(monkeypatch, response):
    client, writer, _ = mocked_sync(monkeypatch, [response])
    with pytest.raises(service.GoodcangStorageSyncError) as error:
        service.sync_goodcang_storage()
    assert error.value.stage == "EXTRACT"
    writer.assert_not_called()
    client.fetch_storage_detail_page.assert_not_called()


@pytest.mark.parametrize("bill", [None, "", "  "])
def test_summary_without_bill_number_never_replaces_either_table(monkeypatch, bill):
    _, writer, _ = mocked_sync(monkeypatch, [summary(bill)])
    with pytest.raises(service.GoodcangStorageSyncError):
        service.sync_goodcang_storage()
    writer.assert_not_called()


@pytest.mark.parametrize("response", [
    {"code": 0, "count": 0, "data": []},
    {"ask": "Error", "count": 0, "data": []},
    {"ask": "Success", "count": 1},
    {"ask": "Success", "count": 1, "data": None},
    {"ask": "Success", "count": 0, "data": {}},
    {"ask": "Success", "count": 1, "data": ["invalid-row"]},
    {"ask": "Success", "count": 2, "data": [{"product_sku": "a"}]},
    {"ask": "Success", "count": 1, "data": [{"wis_code": "WTG-OTHER"}]},
])
def test_invalid_detail_pages_never_replace_either_table(monkeypatch, response):
    _, writer, _ = mocked_sync(monkeypatch, [summary("WTG-A")], [response])
    with pytest.raises(service.GoodcangStorageSyncError):
        service.sync_goodcang_storage()
    writer.assert_not_called()


def test_later_bill_failure_does_not_publish_partial_success(monkeypatch):
    _, writer, _ = mocked_sync(monkeypatch, [summary("WTG-A", "WTG-B")], [
        {"ask": "Success", "count": 1, "data": [{"wis_code": "WTG-A", "product_sku": "ok"}]},
        {"ask": "Error", "count": 0, "data": []},
    ])
    with pytest.raises(service.GoodcangStorageSyncError):
        service.sync_goodcang_storage()
    writer.assert_not_called()


def test_changed_detail_count_preserves_old_snapshot(monkeypatch):
    first = [{"product_sku": str(i)} for i in range(200)]
    _, writer, _ = mocked_sync(monkeypatch, [summary("WTG-A")], [
        {"ask": "Success", "count": 201, "data": first},
        {"ask": "Success", "count": 202, "data": [{"product_sku": "last"}]},
    ])
    with pytest.raises(service.GoodcangStorageSyncError) as error:
        service.sync_goodcang_storage()
    assert error.value.stage == "DETAIL_EXTRACT"
    writer.assert_not_called()


def test_replayed_full_detail_page_preserves_old_snapshot(monkeypatch):
    first = [{"product_sku": str(i)} for i in range(200)]
    _, writer, _ = mocked_sync(monkeypatch, [summary("WTG-A")], [
        {"ask": "Success", "count": 400, "data": first},
        {"ask": "Success", "count": 400, "data": list(first)},
    ])
    with pytest.raises(service.GoodcangStorageSyncError):
        service.sync_goodcang_storage()
    writer.assert_not_called()


def test_identical_individual_batch_rows_are_retained_even_across_pages(monkeypatch):
    first = [{"product_sku": str(i)} for i in range(200)]
    _, writer, captured = mocked_sync(monkeypatch, [summary("WTG-A")], [
        {"ask": "Success", "count": 201, "data": first},
        {"ask": "Success", "count": 201, "data": [{"product_sku": "0"}]},
    ])
    service.sync_goodcang_storage()
    writer.assert_called_once()
    assert len(captured["detail"]) == 201
    assert captured["detail"][0]["product_sku"] == captured["detail"][-1]["product_sku"] == "0"


@pytest.mark.parametrize("empty_response", [
    {"ask": "Success", "count": 0},
    {"ask": "Success", "count": 0, "data": None},
    {"ask": "Success", "count": 0, "data": []},
])
def test_confirmed_empty_bill_is_valid_and_still_keeps_summary(monkeypatch, empty_response):
    _, writer, captured = mocked_sync(monkeypatch, [summary("WTG-A")], [empty_response])
    result = service.sync_goodcang_storage()
    writer.assert_called_once()
    assert len(captured["summary"]) == 1
    assert captured["detail"] == []
    assert result["completed_bills"] == result["empty_detail_bills"] == 1


def test_confirmed_empty_summary_replaces_both_with_empty(monkeypatch):
    client, writer, captured = mocked_sync(monkeypatch, [summary()])
    result = service.sync_goodcang_storage()
    writer.assert_called_once()
    assert captured == {"summary": [], "detail": []}
    client.fetch_storage_detail_page.assert_not_called()
    assert result["bill_count"] == result["detail_rows"] == result["extract_rows"] == 0


def test_detail_keeps_precise_values_original_missing_bill_and_request_link(monkeypatch):
    source = {
        "product_sku": "SKU-1", "product_barcode": "000001", "reference_no": "000123",
        "quantity": 0, "day": "423", "length": Decimal("10.123456789012"),
        "width": None, "height": "5.000", "volume": Decimal("0.000000000001"),
        "bill_amount": Decimal("-0.123456789012"), "settlement_amount": "0",
        "warehouse_rent_amount": None, "extra_from_api": {"value": "retained"},
    }
    _, _, captured = mocked_sync(monkeypatch, [summary("WTG-A")], [
        {"ask": "Success", "count": 1, "data": [source]},
    ])
    service.sync_goodcang_storage()
    row = captured["detail"][0]
    assert row["wis_code"] is None
    assert row["request_wis_code"] == "WTG-A"
    assert row["quantity"] == 0
    assert row["day"] == 423
    assert row["length"] == Decimal("10.123456789012")
    assert row["volume"] == Decimal("0.000000000001")
    assert row["bill_amount"] == Decimal("-0.123456789012")
    assert row["width"] is row["warehouse_rent_amount"] is None
    assert row["product_barcode"] == "000001"
    assert row["reference_no"] == "000123"
    raw = json.loads(row["raw_json"], parse_float=Decimal)
    assert "wis_code" not in raw
    assert raw["bill_amount"] == source["bill_amount"]
    assert raw["extra_from_api"] == source["extra_from_api"]


@pytest.mark.parametrize("field,value", [
    ("quantity", "1.5"), ("quantity", True), ("day", "0.1"), ("day", False),
    ("bill_amount", "NaN"), ("volume", "0.0000000000001"),
])
def test_invalid_detail_numeric_fields_never_replace_old_tables(monkeypatch, field, value):
    _, writer, _ = mocked_sync(monkeypatch, [summary("WTG-A")], [
        {"ask": "Success", "count": 1, "data": [{field: value}]},
    ])
    with pytest.raises(service.GoodcangStorageSyncError):
        service.sync_goodcang_storage()
    writer.assert_not_called()
