from unittest.mock import MagicMock

import pytest

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


@pytest.mark.parametrize(
    ("source_month", "report_month"),
    [("2026-09", "2026-10"), ("2026-12", "2027-01")],
)
def test_rebuild_uses_display_month_rules_for_inventory_only(
    monkeypatch, source_month, report_month,
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
    monkeypatch.setattr(service, "_dimension_summaries", lambda *args: [])
    monkeypatch.setattr(service, "_department_summaries", lambda *args, **kwargs: [])
    monkeypatch.setattr(service.repo, "replace_clean_month", lambda *args: {
        "inserted_rows": 0, "deleted_rows": 0,
    })

    result = service.rebuild_monthly_inventory_report(source_month)

    assert result["stat_month"] == source_month
    assert inventory_rules == {
        "group": source_month, "amazon": report_month,
        "ebay": report_month, "sales": source_month,
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
