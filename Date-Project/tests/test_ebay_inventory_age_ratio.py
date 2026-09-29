from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock
import json

import pytest

from backend.services import ebay_inventory_age_ratio_service as service
from backend.services.clearance_service import _ebay_inventory_age_rows
from backend.repositories import clearance_repository as costs
from backend.repositories import ebay_inventory_age_ratio_repository as repository
from test_ebay_inventory_pivot_api_export import client
from backend.api.v1 import ebay_inventory_detail as api


def source(**overrides):
    return dict(source_inventory_age_id=1, source_goodcang_batch_id="batch-1",
                source_product_batch_id="product-1", source_product_sku="JMH-00123-0001",
                sku="BMW-00123-0001", sku_middle="00123-0001", cg_price="10", step_price="12",
                first_leg_cost="3", inventory_quantity=4, warehouse_age_days=90,
                warehouse_code="DE", source_pulled_at=datetime(2026, 9, 29, 6),
                candidate_count=1, non_jmh_count=1, pull_month="2026-09", **overrides)


def make_source(**overrides):
    row = source()
    row.update(overrides)
    return row


def product(**overrides):
    row = {"sku": "BMW-00123-0001", "cg_price": "10", "step_price": "12",
           "transport_costs": {"DE": "3", "UK": "4"}, "source_product_batch_id": "product-1"}
    row.update(overrides)
    return row


def cleaned(*rows):
    return _ebay_inventory_age_rows("2026-09", "test", datetime(2026, 9, 29), list(rows))[0]


@pytest.mark.parametrize("age,bucket", [(0, 0), (89, 0), (90, 1), (119, 1), (120, 2),
                                       (179, 2), (180, 2), (181, 3), (999, 3), (-1, None), (None, None)])
def test_exact_boundaries(age, bucket):
    assert service.age_bucket(age) == (service.BUCKETS[bucket] if bucket is not None else None)


def test_quantity_times_clearance_unit_cost_and_owner_site_totals_reconcile():
    rows = cleaned(*(make_source(warehouse_age_days=age, inventory_quantity=i + 1,
                                 warehouse_code="DE" if i < 2 else "CZ")
                     for i, age in enumerate([89, 90, 120, 181])))
    # Existing clearance remains unit-cost only.
    assert all(r["inventory_age_cost"] == Decimal(15) for r in rows)
    data = service.aggregate(rows, {"BMW": "张三"}, {}, "2026-09-29")
    owner, site = data["owners"][0], data["sites"][0]
    assert owner["name"] == "张三" and site["name"] == "德国"
    assert owner["total_value"] == site["total_value"] == "150.000000"
    assert [owner[b + "_value"] for b in service.BUCKETS] == ["15.000000", "30.000000", "45.000000", "60.000000"]
    assert sum(Decimal(owner[b + "_ratio"]) for b in service.BUCKETS) == 1


def test_missing_cost_and_unknown_owner_are_not_silently_dropped_or_zero_filled():
    rows = cleaned(make_source(first_leg_cost=None), make_source(sku="XYZ-00123-0001"),
                   make_source(sku="ABC-00123-0001", warehouse_age_days=None),
                   make_source(sku="NEG-00123-0001", inventory_quantity=-1))
    data = service.aggregate(rows, {"BMW": "张三"}, {}, "2026-09-29")
    assert data["excluded_rows"] == 3 and data["valued_rows"] == 1
    assert next(r for r in data["owners"] if r["name"] == "张三")["total_value"] is None
    assert next(r for r in data["owners"] if r["name"] == "未分配")["total_value"] == "60.000000"
    assert data["sites"][0]["total_value"] == "60.000000"


def test_zero_total_has_undefined_ratios_and_fixed_performance_owners():
    rows = cleaned(make_source(sku="FLL-1", inventory_quantity=0), make_source(sku="CL-1", inventory_quantity=0))
    data = service.aggregate(rows, {}, {}, "2026-09-29")
    assert {r["name"] for r in data["owners"]} == {"方黎力", "陈丽"}
    assert all(r["total_value"] == "0.000000" for r in data["owners"])
    assert all(r[b + "_ratio"] is None for r in data["owners"] for b in service.BUCKETS)


def test_snapshot_uses_current_rules_latest_source_and_persists_both_dimensions(monkeypatch):
    @contextmanager
    def lock(_):
        yield True
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 29, 12, tzinfo=tz)
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "named_lock", lock)
    query = MagicMock(return_value=([source()], [product()]))
    rules = MagicMock(return_value=[{"rule_type": "EBAY_BRAND", "match_key": "BMW", "principal_name": "张三"}])
    sku_map = MagicMock(return_value={})
    save = MagicMock()
    monkeypatch.setattr(service.repository, "load_source", query)
    monkeypatch.setattr(service.owners, "owner_rules", rules)
    monkeypatch.setattr(service, "_ebay_product_sku_map", sku_map)
    monkeypatch.setattr(service.repository, "save_snapshot", save)
    data = service.capture_snapshot()
    query.assert_called_once_with("2026-09")
    rules.assert_called_once_with("2026-09", "ebay")
    sku_map.assert_called_once_with("2026-09", include_next=False)
    save.assert_called_once_with(data)
    assert data["stat_date"] == "2026-09-29" and data["owners"] and data["sites"]
    assert data["source_pulled_at"] == "2026-09-29 06:00:00"
    query.return_value = ([source(), make_source(source_goodcang_batch_id="mixed")], [product()])
    with pytest.raises(ValueError, match="批次"):
        service.capture_snapshot()
    assert save.call_count == 1
    query.return_value = ([source()], [product(transport_costs={})])
    with pytest.raises(ValueError, match="没有可计算"):
        service.capture_snapshot()
    assert save.call_count == 1


@pytest.mark.parametrize("suffix", ["-YXR", "-RXY", "-YXQ", "-GWC", "-YXQ-2", "-OTHER", ""])
def test_middle_code_matches_variants_to_normal_product(suffix):
    raw = make_source(source_product_sku="JMH-110147-0740" + suffix)
    catalog = [product(sku="LR-110147-0740"), product(sku="LR-110147-0740-YXR", step_price=None, cg_price="0")]
    matched = service.match_middle_code([raw], catalog, {"LR": "张三"}, {})
    assert len(matched) == 1
    assert matched[0]["sku"] == "LR-110147-0740"
    assert matched[0]["sku_middle"] == "110147-0740"
    assert matched[0]["middle_match_error"] is None
    row = service.clean_matched_rows("2026-09", datetime(2026, 9, 29), matched)[0]
    assert row["match_status"] == "MATCHED" and row["unit_landed_cost"] == Decimal(15)
    assert row["inventory_quantity"] == 4 and row["matched_owner"] == "张三"


def test_equal_normal_candidates_count_inventory_once_and_different_prices_use_highest():
    catalog = [product(), product(sku="LR-00123-0001")]
    raw = [source(), make_source(source_inventory_age_id=2)]
    matched = service.match_middle_code(raw, catalog, {"BMW": "张三", "LR": "张三"}, {})
    data = service.aggregate(service.clean_matched_rows("2026-09", datetime(2026, 9, 29), matched), {}, {}, "2026-09-29")
    assert data["source_rows"] == data["valued_rows"] == 2
    assert data["owners"][0]["total_value"] == "120.000000"
    catalog[1]["step_price"] = "18"
    matched = service.match_middle_code(raw, catalog, {"BMW": "张三", "LR": "张三"}, {})
    assert all(r["middle_match_error"] is None and r["sku"] == "LR-00123-0001" for r in matched)
    data = service.aggregate(service.clean_matched_rows("2026-09", datetime(2026, 9, 29), matched), {}, {}, "2026-09-29")
    assert data["valued_rows"] == 2 and data["excluded_rows"] == 0
    assert data["owners"][0]["total_value"] == "168.000000"


def test_highest_cost_is_country_specific_and_never_combines_components_across_skus():
    catalog = [product(), product(sku="LR-00123-0001", transport_costs={"DE": "3", "UK": "5"})]
    matched = service.match_middle_code([source(), make_source(warehouse_code="UK")], catalog, {"BMW": "张三", "LR": "张三"}, {})
    assert matched[0]["middle_match_error"] is None
    assert matched[1]["middle_match_error"] is None
    assert matched[1]["sku"] == "LR-00123-0001"
    assert matched[1]["first_leg_cost"] == "5"
    catalog[1].update(step_price="11", transport_costs={"DE": "4"})
    tied = service.match_middle_code([source()], catalog, {}, {})[0]
    assert tied["middle_match_error"] is None
    assert (tied["step_price"], tied["first_leg_cost"]) in {("12", "3"), ("11", "4")}
    catalog[1].update(step_price="5", transport_costs={"DE": "20"})
    highest = service.match_middle_code([source()], catalog, {}, {})[0]
    assert highest["step_price"] == "5" and highest["first_leg_cost"] == "20"


def test_highest_candidate_requires_both_valid_costs_and_owner_follows_winner():
    catalog = [product(), product(sku="LR-00123-0001", step_price="100", transport_costs={})]
    chosen = service.match_middle_code([source()], catalog, {"BMW": "甲", "LR": "乙"}, {})[0]
    assert chosen["sku"] == "BMW-00123-0001" and chosen["matched_owner"] == "甲"
    catalog[1]["transport_costs"] = {"DE": "1"}
    chosen = service.match_middle_code([source()], catalog, {"BMW": "甲", "LR": "乙"}, {})[0]
    assert chosen["sku"] == "LR-00123-0001" and chosen["matched_owner"] == "乙"
    catalog[0]["transport_costs"] = {}
    catalog[1]["transport_costs"] = {"DE": "-1"}
    assert service.match_middle_code([source()], catalog, {}, {})[0]["middle_match_error"] == "COST_NOT_FOUND"


def test_different_owners_are_not_assigned_arbitrarily_even_when_costs_agree():
    matched = service.match_middle_code([source()], [product(), product(sku="LR-00123-0001")],
                                       {"BMW": "甲", "LR": "乙"}, {})
    assert matched[0]["middle_match_error"] == "OWNER_AMBIGUOUS"
    assert matched[0]["matched_owner"] == "未分配"


def test_normal_precedes_used_and_used_only_is_fallback_not_forced_zero():
    catalog = [product(sku="JMH-00123-0001"), product(sku="BMW-00123-0001-RXY", cg_price="0", step_price=None)]
    matched = service.match_middle_code([source()], catalog, {"BMW": "张三"}, {"00123-0001": "BMW-00123-0001"})
    assert matched[0]["sku"] == "JMH-00123-0001" and matched[0]["step_price"] == "12"
    matched = service.match_middle_code([source()], [product(sku="BMW-00123-0001-YXR")], {"BMW": "张三"}, {})
    assert matched[0]["middle_match_error"] is None
    assert matched[0]["sku"] == "BMW-00123-0001-YXR"


def test_leading_zero_middle_codes_are_textual_and_invalid_codes_do_not_merge():
    raw = [source(), make_source(source_product_sku="JMH-123-0001"), make_source(source_product_sku="JMH--0001")]
    matched = service.match_middle_code(raw, [product()], {}, {})
    assert [r["middle_match_error"] for r in matched] == [None, "PRODUCT_NOT_FOUND", "INVALID_MIDDLE_CODE"]


def test_alphanumeric_middle_codes_are_preserved_without_stripping_letters():
    raw = [make_source(source_product_sku="JMH-30243C-0056-YXR"), make_source(source_product_sku="JMH-30243-0056")]
    matched = service.match_middle_code(raw, [product(sku="BMW-30243C-0056")], {}, {})
    assert matched[0]["sku_middle"] == "30243C-0056" and matched[0]["middle_match_error"] is None
    assert matched[1]["middle_match_error"] == "PRODUCT_NOT_FOUND"


def test_screenshot_variants_use_base_product_but_never_other_supplier():
    suffixes = ["", "-YXQ", "-GWC", "-YXQ-2", "-YXR"]
    raw = [make_source(source_product_sku="JMH-70013-0082" + suffix) for suffix in suffixes]
    catalog = [product(sku="FRD-70013-0082", cg_price="375", step_price=None)]
    # Even an expensive suffixed record cannot override the preferred base SKU.
    catalog += [product(sku="FRD-70013-0082" + suffix, cg_price="999", step_price=None)
                for suffix in suffixes[1:]]
    catalog += [product(sku="FRD-70013-0099", cg_price="9999", step_price=None)]
    matched = service.match_middle_code(raw, catalog, {"FRD": "张三"}, {})
    assert len(matched) == len(raw)
    assert all(r["sku_middle"] == "70013-0082" and r["sku"] == "FRD-70013-0082" for r in matched)
    assert all(r["cg_price"] == "375" for r in matched)
    assert all(len(r["candidate_details"]) == 1 for r in matched)
    other = service.match_middle_code([make_source(source_product_sku="JMH-70013-0083-YXR")], catalog, {}, {})[0]
    assert other["middle_match_error"] == "PRODUCT_NOT_FOUND"


@pytest.mark.parametrize("sku,key", [("FRD-70013-0082-YXQ-2", "70013-0082"),
                                     ("JMH-00123-0001", "00123-0001"),
                                     ("JMH-00123-1", "00123-1"),
                                     ("JMH-00123", None), ("JMH-00123--YXR", None)])
def test_core_and_supplier_are_exact_textual_segments(sku, key):
    assert service.product_middle_code(sku) == key


def test_source_loader_reads_catalog_and_inventory_consistently_without_row_multiplication(monkeypatch):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [[source()], [product()], [{"sku": "BMW-00123-0001", "country_code": "DE", "transport_cost": Decimal(3)}]]
    monkeypatch.setattr(repository, "db_connection", lambda: conn)
    inventory, products = repository.load_source("2026-09")
    assert len(inventory) == len(products) == 1
    assert products[0]["transport_costs"] == {"DE": Decimal(3)}
    calls = cur.execute.call_args_list
    assert "REPEATABLE READ" in calls[0].args[0]
    assert "ods_goodcang_inventory_age_latest" in calls[1].args[0]
    assert calls[2].args[1] == ("2026-09", "2026-09")
    assert calls[3].args[1] == ("2026-09",)
    conn.begin.assert_called_once()
    conn.commit.assert_called_once()


@pytest.mark.parametrize("day", ["2026-9-1", "2026-02-30", "bad"])
def test_invalid_date_never_queries_database(monkeypatch, day):
    query = MagicMock()
    monkeypatch.setattr(service.repository, "read_snapshot", query)
    with pytest.raises(ValueError, match="统计日期"):
        service.read_snapshot(day)
    query.assert_not_called()


@pytest.mark.parametrize("latest", [False, True])
def test_source_sql_preserves_monthly_default_and_uses_current_cost_month_for_latest(monkeypatch, latest):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(costs, "db_connection", lambda: conn)
    costs.ebay_inventory_age_source_rows("2026-09", latest=latest)
    sql, args = cur.execute.call_args.args
    assert ("ods_goodcang_inventory_age_latest" if latest else "ods_goodcang_inventory_age_monthly") in sql
    assert args == ("2026-09",) * 4
    assert ("p.snapshot_month=g.snapshot_month" in sql) == (not latest)


def test_snapshot_write_is_atomic_and_rolls_back_on_failure(monkeypatch):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(repository, "db_connection", lambda: conn)
    data = {"stat_date": "2026-09-29", "generated_at": "2026-09-29 12:00:00", "source_batch_id": "b",
            "owners": [], "sites": []}
    repository.save_snapshot(data)
    conn.commit.assert_called_once()
    assert "ON DUPLICATE KEY UPDATE" in cur.execute.call_args.args[0]
    cur.execute.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError):
        repository.save_snapshot(data)
    conn.rollback.assert_called_once()
    assert conn.commit.call_count == 1


def test_api_read_and_refresh_ignore_client_dates_and_amounts(client, monkeypatch):
    read = MagicMock(return_value={"owners": [], "sites": []})
    capture = MagicMock(return_value={"stat_date": "2026-09-29"})
    monkeypatch.setattr(api.age_ratio_service, "read_snapshot", read)
    monkeypatch.setattr(api.age_ratio_service, "capture_snapshot", capture)
    assert client.get('/api/v1/finance/ebay-inventory-detail/age-ratio?stat_date=2026-09-01').status_code == 200
    read.assert_called_once_with("2026-09-01")
    response = client.post('/api/v1/finance/ebay-inventory-detail/age-ratio/recalculate',
                           json={"stat_date": "2020-01-01", "total_value": 999})
    assert response.status_code == 200 and response.json()["data"]["stat_date"] == "2026-09-29"
    capture.assert_called_once_with()
    assert client.get('/api/v1/finance/ebay-inventory-detail/age-ratio/recalculate').status_code == 405


def test_historical_read_is_frozen_and_missing_day_never_falls_back(monkeypatch):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [{"stat_date": "2026-09-29"}, {"stat_date": "2026-09-28"}]
    frozen = {"stat_date": "2026-09-28", "owners": [{"name": "旧负责人", "total_value": "12"}], "sites": []}
    cur.fetchone.return_value = {"report_json": json.dumps(frozen)}
    monkeypatch.setattr(repository, "db_connection", lambda: conn)
    assert repository.read_snapshot("2026-09-28")["owners"][0]["name"] == "旧负责人"
    assert cur.execute.call_args.args[1] == ("2026-09-28",)
    cur.fetchone.return_value = None
    assert repository.read_snapshot("2020-01-01")["owners"] == []
    assert cur.execute.call_args.args[1] == ("2020-01-01",)
    assert all("ebay_inventory_age_ratio_snapshot" in call.args[0] for call in cur.execute.call_args_list)


def test_range_reads_only_frozen_snapshots_without_merging_days(monkeypatch):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [
        {"stat_date": day, "report_json": json.dumps({"owners": [{"name": "甲", "total_value": amount}],
          "sites": [{"name": "德国", "total_value": amount}]})}
        for day, amount in [("2026-09-29", "20"), ("2026-09-28", "12")]
    ]
    monkeypatch.setattr(repository, "db_connection", lambda: conn)
    report = service.read_range("2026-09-28", "2026-09-29")
    assert report["snapshot_dates"] == ["2026-09-29", "2026-09-28"]
    assert [row["total_value"] for row in report["owners"]] == ["20", "12"]
    assert [row["stat_date"] for row in report["sites"]] == report["snapshot_dates"]
    sql, args = cur.execute.call_args.args
    assert "BETWEEN %s AND %s" in sql and "ORDER BY stat_date DESC" in sql
    assert args == ("2026-09-28", "2026-09-29")
    assert cur.execute.call_count == 1
    conn.commit.assert_not_called()
    cur.fetchall.return_value = []
    assert service.read_range("2020-01-01", "2020-01-31")["owners"] == []


@pytest.mark.parametrize("start,end", [(None, "2026-09-29"), ("2026-09-29", None),
    ("2026-09-30", "2026-09-29"), ("2026-02-30", "2026-09-29"), ("20260901", "2026-09-29")])
def test_range_rejects_invalid_dates_without_database_access(monkeypatch, start, end):
    read = MagicMock()
    monkeypatch.setattr(repository, "read_range", read)
    with pytest.raises(ValueError):
        service.read_range(start, end)
    read.assert_not_called()


def test_range_api_forwards_dates(client, monkeypatch):
    read = MagicMock(return_value={"owners": [], "sites": [], "snapshot_dates": []})
    monkeypatch.setattr(service, "read_range", read)
    assert client.get('/api/v1/finance/ebay-inventory-detail/age-ratio?start_date=2026-09-01&end_date=2026-09-29').status_code == 200
    read.assert_called_once_with("2026-09-01", "2026-09-29")


def test_age_ratio_api_requires_internal_access(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(api.router)
    capture = MagicMock()
    monkeypatch.setattr(api.age_ratio_service, "capture_snapshot", capture)
    with TestClient(app) as client:
        assert client.post('/api/v1/finance/ebay-inventory-detail/age-ratio/recalculate').status_code in (401, 403)
    capture.assert_not_called()
