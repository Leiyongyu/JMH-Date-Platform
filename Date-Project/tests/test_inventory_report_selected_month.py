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

    def clean_fba(month, rows, shops, rules):
        inventory_rules["amazon"] = rules[0][("EU", "BRAND", "BMW")]
        return [], {}

    def clean_overseas(month, rows, rules, sku_map, wids):
        inventory_rules["ebay"] = rules["BMW"]
        return [], {}

    def clean_sales(month, rows, shops, rules):
        inventory_rules["sales"] = rules[0][("EU", "BRAND", "BMW")]
        return [], {}

    monkeypatch.setattr(service, "_clean_fba", clean_fba)
    monkeypatch.setattr(service, "_clean_overseas", clean_overseas)
    monkeypatch.setattr(service, "_clean_local", lambda *args: ([], {}))
    monkeypatch.setattr(service, "_clean_amz_sales", clean_sales)
    monkeypatch.setattr(service, "_dimension_summaries", lambda *args: [])
    monkeypatch.setattr(service, "_department_summaries", lambda *args, **kwargs: [])
    monkeypatch.setattr(service.repo, "replace_clean_month", lambda *args: {
        "inserted_rows": 0, "deleted_rows": 0,
    })

    result = service.rebuild_monthly_inventory_report(source_month)

    assert result["stat_month"] == source_month
    assert inventory_rules == {
        "amazon": report_month, "ebay": report_month, "sales": source_month,
    }
    assert calls == [
        (report_month, "amazon"), (report_month, "ebay"),
        (source_month, "amazon"),
    ]
