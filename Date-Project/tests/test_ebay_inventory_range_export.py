"""Inclusive frozen-detail exports: no current data, no deduplication, no writes."""
import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.api.deps import require_internal_access
from backend.api.v1 import ebay_inventory_detail as api
from backend.repositories import ebay_inventory_pivot_repository as repo
from backend.services import ebay_inventory_detail_service as service
from backend.services import ebay_inventory_detail_export_service as exporter


def row(day, quantity="10", imported=False):
    return dict(site="德国", sku="MCD-20017-0071", brand="MCD", grade="A", owner="历史负责人",
                stat_date=day, overseas_total_quantity=Decimal(quantity),
                cycle_total_quantity=Decimal(quantity), sales_qty_30d=Decimal("2"),
                warehouse_rent_30d_cny=None, history_origin="EXCEL_IMPORT" if imported else "GENERATED")


@pytest.mark.parametrize("params", [
    {"start_date": "2026-09-01"}, {"end_date": "2026-09-29"},
    {"start_date": "", "end_date": "2026-09-29"},
    {"start_date": "2026-02-30", "end_date": "2026-09-29"},
    {"start_date": "2026-9-1", "end_date": "2026-09-29"},
    {"start_date": "2026-09-30", "end_date": "2026-09-29"},
    {"start_date": "2026-09-01", "end_date": "2026-09-29", "stat_date": "latest"},
])
def test_bad_range_rejected_before_database_or_live_calls(monkeypatch, params):
    reader = MagicMock(side_effect=AssertionError("must not query"))
    monkeypatch.setattr(repo, "read_inventory_range", reader)
    monkeypatch.setattr(service, "load_calculated_inventory", reader)
    with pytest.raises(ValueError, match="统计"):
        exporter.export_inventory(**params)
    reader.assert_not_called()


def test_export_keeps_dates_duplicates_frozen_values_and_import_nulls(monkeypatch):
    rows = [row("2026-09-29", "99"), row("2026-09-01", "3", True), row("2026-09-01", "4", True)]
    reader = MagicMock(return_value=(rows, {}, []))
    monkeypatch.setattr(repo, "read_inventory_range", reader)
    monkeypatch.setattr(service, "load_calculated_inventory", MagicMock(side_effect=AssertionError("live")))
    filename, content = exporter.export_inventory(start_date="2026-09-01", end_date="2026-09-29",
        site="英国", sku="99999", selected_keys=[{"site": "美国", "sku": "other"}], page_size=1)
    reader.assert_called_once_with("2026-09-01", "2026-09-29")
    assert filename == "库存明细持续更新-ebay-2026-09-01_至_2026-09-29.xlsx"
    with BytesIO(content) as stream:
        book = load_workbook(stream)
        values = list(book.active.values)
        cols = {key: i for i, (key, _, _) in enumerate(exporter.COLUMNS)}
        assert [r[cols["stat_date"]] for r in values[1:]] == ["2026-09-01", "2026-09-01", "2026-09-29"]
        assert [r[cols["overseas_total_quantity"]] for r in values[1:]] == [3, 4, 99]
        assert values[1][cols["warehouse_rent_30d_cny"]] == "--"
        assert values[3][cols["warehouse_rent_30d_cny"]] is None
        assert len(values) == 4
        book.close()


@pytest.mark.parametrize("filters", [
    {"start_date": "2026-09-16", "end_date": "2026-09-16"},
    {"stat_date": "2026-09-16"},
    {"stat_date": "latest"},
])
def test_filename_uses_actual_snapshot_day_without_duplicate_date_or_download_time(monkeypatch, filters):
    monkeypatch.setattr(exporter, "list_inventory", lambda **kwargs: {
        "items": [row("2026-09-16")], "metadata": {"stat_date": "2026-09-16"}})
    filename, _ = exporter.export_inventory(**filters)
    assert filename == "库存明细持续更新-ebay-2026-09-16.xlsx"


def test_empty_range_no_live_fallback(monkeypatch):
    monkeypatch.setattr(repo, "read_inventory_range", lambda *args: ([], {}, []))
    monkeypatch.setattr(service, "load_calculated_inventory", MagicMock(side_effect=AssertionError("live")))
    with pytest.raises(ValueError, match="没有可导出"):
        exporter.export_inventory(start_date="2026-09-01", end_date="2026-09-01")


def test_range_repository_inclusive_parameterized_single_snapshot(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"total": 2}
    saved = row("wrong-date")
    payload = json.dumps({"values": saved, "decimal_fields": [
        k for k, v in saved.items() if isinstance(v, Decimal)]}, default=str)
    cursor.fetchall.return_value = [
        {"stat_date": date(2026, 9, 1), "item_json": payload},
        {"stat_date": date(2026, 9, 29), "item_json": payload}]
    monkeypatch.setattr(repo, "db_connection", lambda: connection)
    rows, metadata, _ = repo.read_inventory_range("2026-09-01", "2026-09-29")
    assert [item["stat_date"] for item in rows] == ["2026-09-01", "2026-09-29"]
    assert rows[0]["overseas_total_quantity"] == Decimal("10")
    assert metadata["is_history"] is True
    for call in cursor.execute.call_args_list[1:]:
        assert "s.stat_date >= %s AND s.stat_date <= %s" in call.args[0]
        assert call.args[1] == ("2026-09-01", "2026-09-29")
        assert "DISTINCT" not in call.args[0]
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()


def test_range_limit_rejects_instead_of_silently_truncating(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"total": 200001}
    monkeypatch.setattr(repo, "db_connection", lambda: connection)
    with pytest.raises(ValueError, match="20万"):
        repo.read_inventory_range("2026-01-01", "2026-12-31")
    cursor.fetchall.assert_not_called()
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_api_accepts_range_and_rejects_invalid_range(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None
    monkeypatch.setattr(repo, "read_inventory_range", lambda *args: ([row(args[0])], {}, []))
    with TestClient(app) as client:
        path = "/api/v1/finance/ebay-inventory-detail/export"
        response = client.post(path, json={"start_date": "2026-09-01", "end_date": "2026-09-01"})
        assert response.status_code == 200
        assert response.content.startswith(b"PK")
        response = client.post(path, json={"start_date": "2026-09-29", "end_date": "2026-09-01"})
        assert response.status_code == 400
