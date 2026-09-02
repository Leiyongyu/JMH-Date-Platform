import pytest

from backend.services import inventory_report_etl_service as service


def test_rebuild_does_not_replace_existing_results_when_any_source_is_empty(
    monkeypatch,
):
    monkeypatch.setattr(
        service.repo,
        "source_rows",
        lambda _month: {
            "fba": [{"id": 1}],
            "overseas": [],
            "local": [{"id": 2}],
            "order_profit": [{"id": 3}],
        },
    )

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("空源数据时不应读取后续规则或覆盖汇总表")

    monkeypatch.setattr(service.repo, "amazon_shop_map", unexpected_call)
    monkeypatch.setattr(service.repo, "replace_clean_month", unexpected_call)

    with pytest.raises(ValueError, match="缺少海外仓源数据.*保持不变"):
        service.rebuild_monthly_inventory_report("2026-07")


def test_rebuild_inventory_does_not_require_order_profit(monkeypatch):
    sources = {
        "fba": [{"id": 1}],
        "overseas": [{"id": 2}],
        "local": [{"id": 3}],
        "order_profit": [],
        "ebay_sales": [],
    }

    service._require_complete_sources("2026-07", sources)


def test_overseas_rows_are_all_ebay_and_match_owner_by_sku_brand():
    rows = service._clean_overseas(
        "2026-07",
        [
            {
                "id": 1,
                "sync_batch_id": "batch-1",
                "sys_wid": "100",
                "ware_house_name": "海外仓",
                "seller_name": None,
                "sku": "BMW-30386-0557",
                "allocation_in_transit_count": "2",
                "allocation_in_transit_cost": "20.50",
                "day_end_count": "3",
                "day_end_cost": "30.75",
                "child_list": None,
            }
        ],
        {"BMW": "测试负责人"},
    )

    assert len(rows) == 1
    assert rows[0]["platform_code"] == "EBAY"
    assert rows[0]["group_code"] == "EBAY-1"
    assert rows[0]["department_code"] == "EBAY-1"
    assert rows[0]["principal_name"] == "测试负责人"
    assert rows[0]["principal_match_source"] == "EBAY_BRAND"


def test_overseas_jmh_sku_uses_product_mapping_for_owner():
    rows = service._clean_overseas(
        "2026-07",
        [{
            "id": 1,
            "sync_batch_id": "batch-1",
            "sys_wid": "100",
            "sku": "JMH-30032-0018",
            "allocation_in_transit_count": "0",
            "allocation_in_transit_cost": "0",
            "day_end_count": "12",
            "day_end_cost": "588",
            "child_list": None,
        }],
        {"BMW": "陈丽"},
        {"30032-0018": "BMW-30032-0018"},
    )

    assert rows[0]["principal_name"] == "陈丽"
    assert rows[0]["principal_match_source"] == "EBAY_PRODUCT_SKU_BRAND"


def test_amz_sales_uses_fba_assignment_and_special_store_filter():
    rules = service._amazon_rule_maps(
        [
            {
                "group_code": "US1",
                "rule_type": "STORE",
                "match_key": "优贝诺",
                "principal_name": "测试负责人",
            }
        ]
    )
    rows, stats = service._clean_amz_sales(
        "2026-07",
        [
            {
                "id": 1,
                "sid": "1001",
                "msku": "NORMAL-1",
                "local_sku": "SKU-1",
                "currency_code": "CNY",
                "amount": "100",
            },
            {
                "id": 2,
                "sid": "1001",
                "msku": "DSQ-1",
                "local_sku": "SKU-2",
                "currency_code": "CNY",
                "amount": "200",
            },
        ],
        {"1001": "US1-优贝诺-US"},
        rules,
    )

    assert stats["amz_sales_excluded_special_msku_rows"] == 1
    assert len(rows) == 1
    assert rows[0]["msku"] == "DSQ-1"
    assert rows[0]["group_code"] == "US1"
    assert rows[0]["department_code"] == "AMZ-US1"
    assert rows[0]["principal_name"] == "测试负责人"


def test_monthly_inventory_chongqing_store_prefers_exact_month_rule():
    rules = service._amazon_rule_maps(
        [
            {
                "group_code": "US1",
                "rule_type": "STORE",
                "match_key": "重庆茁凯",
                "principal_name": "当月负责人",
            },
            {
                "group_code": "US1",
                "rule_type": "STORE",
                "match_key": "邱存帅",
                "principal_name": "旧负责人",
            },
        ]
    )

    assert service._amazon_assignment(
        "US1-重庆茁凯-US", "ABC-001", rules
    ) == ("当月负责人", "AMAZON_STORE", "US1")


def test_monthly_inventory_chongqing_store_keeps_legacy_fallback():
    rules = service._amazon_rule_maps(
        [
            {
                "group_code": "US1",
                "rule_type": "STORE",
                "match_key": "邱存帅",
                "principal_name": "旧负责人",
            }
        ]
    )

    assert service._amazon_assignment(
        "US1-重庆茁凯-US", "ABC-001", rules
    ) == ("旧负责人", "AMAZON_STORE", "US1")


def test_monthly_inventory_eu_uk_site_uses_fixed_owner():
    rules = service._amazon_rule_maps(
        [
            {
                "group_code": "EU",
                "rule_type": "BRAND",
                "match_key": "ABC",
                "principal_name": "其他品牌负责人",
            }
        ]
    )

    assert service._amazon_assignment(
        "EU-示例店铺-uk", "ABC-001", rules
    ) == ("吴清栩", "AMAZON_EU_UK_FIXED", "EU")


def test_monthly_inventory_eu_store_dimension_does_not_override_us_store():
    rules = service._amazon_rule_maps(
        [
            {
                "group_code": "EU",
                "rule_type": "STORE",
                "match_key": "同名店铺",
                "principal_name": "EU店铺负责人",
            },
            {
                "group_code": "US1",
                "rule_type": "STORE",
                "match_key": "同名店铺",
                "principal_name": "US店铺负责人",
            },
        ]
    )

    assert service._amazon_assignment(
        "US2-同名店铺-US", "ABC-001", rules
    ) == ("US店铺负责人", "AMAZON_STORE", "US2")


def test_department_summary_calculates_actual_and_target_rate():
    fba_row = {
        "department_code": "AMZ-US1",
        "end_inventory_qty": service.ZERO,
        "end_inventory_total_cost": service.Decimal("100"),
        "end_in_transit_qty": service.ZERO,
        "end_in_transit_total_cost": service.Decimal("50"),
    }
    rows = service._department_summaries(
        "2026-07",
        [fba_row],
        [],
        [],
        amz_sales_rows=[
            {
                "department_code": "AMZ-US1",
                "amount": service.Decimal("20"),
            }
        ],
    )

    us1 = next(row for row in rows if row["department_code"] == "AMZ-US1")
    assert us1["actual_achievement_amount"] == service.Decimal("20")
    assert us1["target_achievement_rate"] == (
        service.Decimal("20") / service._sales_target_cny(us1)
    )
    total = next(row for row in rows if row["department_code"] == "AUTO-PARTS-TOTAL")
    assert total["target_achievement_rate"] == us1["target_achievement_rate"]


def test_sales_target_uses_department_specific_factor():
    base = {
        "overseas_end_inventory_total_cost": service.ZERO,
        "fba_end_inventory_total_cost": service.Decimal("100"),
        "overseas_end_in_transit_total_cost": service.ZERO,
        "fba_end_in_transit_total_cost": service.Decimal("50"),
    }

    ebay = service._sales_target_cny({**base, "department_code": "EBAY-1"})
    eu = service._sales_target_cny({**base, "department_code": "AMZ-EU"})
    us1 = service._sales_target_cny({**base, "department_code": "AMZ-US1"})
    us2 = service._sales_target_cny({**base, "department_code": "AMZ-US2"})
    us2_mj = service._sales_target_cny({**base, "department_code": "AMZ-US2-MJ"})
    us1_zxy = service._sales_target_cny({**base, "department_code": "AMZ-US1-ZXY"})

    assert eu > us1
    assert us1 == us2 == us2_mj == us1_zxy
    assert us1 > ebay


def test_sales_target_usd_uses_rate_and_missing_rate_returns_none():
    row = {
        "department_code": "AMZ-US1",
        "overseas_end_inventory_total_cost": service.Decimal("100"),
        "fba_end_inventory_total_cost": service.Decimal("200"),
        "overseas_end_in_transit_total_cost": service.Decimal("30"),
        "fba_end_in_transit_total_cost": service.Decimal("70"),
    }
    rate = service.Decimal("7.1234")

    target_usd = service._sales_target(row, rate)

    assert target_usd * rate == service._sales_target_cny(row)
    assert service._sales_target(row, None) is None
