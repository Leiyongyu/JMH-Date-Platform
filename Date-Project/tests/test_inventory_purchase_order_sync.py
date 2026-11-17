from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.services import inventory_purchase_order_sync_service as service
from backend.repositories import inventory_report_etl_repository as report_repo


def order(number="PO-1", **overrides):
    result = {"order_sn": number, "custom_order_sn": "CUSTOM-1", "status": 2,
              "wid": "1", "ware_house_name": "CTUAMZ-US3中转仓", "purchase_currency": "CNY",
              "item_list": [{"id": "1", "sku": "SKU-1", "wid": "1", "ware_house_name": "",
                             "sid": 0, "price": "1090", "tax_rate": "10", "quantity_receive": "20",
                             "is_delete": 0}]}
    result.update(overrides)
    return result


def transform(orders, shops=None):
    return service.transform_orders({o["order_sn"]: o for o in orders}, "2026-10", "batch", shops or {})


def test_all_lines_tax_conversion_and_system_number():
    source = order()
    source["item_list"].append({**source["item_list"][0], "id": "2", "quantity_receive": "2"})
    result = transform([source])
    assert len(result["rows"]) == 2  # Same SKU is allowed on distinct line IDs.
    assert result["total_pending_arrival_qty"] == 22
    assert result["total_pending_cost"] == Decimal("21800.0002")
    assert all(row["unit_price"] == Decimal("990.9091") for row in result["rows"])
    assert all(row["department_code"] == "AMZ-US2-MJ" for row in result["rows"])
    assert result["rows"][0]["purchase_order_no"] == "PO-1"
    assert result["active_orders"][0]["custom_order_sn"] == "CUSTOM-1"


def test_completed_and_deleted_lines_leave_transit_and_zero_is_valid():
    source = order()
    source["item_list"][0]["quantity_receive"] = "0"
    source["item_list"].append({**source["item_list"][0], "id": "2", "is_delete": 1, "quantity_receive": None})
    result = transform([source, order("PO-2", status=3)])
    assert len(result["rows"]) == 1
    assert result["total_pending_arrival_qty"] == 0
    assert result["skipped_rows"] == 1


def test_detail_warehouse_priority_and_unknown_warehouse_is_visible():
    source = order()
    source["item_list"][0]["ware_house_name"] = "CTUebay-UK中转仓"
    source["item_list"].append({**source["item_list"][0], "id": "2", "ware_house_name": "其他仓"})
    result = transform([source])
    assert result["rows"][0]["department_code"] == "EBAY-1"
    assert result["excluded_warehouses"] == {"其他仓": 1}


@pytest.mark.parametrize("field,value", [("quantity_receive", None), ("quantity_receive", "-1"),
    ("price", "NaN"), ("tax_rate", None), ("tax_rate", "101"), ("sku", ""),
    ("id", ""), ("is_delete", "2"), ("sid", "999"), ("wid", "different")])
def test_invalid_data_fails_instead_of_defaulting_to_zero(field, value):
    source = order()
    source["item_list"][0][field] = value
    with pytest.raises(ValueError):
        transform([source])


def test_currency_and_duplicate_line_rejected():
    with pytest.raises(ValueError, match="人民币"):
        transform([order(purchase_currency="USD")])
    source = order()
    source["item_list"].append(dict(source["item_list"][0]))
    with pytest.raises(ValueError, match="重复"):
        transform([source])


def test_sid_store_mapping_does_not_guess():
    source = order()
    source["item_list"][0]["sid"] = 123
    assert transform([source], {"123": "EU-示例-DE"})["rows"][0]["store_name"] == "EU-示例-DE"


def test_full_pagination_reads_all_statuses_without_status_request_filter(monkeypatch):
    calls = []
    def request(_client, body):
        calls.append(body)
        return {"total": 501, "data": [order(str(i)) for i in range(body["offset"], min(501, body["offset"] + 500))]}
    monkeypatch.setattr(service, "_request", request)
    result = service.fetch_orders(None, "2000-01-01", "2026-11-02", full=True)
    assert len(result) == 501
    assert [c["offset"] for c in calls] == [0, 500]
    assert all("status" not in c and c["length"] == 500 for c in calls)
    assert calls[0]["search_field_time"] == "create_time"


@pytest.mark.parametrize("responses", [
    [{"total": 1, "data": []}],
    [{"total": 2, "data": [order(), order()]}],
    [{"total": 0, "data": []}],
])
def test_partial_duplicate_and_empty_full_fetch_rejected(monkeypatch, responses):
    monkeypatch.setattr(service, "_request", lambda *_: responses.pop(0))
    with pytest.raises(ValueError):
        service.fetch_orders(None, "2000-01-01", "2026-11-02", full=True)


def test_empty_increment_is_allowed_and_uses_update_time(monkeypatch):
    def request(_client, body):
        assert body["search_field_time"] == "update_time"
        return {"total": 0, "data": []}
    monkeypatch.setattr(service, "_request", request)
    assert service.fetch_orders(None, "2026-10-30", "2026-11-02", full=False) == {}


def test_changed_total_rejected(monkeypatch):
    monkeypatch.setattr(service, "PAGE_SIZE", 1)
    replies = [{"total": 2, "data": [order()]}, {"total": 3, "data": [order("PO-2")]}]
    monkeypatch.setattr(service, "_request", lambda *_: replies.pop(0))
    with pytest.raises(ValueError, match="total"):
        service.fetch_orders(None, "2000-01-01", "2026-11-02", full=True)


def test_request_rate_limit_retries_without_logging_secrets(monkeypatch):
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [
        {"code": 3001008, "message": "secret"}, {"code": 0, "data": [], "total": 0}]
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    service._request(client, {"offset": 0})
    assert client.post_signed_query_auth.call_count == 2
    client.post_signed_query_auth.side_effect = None
    client.post_signed_query_auth.return_value = {"code": 1, "message": "secret"}
    with pytest.raises(service.PurchaseOrderSyncError) as error:
        service._request(client, {"offset": 0})
    assert "secret" not in str(error.value)


@pytest.fixture
def sync_setup(monkeypatch):
    now = datetime(2026, 11, 2, 8, 30)
    previous = {"pulled_at": datetime(2026, 11, 1), "full_pulled_at": datetime(2026, 10, 30)}
    monkeypatch.setattr(service, "now_shanghai", lambda: now)
    monkeypatch.setattr(service.repo, "state", lambda: previous)
    monkeypatch.setattr(service.report_repo, "view_snapshot", lambda *_: None)
    monkeypatch.setattr(service.repo, "shop_map", lambda: {})
    monkeypatch.setattr(service, "LingXingClient", lambda **_: None)
    monkeypatch.setattr(service, "named_lock", lambda _: nullcontext(True))
    monkeypatch.setattr(service.report_repo, "purchase_order_transaction", lambda: nullcontext("connection"))
    publication = MagicMock(return_value={})
    monkeypatch.setattr(service, "publish_inventory_report_purchase_order", publication)
    cache = MagicMock()
    monkeypatch.setattr(service.repo, "publish_cache", cache)
    return previous, publication, cache


def test_increment_keeps_old_orders_and_removes_completed_order(monkeypatch, sync_setup):
    previous, publication, cache = sync_setup
    old = order("PO-OLD", create_time="2021-01-01")
    monkeypatch.setattr(service.repo, "cached_orders", lambda: {"PO-OLD": old, "PO-1": order()})
    def fetch(_client, start, end, *, full):
        assert (start, end, full) == ("2026-10-30", "2026-11-02", False)
        return {"PO-1": order(status=3)}
    monkeypatch.setattr(service, "fetch_orders", fetch)
    result = service.sync_purchase_orders()
    assert result["mode"] == "INCREMENTAL"
    assert [r["purchase_order_no"] for r in publication.call_args.args[0]["rows"]] == ["PO-OLD"]
    assert cache.call_args.kwargs["previous_state"] is previous
    assert cache.call_args.kwargs["stat_month"] == "2026-10"


def test_weekly_full_drops_missing_orders(monkeypatch, sync_setup):
    previous, publication, cache = sync_setup
    previous["full_pulled_at"] = datetime(2026, 10, 20)
    def fetch(_client, start, _end, *, full):
        assert start == "2000-01-01" and full
        return {"PO-2": order("PO-2")}
    monkeypatch.setattr(service, "fetch_orders", fetch)
    monkeypatch.setattr(service.repo, "cached_orders", lambda: pytest.fail("full must not load old cache"))
    service.sync_purchase_orders()
    assert publication.call_args.args[0]["rows"][0]["purchase_order_no"] == "PO-2"
    assert cache.call_args.kwargs["full"]


def test_extract_failure_never_publishes(monkeypatch, sync_setup):
    _, publication, cache = sync_setup
    monkeypatch.setattr(service, "fetch_orders", MagicMock(side_effect=ValueError("不完整")))
    with pytest.raises(service.PurchaseOrderSyncError):
        service.sync_purchase_orders()
    publication.assert_not_called()
    cache.assert_not_called()


def test_history_and_cross_month_rejected(monkeypatch):
    monkeypatch.setattr(service, "now_shanghai", lambda: datetime(2026, 11, 2))
    with pytest.raises(ValueError, match="历史月份"):
        service._require_current_report("2026-09")
    monkeypatch.setattr(service.report_repo, "view_snapshot", lambda *_: {"historical_import": True})
    with pytest.raises(ValueError, match="历史导入"):
        service._require_current_report("2026-10")
    assert service.current_source_month(datetime(2027, 1, 1)) == "2026-12"


def test_transaction_defers_nested_commits_and_rolls_back_snapshot_failure(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"total": 3}
    monkeypatch.setattr(report_repo, "_database_connection", lambda: nullcontext(connection))
    monkeypatch.setattr(report_repo, "_insert_rows", lambda *_: None)
    monkeypatch.setattr(report_repo, "_apply_purchase_order_transit_to_summary", lambda *_: 2)
    with report_repo.purchase_order_transaction():
        report_repo.replace_purchase_order_transit("2026-10", [], [])
        report_repo.save_view_snapshots("2026-10", {"GROUP": {"items": []}})
        connection.commit.assert_not_called()
    connection.commit.assert_called_once()
    connection.reset_mock()
    with pytest.raises(RuntimeError):
        with report_repo.purchase_order_transaction():
            report_repo.replace_purchase_order_transit("2026-10", [], [])
            raise RuntimeError("render failed")
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    assert report_repo._report_transaction.get() is None


def test_scheduler_rejects_historical_period_before_creating_run(monkeypatch):
    from backend.services import scheduler_service as scheduler
    monkeypatch.setattr(scheduler.repo, "performance_connection", lambda: pytest.fail("must reject before DB access"))
    with pytest.raises(ValueError, match="历史"):
        scheduler.run_scheduler_task(service.TASK_CODE, stat_month="2026-09")
    spec = scheduler.TASK_SPECS[service.TASK_CODE]
    assert spec.lock_name(None) == "inventory:purchase-order-api"


def test_api_month_lock_refuses_overlapping_import_or_calculate(monkeypatch):
    from backend.services import inventory_purchase_order_job_service as jobs
    action = MagicMock()
    monkeypatch.setattr(jobs, "named_lock", lambda name: nullcontext(False))
    with pytest.raises(ValueError, match="正在同步"):
        jobs.report_write("2026-10", action)
    action.assert_not_called()


def test_repeated_submit_reuses_accepted_job(monkeypatch):
    from backend.services import inventory_purchase_order_job_service as jobs
    future = MagicMock()
    future.done.return_value = False
    monkeypatch.setattr(jobs, "_future", future)
    monkeypatch.setattr(jobs, "_request_id", "already-running")
    executor = MagicMock()
    monkeypatch.setattr(jobs, "_executor", executor)
    assert jobs.submit() == {"status": "running", "request_id": "already-running"}
    executor.submit.assert_not_called()


def test_restart_interruption_and_start_failure_are_visible(monkeypatch):
    from backend.services import inventory_purchase_order_job_service as jobs
    monkeypatch.setattr(jobs.repo, "status", lambda *_: {"running": False, "run": None})
    future = MagicMock()
    future.done.return_value = True
    future.cancelled.return_value = False
    future.exception.return_value = RuntimeError("sensitive URL and SQL")
    monkeypatch.setattr(jobs, "_future", future)
    monkeypatch.setattr(jobs, "_request_id", "failed-start")
    result = jobs.get_status("2026-10", "failed-start")
    assert result["run"]["status"] == "failed"
    assert "sensitive" not in result["run"]["error_message"]


def test_month_switch_before_publication_keeps_old_data(monkeypatch, sync_setup):
    _, publication, cache = sync_setup
    monkeypatch.setattr(service.repo, "cached_orders", lambda: {"PO-1": order()})
    monkeypatch.setattr(service, "fetch_orders", lambda *_args, **_kwargs: {})
    times = iter([datetime(2026, 11, 30, 23, 59), datetime(2026, 11, 30, 23, 59), datetime(2026, 12, 1)])
    monkeypatch.setattr(service, "now_shanghai", lambda: next(times))
    with pytest.raises(service.PurchaseOrderSyncError, match="历史月份"):
        service.sync_purchase_orders()
    publication.assert_not_called()
    cache.assert_not_called()
