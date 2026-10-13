from decimal import Decimal

from backend.services import inventory_report_etl_service as service


def _metrics(inventory_qty, inventory_cost, transit_qty, transit_cost):
    return {
        "end_inventory_qty": Decimal(str(inventory_qty)),
        "end_inventory_total_cost": Decimal(str(inventory_cost)),
        "end_in_transit_qty": Decimal(str(transit_qty)),
        "end_in_transit_total_cost": Decimal(str(transit_cost)),
    }


def test_dimension_summaries_build_store_and_owner_with_consistent_local_transit():
    fba = [{
        "store_name": "US1-示例店铺-CA",
        "principal_name": "负责人甲",
        "department_code": "AMZ-US1",
        **_metrics(10, 100, 2, 20),
    }]
    overseas = [{
        "platform_code": "EBAY",
        "principal_name": "负责人乙",
        "department_code": "EBAY-1",
        **_metrics(3, 30, 1, 10),
    }]
    local = [
        {
            "platform_code": "AMZ",
            "seller_name": "US1-示例店铺-US",
            "principal_name": "负责人甲",
            "department_code": "AMZ-US1",
            **_metrics(5, 50, 999, 999),
        },
        {
            "platform_code": "EBAY",
            "seller_name": "不应生成的eBay店铺",
            "principal_name": "负责人乙",
            "department_code": "EBAY-1",
            **_metrics(7, 70, 999, 999),
        },
    ]
    purchase_transit = [
        {
            "platform_code": "AMZ", "store_name": "US1-示例店铺-US",
            "sku": "ABC-001", "department_code": "AMZ-US1",
            "pending_arrival_qty": Decimal("4"),
            "sku_pending_total_cost": Decimal("40"),
        },
        {
            "platform_code": "EBAY", "sku": "BMW-123-001",
            "department_code": "EBAY-1",
            "pending_arrival_qty": Decimal("6"),
            "sku_pending_total_cost": Decimal("60"),
        },
    ]
    amazon_rules = service._amazon_rule_maps([{
        "group_code": "US1",
        "rule_type": "STORE",
        "match_key": "示例店铺",
        "principal_name": "负责人甲",
    }])

    rows = service._dimension_summaries(
        "2026-07",
        fba,
        overseas,
        local,
        purchase_transit,
        amazon_rules,
        {"BMW": "负责人乙"},
    )

    assert {row["dimension_type"] for row in rows} == {"STORE", "OWNER"}
    assert not any(
        row["dimension_type"] == "STORE" and row["platform_code"] == "EBAY"
        for row in rows
    )
    fba_store = next(
        row for row in rows
        if row["source_type"] == "FBA"
        and row["dimension_type"] == "STORE"
        and row["dimension_value"] == "示例店铺"
    )
    assert fba_store["end_inventory_qty"] == Decimal("10")
    assert fba_store["end_inventory_total_cost"] == Decimal("100")
    assert fba_store["end_in_transit_qty"] == Decimal("2")
    assert fba_store["end_in_transit_total_cost"] == Decimal("20")
    assert not any(
        row["dimension_type"] == "STORE" and row["source_type"] == "LOCAL"
        for row in rows
    )
    assert not any(row["source_type"] in {"LOCAL", "LOCAL_PO"}
                   and row["department_code"] == "AMZ-US1" for row in rows)
    local_owner = next(row for row in rows if row["source_type"] == "LOCAL"
                       and row["platform_code"] == "EBAY")
    purchase_owner = next(row for row in rows if row["source_type"] == "LOCAL_PO")
    assert local_owner["dimension_value"] == purchase_owner["dimension_value"] == "负责人乙"
    assert local_owner["end_inventory_qty"] == Decimal("7")
    assert local_owner["end_in_transit_qty"] == Decimal("0")
    assert purchase_owner["end_inventory_qty"] == Decimal("0")
    assert purchase_owner["end_in_transit_qty"] == Decimal("6")


def test_us_local_remains_in_group_but_not_in_owner_dimension():
    local = [
        {"platform_code": "AMZ", "principal_name": "负责人甲",
         "department_code": "AMZ-US2-MJ", **_metrics(2, 20, 0, 0)},
        {"platform_code": "AMZ", "principal_name": service.UNASSIGNED,
         "department_code": "AMZ-US1-ZXY", **_metrics(3, 30, 0, 0)},
    ]
    purchases = [
        {"platform_code": "AMZ", "group_code": "US3",
         "department_code": "AMZ-US2-MJ", "store_name": "US3-新志楠-US",
         "sku": "A-1", "pending_arrival_qty": Decimal("4"),
         "sku_pending_total_cost": Decimal("40")},
    ]
    dimensions = service._dimension_summaries(
        "2026-09", [], [], local, purchases,
        service._amazon_rule_maps([]), {}, owner_rule_month="2026-10",
    )
    groups = service._department_summaries(
        "2026-09", [], [], local, purchases,
    )
    assert dimensions == []
    mj = next(row for row in groups if row["department_code"] == "AMZ-US2-MJ")
    zxy = next(row for row in groups if row["department_code"] == "AMZ-US1-ZXY")
    assert mj["local_end_inventory_qty"] == Decimal("2")
    assert zxy["local_end_inventory_qty"] == Decimal("3")
    assert mj["local_end_in_transit_qty"] == Decimal("4")
    assert zxy["local_end_in_transit_qty"] == Decimal("0")


def test_eu_local_inventory_and_purchase_reconcile_including_unassigned():
    rules = service._amazon_rule_maps([{
        "group_code": "EU", "rule_type": "BRAND", "match_key": "BMW",
        "principal_name": "负责人甲",
    }])
    local = [
        {"platform_code": "AMZ", "principal_name": "负责人甲",
         "department_code": "AMZ-EU", **_metrics(2, 20, 0, 0)},
        {"platform_code": "AMZ", "principal_name": service.UNASSIGNED,
         "department_code": "AMZ-EU", **_metrics(3, 30, 0, 0)},
    ]
    purchases = [
        {"platform_code": "AMZ", "group_code": "EU",
         "department_code": "AMZ-EU", "store_name": None,
         "sku": "BMW-123-001", "pending_arrival_qty": Decimal("4"),
         "sku_pending_total_cost": Decimal("40")},
    ]
    dimensions = service._dimension_summaries(
        "2026-09", [], [], local, purchases, rules, {},
    )
    group = next(row for row in service._department_summaries(
        "2026-09", [], [], local, purchases,
    ) if row["department_code"] == "AMZ-EU")
    assert sum((row["end_inventory_qty"] for row in dimensions
                if row["source_type"] == "LOCAL"), Decimal("0")) == group["local_end_inventory_qty"]
    assert sum((row["end_inventory_total_cost"] for row in dimensions
                if row["source_type"] == "LOCAL"), Decimal("0")) == group["local_end_inventory_total_cost"]
    assert sum((row["end_in_transit_qty"] for row in dimensions
                if row["source_type"] == "LOCAL_PO"), Decimal("0")) == group["local_end_in_transit_qty"]
    assert sum((row["end_in_transit_total_cost"] for row in dimensions
                if row["source_type"] == "LOCAL_PO"), Decimal("0")) == group["local_end_in_transit_total_cost"]
    assert any(row["dimension_value"] == service.UNASSIGNED for row in dimensions)


def test_missing_amazon_store_only_uses_known_eu_brand_rule():
    rules = service._amazon_rule_maps([{
        "group_code": "EU", "rule_type": "BRAND", "match_key": "BMW",
        "principal_name": "负责人甲",
    }])
    assert service._amazon_local_assignment("", "BMW-123-001", "EU", rules)[:2] == (
        "负责人甲", "EU_BRAND_FROM_WAREHOUSE",
    )
    assert service._amazon_local_assignment("", "BMW-123-001", "US1", rules)[0] == service.UNASSIGNED
    assert service._amazon_local_assignment("", "UNKNOWN-123-001", "EU", rules)[1] == "EU_BRAND_UNMATCHED_FROM_WAREHOUSE"


def test_purchase_upload_refreshes_only_selected_group_and_owner_snapshots(monkeypatch):
    calls = []
    parsed = {
        "stat_month": "2026-08", "rows": [], "batch_id": "batch",
        "source_rows": 0, "skipped_rows": 0,
        "total_pending_arrival_qty": Decimal("0"),
        "total_pending_cost": Decimal("0"),
    }
    monkeypatch.setattr(service, "parse_inventory_report_purchase_order_excel",
                        lambda *_: parsed)
    monkeypatch.setattr(service.repo, "owner_rules",
                        lambda month, platform: [])
    monkeypatch.setattr(service, "_ebay_product_sku_map", lambda month: {})
    monkeypatch.setattr(service.repo, "replace_purchase_order_transit",
                        lambda month, rows, owners: calls.append(
                            ("replace", month, rows, owners)) or {
                            "inserted_rows": 0, "deleted_rows": 0,
                            "updated_summary_rows": 0,
                        })
    monkeypatch.setattr(service.repo, "view_snapshot", lambda month, dimension: {})
    monkeypatch.setattr(service.repo, "department_summary",
                        lambda month: {"items": [{"department_code": "AMZ-EU"}]})
    monkeypatch.setattr(service, "get_department_summary",
                        lambda month, *, use_snapshot: {"stat_month": month})
    monkeypatch.setattr(service, "get_dimension_summary",
                        lambda dimension, month, *, use_snapshot: {
                            "stat_month": month, "dimension_type": dimension,
                        })
    monkeypatch.setattr(service.repo, "save_view_snapshots",
                        lambda month, payloads: calls.append(
                            ("snapshot", month, tuple(payloads))))

    service.import_inventory_report_purchase_order(b"x", "orders.xlsx", "2026-08")
    assert calls == [
        ("replace", "2026-08", [], []),
        ("snapshot", "2026-08", ("GROUP", "OWNER")),
    ]


def test_owner_total_preserves_blank_local_columns_without_local_source():
    item = {
        "local_end_in_transit_qty": None,
        "local_end_in_transit_total_cost": None,
        "local_end_inventory_qty": None,
        "local_end_inventory_total_cost": None,
    }
    total = service._dimension_total_item(
        [item], "OWNER", "2026-09", "2026-09", None,
    )
    assert all(total[key] is None for key in item)


def test_inventory_health_counts_each_aged_sku_only_once(monkeypatch):
    monkeypatch.setattr(service.repo, "ebay_product_sku_map", lambda _month: {})
    monkeypatch.setattr(
        service.repo,
        "inventory_age_health_rows",
        lambda _month: [
            {
                "platform_code": "AMZ",
                "group_code": "US1",
                "store_name": "US1-示例店铺-US",
                "sku": "SKU-001",
                "is_aged_sku": 1,
            },
            {
                "platform_code": "AMZ",
                "group_code": "US1",
                "store_name": "US1-示例店铺-CA",
                "sku": "SKU-001",
                "is_aged_sku": 1,
            },
            {
                "platform_code": "AMZ",
                "group_code": "US1",
                "store_name": "US1-示例店铺-US",
                "sku": "SKU-002",
                "is_aged_sku": 1,
            },
            {
                "platform_code": "AMZ",
                "group_code": "US1",
                "store_name": "US1-示例店铺-US",
                "sku": "SKU-003",
                "is_aged_sku": 0,
            },
        ],
    )
    monkeypatch.setattr(
        service.repo,
        "owner_rules",
        lambda _month, platform: ([{
            "group_code": "US1",
            "rule_type": "STORE",
            "match_key": "示例店铺",
            "principal_name": "负责人甲",
        }] if platform == "amazon" else []),
    )

    groups, stores, owners, platforms = service._inventory_health_maps(
        "2026-08"
    )

    assert groups["AMZ-US1"] == Decimal("2")
    assert stores[("AMZ-US1", "示例店铺")] == Decimal("2")
    assert owners[("AMZ", "AMZ-US1", "负责人甲")] == Decimal("2")
    assert platforms == {"AMZ"}
