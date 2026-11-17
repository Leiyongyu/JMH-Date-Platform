"""Frozen detail history: no upstream calls, no current-owner or price recalculation."""
import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.repositories import ebay_inventory_pivot_repository as repo
from backend.services import ebay_inventory_detail_service as service


def frozen(sku="MCD-20017-0071", quantity="10"):
    return dict(site="德国", sku=sku, sku_middle_code="20017", brand="MCD", grade="A",
                owner="旧负责人", overseas_total_quantity=Decimal(quantity),
                cycle_total_quantity=Decimal(quantity), sales_qty_30d=Decimal("2"),
                warehouse_rent_30d_cny=None, stat_date="2026-09-15")


def forbid_live(monkeypatch):
    loader = MagicMock(side_effect=AssertionError("must not read live data"))
    monkeypatch.setattr(service, "load_calculated_inventory", loader)
    return loader


def test_history_filters_numeric_sort_paging_and_selection_use_only_frozen_rows(monkeypatch):
    forbid_live(monkeypatch)
    reader = MagicMock(side_effect=lambda day: (
        [frozen("MCD-20017-0071", "2"), frozen("MCD-00123-0071", "10")],
        {"stat_date": day, "available_dates": [day]}, []))
    monkeypatch.setattr(service.history_repository, "read_inventory_day", reader)
    result = service.list_inventory(stat_date="2026-09-15", site="德国", brand="MCD",
                                    sort_field="cycle_total_quantity", page_size=1)
    assert result["pagination"]["total"] == 2
    assert result["items"][0]["cycle_total_quantity"] == "10"  # numeric, not string sort
    assert result["items"][0]["owner"] == "旧负责人"
    exported = service.list_inventory(stat_date="2026-09-15", paginate=False,
        selected_keys=[{"site": "德国", "sku": "MCD-20017-0071"}])
    assert len(exported["items"]) == 1
    assert exported["items"][0]["stat_date"] == "2026-09-15"
    assert exported["items"][0]["warehouse_rent_30d_cny"] is None


@pytest.mark.parametrize("day", ["2026-9-1", "2026-02-30", "2026-09-15 OR 1=1"])
def test_invalid_date_never_reads_database(monkeypatch, day):
    forbid_live(monkeypatch)
    reader = MagicMock()
    monkeypatch.setattr(service.history_repository, "read_inventory_day", reader)
    with pytest.raises(ValueError, match="统计日期"):
        service.list_inventory(stat_date=day)
    reader.assert_not_called()


def test_date_without_saved_details_stays_empty_never_falls_back(monkeypatch):
    forbid_live(monkeypatch)
    monkeypatch.setattr(service.history_repository, "read_inventory_day",
                        lambda day: ([], {"stat_date": day, "available_dates": []}, []))
    result = service.list_inventory(stat_date="2026-09-14")
    assert result["items"] == []
    assert result["pagination"]["total"] == 0


@pytest.mark.parametrize("selection", ["latest", "2026-09-15"])
def test_repository_reads_header_and_decimal_json_in_one_transaction(monkeypatch, selection):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    saved = frozen()
    saved["sku_middle_code"] = "00123"
    saved["sku_aliases"] = [saved["sku"], saved["sku"] + "-YXQ"]
    saved["merged_sku_count"] = 2
    saved["missing_price_sku_count"] = 1
    numeric = [key for key, value in saved.items() if isinstance(value, Decimal)]
    cursor.fetchall.side_effect = [
        [{"stat_date": date(2026, 9, 15)}],
        [{"item_json": json.dumps({"values": saved, "decimal_fields": numeric}, default=str)}],
    ]
    cursor.fetchone.return_value = {
        "id": 3, "generated_at": datetime(2026, 9, 15, 7, 30),
        "metadata_json": '{"warnings": ["历史缺价"], "owner_rule_month": "2026-09"}',
    }
    monkeypatch.setattr(repo, "db_connection", lambda: connection)
    rows, meta, warnings = repo.read_inventory_day(selection)
    assert rows[0]["overseas_total_quantity"] == Decimal("10")
    assert isinstance(rows[0]["overseas_total_quantity"], Decimal)
    assert rows[0]["sku_middle_code"] == "00123"  # identifiers are never converted to numbers
    assert rows[0]["sku_aliases"] == saved["sku_aliases"]
    assert rows[0]["merged_sku_count"] == 2
    assert rows[0]["missing_price_sku_count"] == 1
    assert meta["stat_date"] == "2026-09-15"
    assert warnings == ["历史缺价"]
    queries = cursor.execute.call_args_list
    assert "REPEATABLE READ" in queries[0].args[0]
    assert queries[2].args[1] == ("2026-09-15",)
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()


def test_frozen_read_failure_rolls_back(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = RuntimeError("read failed")
    monkeypatch.setattr(repo, "db_connection", lambda: connection)
    with pytest.raises(RuntimeError):
        repo.read_inventory_day("latest")
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
