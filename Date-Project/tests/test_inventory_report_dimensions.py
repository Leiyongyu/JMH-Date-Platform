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
    purchase_transit = [{
        "platform_code": "AMZ",
        "store_name": "US1-示例店铺-US",
        "sku": "ABC-001",
        "department_code": "AMZ-US1",
        "pending_arrival_qty": Decimal("4"),
        "sku_pending_total_cost": Decimal("40"),
    }]
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
        {},
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


def test_inventory_health_counts_each_aged_sku_only_once(monkeypatch):
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
