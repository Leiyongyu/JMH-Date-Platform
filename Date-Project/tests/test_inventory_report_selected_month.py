from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.api.v1 import finance
from backend.database import (
    _ensure_inventory_report_owner_rule_month,
    _ensure_inventory_report_view_snapshot,
)
from backend.services import inventory_report_etl_service as service


def test_rebuild_replaces_only_requested_source_month(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"total": 0}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(service.repo, "db_connection", lambda: connection)
    monkeypatch.setattr(service.repo, "_insert_rows", lambda *_args: None)

    service.repo.replace_clean_month("2026-08", [], [], [], [], [], [])

    deletes = [call.args for call in cursor.execute.call_args_list
               if call.args[0].startswith("DELETE FROM")]
    assert len(deletes) == 6
    assert all(params == ("2026-08",) for _query, params in deletes)
    connection.commit.assert_called_once()


def test_manual_rebuild_preserves_sales_detail_used_by_previous_report(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"total": 0}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(service.repo, "db_connection", lambda: connection)
    monkeypatch.setattr(service.repo, "_insert_rows", lambda *_args: None)

    result = service.repo.replace_clean_month(
        "2026-09", [], [], [], [{"stat_month": "2026-09"}], [], [],
        replace_amz_sales=False,
    )

    deletes = [call.args[0] for call in cursor.execute.call_args_list
               if call.args[0].startswith("DELETE FROM")]
    assert len(deletes) == 5
    assert all("dwd_inventory_report_amz_sales_detail" not in query for query in deletes)
    assert result["amz_sales_detail_rows"] == 0
    connection.commit.assert_called_once()


def test_calculate_endpoint_requests_sales_preservation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        finance, "rebuild_monthly_inventory_report",
        lambda month, *, preserve_sales_detail: (
            calls.append((month, preserve_sales_detail)) or {"stat_month": month}
        ),
    )
    finance.post_monthly_inventory_report_rebuild(
        SimpleNamespace(stat_month="2026-09"),
        SimpleNamespace(state=SimpleNamespace(request_id="test-request")),
    )
    assert calls == [("2026-09", True)]


def test_owner_rule_month_schema_upgrade_is_additive_and_idempotent():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    _ensure_inventory_report_owner_rule_month(cursor)
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert len(statements) == 2
    assert statements[0].startswith("SHOW COLUMNS")
    assert statements[1].startswith("ALTER TABLE dws_inventory_report_dimension_summary ADD COLUMN")

    cursor.reset_mock()
    cursor.fetchone.return_value = {"Field": "owner_rule_month"}
    _ensure_inventory_report_owner_rule_month(cursor)
    assert cursor.execute.call_count == 1


def test_view_snapshot_schema_has_one_entry_per_month_and_dimension():
    cursor = MagicMock()
    _ensure_inventory_report_view_snapshot(cursor)
    statement = cursor.execute.call_args.args[0]
    assert "CREATE TABLE IF NOT EXISTS monthly_inventory_report_view_snapshot" in statement
    assert "PRIMARY KEY (stat_month, dimension_type)" in statement


def test_missing_snapshot_query_includes_latest_month(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"stat_month": "2026-08"}, {"stat_month": "2026-09"}]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(service.repo, "db_connection", lambda: connection)

    assert service.repo.missing_legacy_snapshot_months() == ["2026-08", "2026-09"]
    query = cursor.execute.call_args.args[0]
    assert "COUNT(s.dimension_type) < 3" in query
    assert "MAX(stat_month)" not in query


def test_recalculate_replaces_only_selected_month_view_snapshots(monkeypatch):
    cursor = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(service.repo, "db_connection", lambda: connection)
    payloads = {dimension: {"items": [{"value": dimension}]}
                for dimension in ("GROUP", "STORE", "OWNER")}

    service.repo.save_view_snapshots("2026-09", payloads)

    assert cursor.execute.call_count == 3
    for call in cursor.execute.call_args_list:
        query, params = call.args
        assert "ON DUPLICATE KEY UPDATE" in query
        assert params[0] == "2026-09"
        assert params[1] in payloads
    connection.commit.assert_called_once()


def test_backfill_freezes_old_and_latest_month_without_overwriting_existing(monkeypatch):
    stored = {("2026-08", "GROUP"): {"items": [{"value": "original"}]}}
    generated = []
    monkeypatch.setattr(
        service.repo, "missing_legacy_snapshot_months",
        lambda: ["2026-08", "2026-09"],
    )

    def payloads(month):
        generated.append(month)
        return {dimension: {"items": [{"value": month}]}
                for dimension in ("GROUP", "STORE", "OWNER")}

    def save(month, payloads_by_dimension, *, only_missing):
        assert only_missing
        for dimension, payload in payloads_by_dimension.items():
            stored.setdefault((month, dimension), payload)

    monkeypatch.setattr(service, "_report_view_payloads", payloads)
    monkeypatch.setattr(service.repo, "save_view_snapshots", save)
    monkeypatch.setattr(service.repo, "view_snapshot", lambda month, dim: stored.get((month, dim)))

    assert service.backfill_missing_monthly_inventory_snapshots() == 2
    assert generated == ["2026-08", "2026-09"]
    assert service.get_department_summary("2026-08")["items"][0]["value"] == "original"
    assert service.get_department_summary("2026-09")["items"][0]["value"] == "2026-09"
    assert len(stored) == 6


def test_snapshot_read_does_not_recalculate_after_live_rules_change(monkeypatch):
    snapshots = {
        ("2026-08", "OWNER"): {"items": [{"dimension_value": "原负责人"}]},
        ("2026-09", "OWNER"): {"items": [{"dimension_value": "新负责人"}]},
    }
    monkeypatch.setattr(
        service.repo, "view_snapshot",
        lambda month, dimension: snapshots.get((month, dimension)),
    )
    monkeypatch.setattr(
        service.repo, "dimension_summary",
        lambda *_args: pytest.fail("a frozen month must not query live details"),
    )
    monkeypatch.setattr(
        service.repo, "owner_rules",
        lambda *_args: pytest.fail("a frozen month must not query live rules"),
    )

    assert service.get_dimension_summary("OWNER", "2026-08") == snapshots[("2026-08", "OWNER")]
    assert service.get_dimension_summary("OWNER", "2026-09") == snapshots[("2026-09", "OWNER")]


@pytest.mark.parametrize(
    ("source_month", "report_month"),
    [("2026-09", "2026-10"), ("2026-12", "2027-01")],
)
@pytest.mark.parametrize("refresh_snapshot", [True, False])
def test_rebuild_uses_display_month_rules_for_inventory_only(
    monkeypatch, source_month, report_month, refresh_snapshot,
):
    calls = []
    sources = {name: [{}] for name in ("fba", "overseas", "local", "order_profit")}
    sources["purchase_order_transit"] = []
    monkeypatch.setattr(service.repo, "source_rows", lambda month: sources)
    monkeypatch.setattr(service, "_require_complete_sources", lambda *_: None)
    monkeypatch.setattr(service.repo, "opening_inventory_by_department", lambda _: {})
    monkeypatch.setattr(service.repo, "amazon_shop_map", lambda: {})

    def owner_rules(month, platform):
        calls.append((month, platform))
        return [{"group_code": "EU", "rule_type": "BRAND" if platform == "amazon" else "EBAY_BRAND",
                 "match_key": "BMW", "principal_name": month}]

    monkeypatch.setattr(service.repo, "owner_rules", owner_rules)
    monkeypatch.setattr(service, "_ebay_product_sku_map", lambda _: {})
    monkeypatch.setattr(service.repo, "overseas_included_wids", lambda: [1])
    inventory_rules = {}

    def clean_fba(month, rows, shops, rules, *, assignment_rules):
        inventory_rules["group"] = rules[0][("EU", "BRAND", "BMW")]
        inventory_rules["amazon"] = assignment_rules[0][("EU", "BRAND", "BMW")]
        return [], {}

    def clean_overseas(month, rows, rules, sku_map, wids):
        inventory_rules["ebay"] = rules["BMW"]
        return [], {}

    def clean_sales(month, rows, shops, rules):
        inventory_rules["sales"] = rules[0][("EU", "BRAND", "BMW")]
        return [], {}

    monkeypatch.setattr(service, "_clean_fba", clean_fba)
    monkeypatch.setattr(service, "_clean_overseas", clean_overseas)
    monkeypatch.setattr(service, "_clean_local", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(service, "_clean_amz_sales", clean_sales)
    def dimension_summaries(*args, owner_rule_month):
        inventory_rules["saved_rule_month"] = owner_rule_month
        return []

    monkeypatch.setattr(service, "_dimension_summaries", dimension_summaries)
    monkeypatch.setattr(service, "_department_summaries", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "_report_view_payloads", lambda _month: {
        "GROUP": {}, "STORE": {}, "OWNER": {},
    })
    monkeypatch.setattr(
        service.repo, "save_view_snapshots",
        lambda month, payloads, *, only_missing: inventory_rules.update(
            snapshot_month=month, snapshot_dimensions=tuple(payloads),
            snapshot_only_missing=only_missing,
        ),
    )
    def replace_clean_month(*args, replace_amz_sales):
        inventory_rules["replace_sales"] = replace_amz_sales
        return {
        "inserted_rows": 0, "deleted_rows": 0,
        }

    monkeypatch.setattr(service.repo, "replace_clean_month", replace_clean_month)

    result = service.rebuild_monthly_inventory_report(
        source_month, refresh_view_snapshot=refresh_snapshot,
    )

    assert result["stat_month"] == source_month
    assert inventory_rules == {
        "group": source_month, "amazon": report_month,
        "ebay": report_month, "sales": source_month,
        "saved_rule_month": report_month, "replace_sales": True,
        "snapshot_month": source_month,
        "snapshot_dimensions": ("GROUP", "STORE", "OWNER"),
        "snapshot_only_missing": not refresh_snapshot,
    }
    assert calls == [
        (source_month, "amazon"), (report_month, "amazon"),
        (report_month, "ebay"),
    ]


def test_owner_change_does_not_change_fba_group_or_store_summary():
    source_rules = service._amazon_rule_maps([{
        "group_code": "US1", "rule_type": "STORE",
        "match_key": "无前缀店铺", "principal_name": "原负责人",
    }])
    report_rules = service._amazon_rule_maps([{
        "group_code": "US2", "rule_type": "STORE",
        "match_key": "无前缀店铺", "principal_name": "新负责人",
    }])
    source = [{
        "id": 1, "sync_batch_id": "batch-1", "sid": "99999",
        "msku": "SKU-001", "end_count": 3, "end_total_amount": 30,
    }]
    shops = {"99999": "无前缀店铺"}
    old_rows, _ = service._clean_fba("2026-09", source, shops, source_rules)
    new_rows, _ = service._clean_fba(
        "2026-09", source, shops, source_rules, assignment_rules=report_rules,
    )
    assert old_rows[0]["department_code"] == new_rows[0]["department_code"] == "AMZ-US1"
    assert old_rows[0]["principal_name"] == "原负责人"
    assert new_rows[0]["principal_name"] == "新负责人"

    def summaries(rows):
        dimensions = service._dimension_summaries(
            "2026-09", rows, [], [], [], source_rules, {},
        )
        groups = service._department_summaries("2026-09", rows, [], [])
        stores = [row for row in dimensions if row["dimension_type"] == "STORE"]
        owners = [row for row in dimensions if row["dimension_type"] == "OWNER"]
        return stores, groups, owners

    old_stores, old_groups, old_owners = summaries(old_rows)
    new_stores, new_groups, new_owners = summaries(new_rows)
    assert old_stores == new_stores
    assert old_groups == new_groups
    assert old_owners != new_owners


def test_owner_change_keeps_special_local_warehouse_group():
    source_rules = service._amazon_rule_maps([{
        "group_code": "US1", "rule_type": "STORE",
        "match_key": "无前缀店铺", "principal_name": "原负责人",
    }])
    report_rules = service._amazon_rule_maps([{
        "group_code": "US2", "rule_type": "STORE",
        "match_key": "无前缀店铺", "principal_name": "新负责人",
    }])
    source = [{
        "id": 1, "sync_batch_id": "batch-1", "sys_wid": "18680",
        "seller_name": "无前缀店铺", "sku": "SKU-001", "day_end_count": 3,
    }]
    old_rows, _ = service._clean_local("2026-09", source, source_rules, {})
    new_rows, _ = service._clean_local(
        "2026-09", source, source_rules, {}, assignment_rules=report_rules,
    )
    assert old_rows[0]["department_code"] == new_rows[0]["department_code"] == "AMZ-US1-ZXY"
    assert old_rows[0]["principal_name"] == "原负责人"
    assert new_rows[0]["principal_name"] == "新负责人"
