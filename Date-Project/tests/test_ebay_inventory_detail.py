"""库存明细服务隔离用例：无数据库连接、无外部接口、无真实文件修改。"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import re
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api.deps import require_internal_access
from backend.api.v1 import ebay_inventory_detail as inventory_api
from backend.repositories import ebay_inventory_detail_repository as repository
from backend.services import ebay_inventory_detail_service as service


def source(sku="FRD-70618-0687", site="德国", **values):
    return {
        "site": site, "sku": sku, "product_name": "示例产品", "grade": "A",
        "overseas_in_transit_quantity": Decimal("10"),
        "overseas_sellable_quantity": Decimal("20"),
        "chengdu_in_transit_quantity": Decimal("3"),
        "chengdu_sellable_quantity": Decimal("7"),
        "sales_qty_30d": Decimal("12"), **values,
    }


@pytest.mark.parametrize(("sku", "expected"), [
    ("MCD-20017-0071", "20017"), ("FRD-00123-0068", "00123"),
    ("MCD-0-0071", "0"), ("SKU", None), ("MCD--0071", None),
    ("2PC-BMW-30055-0182", None), ("MCD-20A17-0071", None),
])
def test_middle_code_is_second_numeric_segment_and_preserves_text(isolated, sku, expected):
    isolated([source(sku=sku)])
    item = service.list_inventory()["items"][0]
    assert item["sku_middle_code"] == expected
    assert item["sku"] == sku


@pytest.mark.parametrize(("site", "sku", "expected"), [
    ("德国", "DAS-10053-0121", "10053DE"),
    ("美国", "DAS-10053-0121", "10053US"),
    ("英国", "DAS-10053-0121-YXQ", "10053UK"),
    ("德国", "DAS-00123-0121", "00123DE"),
    ("英国", "DAS-0-0121", "0UK"),
    ("法国", "DAS-10053-0121", None),
    ("英国", "2PC-DAS-10053-0121", None),
])
def test_middle_site_code_is_display_only_with_explicit_site_mapping(isolated, site, sku, expected):
    isolated([source(site=site, sku=sku)])
    item = service.list_inventory()["items"][0]
    assert item["sku_middle_site_code"] == expected
    assert item["sku"] == sku
    assert item["site"] == site


def test_middle_site_code_uses_frozen_row_without_recalculating_or_mutating(isolated, monkeypatch):
    isolated([source(sku="DAS-00123-0121", site="英国")])
    frozen, metadata, warnings = service.load_calculated_inventory()
    # Older JSON lacked both display identifiers; infer only from the frozen SKU.
    frozen[0].pop("sku_middle_code")
    original = dict(frozen[0])
    monkeypatch.setattr(service.history_repository, "read_inventory_day", lambda day: (frozen, metadata, warnings))
    monkeypatch.setattr(service, "load_calculated_inventory", lambda: pytest.fail("no current-source query"))
    item = service.list_inventory(stat_date="2026-09-15")["items"][0]
    assert item["sku_middle_site_code"] == "00123UK"
    assert item["sku_middle_code"] == "00123"
    assert frozen[0] == original


def test_middle_site_code_respects_stored_middle_and_does_not_enrich_summary():
    item = {"site": "德国", "sku": "DAS-123-XXX", "sku_middle_code": "00123"}
    assert service._round_item(item)["sku_middle_site_code"] == "00123DE"
    assert service._round_item({**item, "sku_middle_code": None})["sku_middle_site_code"] is None
    assert "sku_middle_site_code" not in service._round_item({"sales_qty_30d": Decimal(10)})


def rent(warehouse="DE", sku="JMH-70618-0687", currency="EUR", amount="10", **values):
    return {
        "warehouse_code": warehouse, "product_sku": sku,
        "bill_currency_code": currency,
        "warehouse_rent_amount": None if amount is None else Decimal(amount),
        "missing_amount_rows": 0, **values,
    }


@pytest.fixture
def isolated(monkeypatch):
    """调用列表也只使用内存数据；负责人解析不访问库。"""
    monkeypatch.setattr(service, "_ebay_assignment", lambda *args: ("张三", "BRAND"))
    monkeypatch.setattr(service, "_ebay_rule_map", lambda rows: rows)
    monkeypatch.setattr(service, "_ebay_product_sku_map", lambda *args, **kwargs: {})
    owner_rules = MagicMock(return_value=[{"rule_type": "BRAND"}])
    monkeypatch.setattr(service.owner_repository, "owner_rules", owner_rules)

    def install(rows, rents=None, rates=None, metadata=None):
        details = [] if rents is None else rents
        meta = {"rent_pull_month": "2026-09", "rent_row_count": len(details), **(metadata or {})}
        snapshot = MagicMock(return_value=(rows, meta, details, rates or {}))
        monkeypatch.setattr(service.repository, "read_snapshot", snapshot)
        return snapshot

    install.owner_rules = owner_rules
    return install


@pytest.mark.parametrize(("sales_3m", "expected"), [
    (300, "363"), (0, "-40"), (120, "121"), (1, "-39"),
])
def test_purchase_quantity_uses_unrounded_monthly_sales_fixed_duration_and_cycle_stock(
    isolated, sales_3m, expected,
):
    isolated([source(sales_qty_3m=sales_3m)])
    item = service.list_inventory()["items"][0]
    assert item["purchase_quantity"] == expected
    assert item["cycle_total_quantity"] == "40"
    assert item["total_duration_months"] == "4.03"
    assert "purchase_quantity" not in service.PLACEHOLDER_FIELDS


@pytest.mark.parametrize("raw", [None, "", "0", "9.99"])
def test_duration_is_fixed_for_every_site_not_overridden_by_source(isolated, raw):
    isolated([source(site=site, sales_qty_3m=300, total_duration_months=raw)
              for site in ["德国", "英国", "美国"]])
    items = service.list_inventory()["items"]
    assert all(item["total_duration_months"] == "4.03" for item in items)
    assert all(item["purchase_quantity"] == "363" for item in items)


@pytest.mark.parametrize("day", [None, "", "2024-12-31", "2026-08-09", "2026-08-31"])
def test_last_sold_date_preserves_year_month_day_or_empty(isolated, day):
    isolated([source(last_sold_at=day)])
    assert service.list_inventory()["items"][0]["last_sold_at"] == (day or None)


@pytest.mark.parametrize(("stock", "expected"), [
    ("250.500001", "152"), ("250.5", "153"), ("250.499999", "153"),
    ("555.499999", "-152"), ("555.5", "-153"), ("555.500001", "-153"),
    ("403.1", "0"), ("403", "0"),
])
def test_purchase_quantity_half_up_once_including_negative_boundaries(isolated, stock, expected):
    isolated([source(sales_qty_3m=300, overseas_sellable_quantity=Decimal(stock),
                     overseas_in_transit_quantity=0, chengdu_in_transit_quantity=0,
                     chengdu_sellable_quantity=0)])
    assert service.list_inventory()["items"][0]["purchase_quantity"] == expected


def test_last_sold_sql_uses_all_history_exact_site_and_sku_not_sales_windows():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    repository._source_rows(cursor)
    query = cursor.execute.call_args.args[0]
    expression = query.split("SELECT DATE_FORMAT(MAX(source.payment_time)", 1)[1].split(") last_sold_at", 1)[0]
    assert "'%%Y-%%m-%%d'" in expression
    assert "FROM dwd_ebay_sku_analysis_order source" in expression
    assert "source.site_name = CONVERT(inventory.site" in expression
    assert "source.inventory_sku = CONVERT(inventory.sku" in expression
    assert "INTERVAL" not in expression and "payment_time >=" not in expression
    assert "SUBSTRING" not in expression


@pytest.mark.parametrize(("pending", "expected"), [(None, "0"), (0, "0"), (12, "12")])
def test_pending_outbound_updates_cycle_monthly_ratio_and_purchase(isolated, pending, expected):
    isolated([source(sales_qty_3m=300, pending_outbound_quantity=pending)])
    item = service.list_inventory()["items"][0]
    assert item["pending_outbound_quantity"] == expected
    assert Decimal(item["cycle_total_quantity"]) == Decimal(40) + Decimal(expected)
    assert Decimal(item["total_stock_sales_ratio_months"]) == (Decimal(40) + Decimal(expected)) / 100
    assert Decimal(item["purchase_quantity"]) == Decimal(363) - Decimal(expected)
    assert item["overseas_total_quantity"] == "30"
    assert item["in_stock_sales_ratio"] == "1.666667"
    assert item["total_stock_sales_ratio"] == "2.5"
    assert item["procurement_plan_quantity"] == "0"


@pytest.mark.parametrize("provided", [None, "", "99"])
def test_procurement_plan_defaults_zero_for_all_sites_without_changing_totals(isolated, provided):
    isolated([source(site=site, sales_qty_3m=300, procurement_plan_quantity=provided)
              for site in ("德国", "英国", "美国")])
    for item in service.list_inventory()["items"]:
        assert item["procurement_plan_quantity"] == "0"
        assert item["cycle_total_quantity"] == "40"
        assert item["purchase_quantity"] == "363"


def test_missing_weekly_inventory_snapshot_is_explicit(isolated):
    isolated([], metadata={"inventory_batch_id": None, "inventory_pulled_at": None})
    result = service.list_inventory()
    assert result["items"] == []
    assert result["pagination"]["total"] == 0
    assert any("没有可用的成功周报库存快照" in value for value in result["metadata"]["warnings"])
    isolated([source()], metadata={"inventory_batch_id": "good", "inventory_pulled_at": "2026-09-14 16:38:43"})
    result = service.list_inventory()
    assert result["metadata"]["inventory_batch_id"] == "good"
    assert not any("没有可用的成功周报库存快照" in value for value in result["metadata"]["warnings"])


def test_formulas_use_decimal_and_preserve_unspecified_fields(isolated):
    isolated([source()])
    item = service.list_inventory()["items"][0]
    assert item["brand"] == "FRD"
    assert item["overseas_total_quantity"] == "30"
    assert item["cycle_total_quantity"] == "40"
    assert item["average_daily_sales_30d"] == "0.4"
    assert item["in_stock_sales_ratio"] == "1.666667"
    assert item["total_stock_sales_ratio"] == "2.5"
    assert item["owner"] == "张三"
    assert item["procurement_plan_quantity"] == "0"
    # 单价缺失不是0元；库存非0也不能伪造货值为0。
    assert item["unit_price_tax"] is None
    assert item["overseas_sellable_value"] is None
    assert item["overseas_total_value"] is None


def test_product_price_uses_full_decimal_before_rounding_valuation(isolated):
    isolated([source(imported_unit_price=Decimal("1.005"), price_source_rows=1,
                     overseas_sellable_quantity=Decimal("3"),
                     overseas_in_transit_quantity=Decimal("2"))],
             metadata={"price_imported_at": "2026-09-16 10:00:00", "price_row_count": 1})
    item = service.list_inventory()["items"][0]
    assert item["unit_price_tax"] == "1.01"
    assert item["overseas_sellable_value"] == "3.02"  # 1.005 * 3, not 1.01 * 3 = 3.03.
    assert item["overseas_total_value"] == "5.03"  # 1.005 * 5, not 1.01 * 5 = 5.05.
    assert item["price_warning"] is None


@pytest.mark.parametrize("price", [0, "0", Decimal("0.000000")])
def test_zero_product_price_is_valid_not_missing(isolated, price):
    isolated([source(imported_unit_price=price, price_source_rows=1)])
    item = service.list_inventory()["items"][0]
    assert all(item[field] == "0" for field in service.PRICE_FIELDS)
    assert item["price_warning"] is None


@pytest.mark.parametrize("price", [None, ""])
def test_missing_price_keeps_values_null_even_when_inventory_is_zero(isolated, price):
    isolated([source(imported_unit_price=price, price_source_rows=1,
                     overseas_sellable_quantity=0, overseas_in_transit_quantity=0)],
             metadata={"price_imported_at": "2026-09-16 10:00:00", "price_row_count": 1})
    result = service.list_inventory()
    item = result["items"][0]
    assert all(item[field] is None for field in service.PRICE_FIELDS)
    assert "不回退产品管理价格" in item["price_warning"]
    assert any("未匹配有效上传单价" in warning for warning in result["metadata"]["warnings"])


def test_product_cny_price_does_not_depend_on_rent_currency_rates(isolated):
    isolated([source(imported_unit_price=Decimal("25.123456"), price_source_rows=1)],
             [rent(currency="EUR")], rates={})
    item = service.list_inventory()["items"][0]
    assert item["warehouse_rent_30d_cny"] is None  # EUR is missing, independently.
    assert item["unit_price_tax"] == "25.12"
    assert item["overseas_sellable_value"] == "502.47"
    assert item["overseas_total_value"] == "753.7"
    assert item["price_warning"] is None


def test_same_middle_code_uses_same_price_across_sites_and_full_sku_aliases(isolated):
    isolated([source(site=site, sku=sku, imported_unit_price=Decimal("8.125"), price_source_rows=3)
              for site, sku in (("德国", "FRD-70618-0687"), ("英国", "OTH-70618-0001"),
                                ("美国", "FRD-70618-0687-YXQ"))])
    items = service.list_inventory(paginate=False)["items"]
    assert len(items) == 3
    assert {row["unit_price_tax"] for row in items} == {"8.13"}
    assert {row["overseas_sellable_value"] for row in items} == {"162.5"}
    assert {row["overseas_total_value"] for row in items} == {"243.75"}


@pytest.mark.parametrize(("source_rows", "batch_count"), [
    (2, 1),
    (1, 2),
])
def test_imported_middle_minimum_is_valid_with_multiple_pairs_and_import_batches(
        isolated, source_rows, batch_count):
    isolated([source(imported_unit_price=Decimal("12.25"), price_source_rows=source_rows)],
             metadata={"price_batch_count": batch_count, "price_snapshot_month": "2026-09"})
    item = service.list_inventory()["items"][0]
    assert item["unit_price_tax"] == "12.25"
    assert item["overseas_total_value"] == "367.5"
    assert item["price_warning"] is None


@pytest.mark.parametrize("catalogue_price", [0, Decimal("99.99"), Decimal("1.005")])
def test_missing_uploaded_price_never_falls_back_to_lingxing_catalogue(isolated, catalogue_price):
    isolated([source(cg_price=catalogue_price, imported_unit_price=None, price_source_rows=1)],
             metadata={"price_snapshot_month": "2026-09", "price_batch_count": 1})
    item = service.list_inventory()["items"][0]
    assert all(item[field] is None for field in service.PRICE_FIELDS)
    assert "不回退产品管理价格" in item["price_warning"]


@pytest.mark.parametrize("price", [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"),
                                  float("-inf"), "invalid-price", True])
def test_invalid_price_does_not_crash_or_create_misleading_values(isolated, price):
    isolated([source(imported_unit_price=price, price_source_rows=1)])
    result = service.list_inventory()
    item = result["items"][0]
    assert all(item[field] is None for field in service.PRICE_FIELDS)
    assert item["price_warning"]
    assert any("未匹配有效上传单价" in warning for warning in result["metadata"]["warnings"])


@pytest.mark.parametrize("field", service.PRICE_FIELDS)
@pytest.mark.parametrize("direction", ["ascending", "descending"])
def test_price_columns_sort_numerically_with_nulls_always_last(isolated, field, direction):
    isolated([source(sku=f"FRD-{label}", imported_unit_price=price, price_source_rows=1,
                     overseas_sellable_quantity=1, overseas_in_transit_quantity=0)
              for label, price in (("TEN", Decimal("10")), ("MISSING", None),
                                   ("NINE", Decimal("9")), ("ZERO", Decimal("0")))])
    result = service.list_inventory(sort_field=field, sort_order=direction, paginate=False)
    expected = ["FRD-ZERO", "FRD-NINE", "FRD-TEN"]
    if direction == "descending":
        expected.reverse()
    assert [item["sku"] for item in result["items"]] == expected + ["FRD-MISSING"]


@pytest.mark.parametrize("sales", [None, 0, Decimal("0")])
def test_missing_or_zero_sales_returns_zero_ratios(isolated, sales):
    isolated([source(sales_qty_30d=sales)])
    item = service.list_inventory()["items"][0]
    assert item["sales_qty_30d"] == "0"
    assert item["average_daily_sales_30d"] == "0"
    assert item["in_stock_sales_ratio"] == "0"
    assert item["total_stock_sales_ratio"] == "0"


@pytest.mark.parametrize(("sales", "expected"), [
    ("1", "0.03"), ("2", "0.07"), ("30", "1"), ("52", "1.73"),
    ("30.15", "1.01"),  # 1.005 must round half up, not half even.
])
def test_average_daily_sales_rounds_half_up_to_two_places(isolated, sales, expected):
    isolated([source(sales_qty_30d=Decimal(sales))])
    item = service.list_inventory()["items"][0]
    assert item["average_daily_sales_30d"] == expected
    assert item["sales_qty_30d"] == sales


def test_daily_sales_rounding_does_not_change_six_place_ratios():
    result = service._round_item({
        "average_daily_sales_30d": Decimal("1.005"),
        "in_stock_sales_ratio": Decimal("1.6666667"),
        "total_stock_sales_ratio": Decimal("2.1234567"),
    })
    assert result == {"average_daily_sales_30d": "1.01", "in_stock_sales_ratio": "1.666667",
                      "total_stock_sales_ratio": "2.123457"}


def test_missing_inventory_counts_zero_but_placeholders_remain_null(isolated):
    isolated([source(overseas_in_transit_quantity=None, overseas_sellable_quantity=None,
                     chengdu_in_transit_quantity=None, chengdu_sellable_quantity=None)])
    item = service.list_inventory()["items"][0]
    assert item["cycle_total_quantity"] == "0"
    assert item["in_stock_sales_ratio"] == "0"
    assert item["procurement_plan_quantity"] == "0"
    assert item["pending_outbound_quantity"] == "0"


def test_rent_combines_warehouses_and_currencies_after_conversion(isolated):
    rows = [source(site="美国"), source(site="英国")]
    details = [rent("USNJ", currency="USD", amount="10"),
               rent("USCA", currency="EUR", amount="2"),
               rent("UK", currency="GBP", amount="4")]
    isolated(rows, details, {"USD": Decimal("6.582861"), "EUR": Decimal("7.600066"),
                             "GBP": Decimal("8.877947")})
    values = {item["site"]: item for item in service.list_inventory(paginate=False)["items"]}
    assert values["美国"]["warehouse_rent_30d_cny"] == "81.03"
    assert values["英国"]["warehouse_rent_30d_cny"] == "35.51"
    assert values["美国"]["rent_rate_month"] == "2026-09"


def test_missing_one_currency_makes_whole_sku_rent_unknown(isolated):
    isolated([source(site="美国")], [rent("USNJ", currency="USD"), rent("USCA", currency="EUR")],
             {"USD": Decimal("6.58")})
    result = service.list_inventory()
    assert result["items"][0]["warehouse_rent_30d_cny"] is None
    assert "EUR" in result["items"][0]["rent_warning"]
    assert result["summary"]["warehouse_rent_30d_cny"] is None


def test_missing_source_amount_does_not_return_partial_rent(isolated):
    isolated([source()], [rent(amount="10", missing_amount_rows=1)], {"EUR": Decimal("7.6")})
    item = service.list_inventory()["items"][0]
    assert item["warehouse_rent_30d_cny"] is None
    assert "缺少仓租金额" in item["rent_warning"]


def test_absent_snapshot_differs_from_no_charge_for_one_sku(isolated):
    isolated([source()])
    assert service.list_inventory()["items"][0]["warehouse_rent_30d_cny"] is None
    isolated([source()], [rent(sku="JMH-OTHER-0001")], {"EUR": Decimal("7.6")})
    assert service.list_inventory()["items"][0]["warehouse_rent_30d_cny"] == "0"


def test_same_product_rent_is_counted_once_before_alias_brand_filter(isolated):
    isolated([source(), source(sku="BMW-70618-0687")], [rent()], {"EUR": Decimal("7.6")})
    result = service.list_inventory(brand="FRD")
    assert result["pagination"]["total"] == 1
    assert result["items"][0]["warehouse_rent_30d_cny"] == "76"
    assert result["items"][0]["rent_warning"] is None
    assert result["items"][0]["overseas_total_quantity"] == "60"
    assert result["summary"]["warehouse_rent_30d_cny"] == "76"


def test_same_suffix_in_different_sites_is_not_collision(isolated):
    isolated([source(), source(sku="BMW-70618-0687", site="英国")],
             [rent(), rent("UK", currency="GBP", amount="4")],
             {"EUR": Decimal("7.6"), "GBP": Decimal("8.88")})
    items = service.list_inventory(paginate=False)["items"]
    assert {item["warehouse_rent_30d_cny"] for item in items} == {"76", "35.52"}
    assert all(item["rent_warning"] is None for item in items)


def test_rent_normalization_removes_exactly_one_prefix():
    assert service.rent_sku_key("JMH-10006-0683") == "10006-0683"
    assert service.rent_sku_key("FRD-10006-0683") == "10006-0683"
    assert service.rent_sku_key("2PC-FRD-10006-0683") == "FRD-10006-0683"


def test_unknown_warehouse_is_reported_not_folded_into_other_site(isolated):
    isolated([source()], [rent("UNKNOWN")], {"EUR": Decimal("7.6")})
    result = service.list_inventory()
    assert any("UNKNOWN" in warning for warning in result["metadata"]["warnings"])


def test_selected_export_keeps_site_and_sku_together(isolated):
    isolated([source(), source(site="英国"), source(sku="BMW-OTHER-0001")])
    result = service.list_inventory(paginate=False, selected_keys=[{"site": "DE", "sku": "FRD-70618-0687"}])
    assert [(item["site"], item["sku"]) for item in result["items"]] == [("德国", "FRD-70618-0687")]
    assert result["pagination"]["total"] == 1


def test_unselected_export_returns_all_filtered_rows_not_current_page(isolated):
    isolated([source(sku=f"FRD-{i:05d}-0001") for i in range(4)] + [source(sku="BMW-OTHER-0001")])
    result = service.list_inventory(brand="FRD", page_size=1, paginate=False, selected_keys=[])
    assert len(result["items"]) == 4
    assert result["pagination"]["total"] == 4


@pytest.mark.parametrize("selected", [
    {"site": "德国", "sku": "MISSING-0001"},
    {"site": "英国", "sku": "FRD-70618-0687"},
    {"site": "德国", "sku": "BMW-OTHER-0001"},
])
def test_stale_or_out_of_filter_selection_rejected(isolated, selected):
    isolated([source(), source(sku="BMW-OTHER-0001")])
    with pytest.raises(ValueError, match="部分已选数据"):
        service.list_inventory(brand="FRD", paginate=False, selected_keys=[selected])


def test_sorting_is_numeric_and_pagination_stable(isolated):
    isolated([source(sku="FRD-B", sales_qty_30d=Decimal("9")),
              source(sku="FRD-C", sales_qty_30d=Decimal("100")),
              source(sku="FRD-A", sales_qty_30d=Decimal("9"))])
    first = service.list_inventory(page=1, page_size=2)
    second = service.list_inventory(page=2, page_size=2)
    assert [item["sku"] for item in first["items"]] == ["FRD-C", "FRD-A"]
    assert [item["sku"] for item in second["items"]] == ["FRD-B"]
    assert first["pagination"]["total"] == second["pagination"]["total"] == 3


def test_source_sql_is_inventory_driven_with_calendar_30_day_window():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    assert repository._source_rows(cursor) == []
    query = cursor.execute.call_args.args[0]
    assert "FROM inventory_summary inventory" in query
    assert "sales_anchor AS" not in query
    assert "INTERVAL 29 DAY" not in query
    assert query.count("COALESCE(source.shipping_status,'') NOT LIKE '%%已作废%%'") == 3
    assert query.count("%s") == 4
    assert "GROUP BY source.site_name,source.inventory_sku" in query
    # Window only deduplicates the seven warehouses in the selected weekly batch;
    # product-name lookup still avoids a full order-table window sort.
    assert "PARTITION BY i.wid,i.product_id" in query
    assert "ORDER BY source.payment_time DESC,source.id DESC LIMIT 1" in query


def test_price_sql_aggregates_uploaded_middle_code_minimum_before_inventory_join():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    repository._source_rows(cursor)
    cursor.execute.assert_called_once()
    query = cursor.execute.call_args.args[0]
    price_cte = query.split("product_prices AS (", 1)[1].split("\n        )", 1)[0]
    table = repository._product_price_table()
    assert table == "ebay_inventory_detail_price"
    assert f"FROM {table}" in price_cte
    assert "snapshot_month" not in price_cte and "sync_batch_id" not in price_cte
    assert "ods_goodcang_inventory_age_latest" not in price_cte
    assert "GROUP BY middle_code" in price_cte
    assert "COUNT(*) price_source_rows" in price_cte
    assert "MIN(unit_price) imported_unit_price" in price_cte
    assert "inventory.sku" not in price_cte
    assert "GROUP BY site" not in price_cte
    assert "NULLIF(unit_price" not in price_cte and "COALESCE(unit_price" not in price_cte
    assert "unit_price>0" not in price_cte.replace(" ", "")  # Zero is a valid minimum.
    assert "middle_code IS NOT NULL AND middle_code<>''" in price_cte
    price_join = query.split("LEFT JOIN product_prices prices", 1)[1].split("LEFT JOIN", 1)[0]
    assert "prices.middle_code" in price_join and "inventory.sku" in price_join
    assert "site" not in price_join
    assert "SUBSTRING_INDEX(SUBSTRING_INDEX(inventory.sku,'-',2),'-',-1)" in price_join
    assert "REGEXP '^[0-9]+$'" in price_join
    assert "CAST(" not in price_join  # Text equality must preserve leading zeros.
    assert "ods_lingxing_product_procurement_monthly" not in query
    assert "cg_price" not in query
    assert "prices.imported_unit_price" in query


def test_source_metadata_reads_all_imported_price_rows_and_middle_count_in_one_query():
    cursor = MagicMock()
    price_meta = {"price_imported_at": "2026-09-16 10:00:00",
                  "price_row_count": 900, "price_middle_code_count": 700}
    cursor.fetchone.side_effect = [{"sales_anchor_date": None},
                                   {"rent_batch_count": 1}, price_meta,
                                   {"age_snapshot_month": None, "age_row_count": 0, "age_batch_count": 0}]
    result = repository._source_metadata(cursor)
    assert cursor.execute.call_count == 4
    assert all(result[key] == value for key, value in price_meta.items())
    price_query = cursor.execute.call_args_list[2].args[0]
    assert f"FROM {repository._product_price_table()}" in price_query
    assert "ebay_inventory_detail_price" in price_query
    assert "MAX(updated_at) price_imported_at" in price_query
    assert "COUNT(DISTINCT middle_code) price_middle_code_count" in price_query
    assert "WHERE" not in price_query.upper()  # Incremental imports are not a latest-only batch.
    assert result["price_source"] == "uploaded_middle_code_min_v1"


def test_empty_uploaded_price_table_returns_null_price_metadata_and_values(isolated):
    cursor = MagicMock()
    price_meta = {"price_imported_at": None, "price_row_count": 0, "price_middle_code_count": 0}
    cursor.fetchone.side_effect = [{"sales_anchor_date": None}, {"rent_batch_count": 0}, price_meta,
                                   {"age_snapshot_month": None, "age_row_count": 0, "age_batch_count": 0}]
    metadata = repository._source_metadata(cursor)
    assert metadata["price_imported_at"] is None
    isolated([source(imported_unit_price=None, price_source_rows=None)], metadata=metadata)
    item = service.list_inventory()["items"][0]
    assert all(item[field] is None for field in service.PRICE_FIELDS)
    assert "不回退产品管理价格" in item["price_warning"]


def test_mixed_rent_batches_are_rejected():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"sales_anchor_date": None}, {"rent_batch_count": 2}]
    with pytest.raises(ValueError, match="多个批次"):
        repository._source_metadata(cursor)


def test_read_snapshot_uses_one_transaction_and_metadata_fx_month(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(repository, "db_connection", lambda: connection)
    metadata = {"rent_pull_month": "2026-08"}
    metadata_reader = MagicMock(return_value=metadata)
    source_reader = MagicMock(return_value=[source()])
    rent_reader = MagicMock(return_value=[rent()])
    rate_reader = MagicMock(return_value={"EUR": Decimal("7.6")})
    sales_window = (date(2026, 6, 1), date(2026, 9, 1))
    window_reader = MagicMock(return_value=sales_window)
    monkeypatch.setattr(repository, "_three_month_sales_window", window_reader)
    monkeypatch.setattr(repository, "_source_metadata", metadata_reader)
    monkeypatch.setattr(repository, "_source_rows", source_reader)
    monkeypatch.setattr(repository, "_rent_rows", rent_reader)
    monkeypatch.setattr(repository, "_rates", rate_reader)
    result = repository.read_snapshot()
    cursor.execute.assert_called_once_with("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    connection.begin.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    for reader in (metadata_reader, rent_reader):
        reader.assert_called_once_with(cursor)
    reference_date = window_reader.call_args.args[0]
    source_reader.assert_called_once_with(cursor, sales_window=sales_window,
                                         recent_window=repository._recent_sales_window(reference_date))
    window_reader.assert_called_once()
    rate_reader.assert_called_once_with(cursor, "2026-08")
    assert result[1] is metadata
    assert metadata["monthly_sales_date_from"] == sales_window[0]
    assert metadata["monthly_sales_date_to_exclusive"] == sales_window[1]


def test_read_snapshot_rolls_back_on_source_failure(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(repository, "db_connection", lambda: connection)
    monkeypatch.setattr(repository, "_source_metadata", MagicMock(side_effect=ValueError("bad batch")))
    with pytest.raises(ValueError, match="bad batch"):
        repository.read_snapshot()
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


@pytest.mark.parametrize(("reference_date", "start", "end"), [
    (date(2026, 9, 1), date(2026, 6, 1), date(2026, 9, 1)),
    (date(2026, 9, 15), date(2026, 6, 1), date(2026, 9, 1)),
    (date(2026, 9, 30), date(2026, 6, 1), date(2026, 9, 1)),
    (date(2026, 10, 1), date(2026, 7, 1), date(2026, 10, 1)),
    (date(2026, 1, 15), date(2025, 10, 1), date(2026, 1, 1)),
    (date(2026, 2, 28), date(2025, 11, 1), date(2026, 2, 1)),
    (date(2024, 3, 1), date(2023, 12, 1), date(2024, 3, 1)),
    (date(2024, 5, 31), date(2024, 2, 1), date(2024, 5, 1)),
])
def test_three_month_sales_window_uses_complete_calendar_months(reference_date, start, end):
    assert repository._three_month_sales_window(reference_date) == (start, end)


def test_three_month_window_default_uses_china_current_month(monkeypatch):
    # UTC is still August 31, but China is September 1: the window must be June-August.
    observed_zones = []
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            observed_zones.append(tz)
            instant = datetime(2026, 8, 31, 16, 5, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
    monkeypatch.setattr(repository, "datetime", FixedDateTime)
    assert repository._three_month_sales_window() == (date(2026, 6, 1), date(2026, 9, 1))
    assert len(observed_zones) == 1
    assert observed_zones[0] is not None
    assert observed_zones[0].utcoffset(None) == timedelta(hours=8)


def test_monthly_sales_sql_uses_explicit_calendar_window_and_preserves_inventory_rows(monkeypatch):
    window = (date(2026, 6, 1), date(2026, 9, 1))
    # Supplying a captured window must not consult the clock or use MAX(payment_time).
    monkeypatch.setattr(repository, "_three_month_sales_window", MagicMock(side_effect=AssertionError("clock read again")))
    cursor = MagicMock()
    rows = [source(sku="FRD-NO-SALES", sales_qty_3m=0), source(sku="FRD-WITH-SALES", sales_qty_3m=30)]
    cursor.fetchall.return_value = rows
    assert repository._source_rows(cursor, sales_window=window) == rows
    query, params = cursor.execute.call_args.args
    assert tuple(params[2:]) == window
    cte = query.split("complete_month_sales AS (", 1)[1].split("\n        ),", 1)[0]
    assert re.search(r"SUM\(\w+\.purchase_quantity\)\s+(?:AS\s+)?sales_qty_3m", cte, re.I)
    assert re.search(r"\w+\.payment_time\s*>=\s*%s", cte)
    assert re.search(r"\w+\.payment_time\s*<\s*%s", cte)
    assert re.search(r"GROUP BY\s+\w+\.site_name\s*,\s*\w+\.inventory_sku", cte, re.I)
    assert "MAX(payment_time)" not in cte and "sales_anchor" not in cte
    assert "INTERVAL 90 DAY" not in cte and "CURRENT_DATE" not in cte
    assert "FROM inventory_summary inventory" in query
    assert re.search(r"LEFT JOIN\s+complete_month_sales\s+", query, re.I)
    assert re.search(r"COALESCE\(\w+\.sales_qty_3m\s*,\s*0\)\s+(?:AS\s+)?sales_qty_3m", query, re.I)
    assert query.count("%s") == 4


def test_snapshot_window_does_not_follow_old_sales_anchor(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(repository, "db_connection", lambda: connection)
    window = (date(2026, 6, 1), date(2026, 9, 1))
    clock = MagicMock(return_value=window)
    monkeypatch.setattr(repository, "_three_month_sales_window", clock)
    recent_window = (date(2026, 8, 22), date(2026, 9, 21))
    recent_clock = MagicMock(return_value=recent_window)
    monkeypatch.setattr(repository, "_recent_sales_window", recent_clock)
    metadata = {"sales_source_latest_date": date(2020, 2, 29), "rent_pull_month": "2026-09"}
    monkeypatch.setattr(repository, "_source_metadata", lambda _: metadata)
    source_reader = MagicMock(return_value=[])
    monkeypatch.setattr(repository, "_source_rows", source_reader)
    monkeypatch.setattr(repository, "_rent_rows", lambda _: [])
    monkeypatch.setattr(repository, "_rates", lambda *_: {})
    _, result, _, _ = repository.read_snapshot()
    clock.assert_called_once()
    recent_clock.assert_called_once_with(clock.call_args.args[0])
    source_reader.assert_called_once_with(cursor, sales_window=window, recent_window=recent_window)
    assert result["sales_anchor_date"] == date(2026, 9, 20)
    assert result["sales_source_latest_date"] == date(2020, 2, 29)
    assert result["sales_date_from"] == recent_window[0]
    assert result["sales_date_to_exclusive"] == recent_window[1]
    assert result["monthly_sales_date_from"] == date(2026, 6, 1)
    assert result["monthly_sales_date_to_exclusive"] == date(2026, 9, 1)


def test_monthly_ratio_uses_cycle_inventory_and_fixed_three_month_average(isolated):
    # One or two months could have no sales: the source sum is still divided by all three months.
    isolated([source(sales_qty_3m=Decimal("30"), active_sales_months=1)])
    item = service.list_inventory()["items"][0]
    assert item["sales_qty_3m"] == "30"
    assert item["average_monthly_sales_3m"] == "10"
    assert item["cycle_total_quantity"] == "40"  # 10+20 overseas, 3+7 Chengdu.
    assert item["total_stock_sales_ratio_months"] == "4"  # 40/(30/3), not 40/30 or 30/10.
    assert "total_stock_sales_ratio_months" not in service.PLACEHOLDER_FIELDS
    assert "total_stock_sales_ratio_months" in service.SORT_FIELDS


def test_monthly_ratio_is_independent_of_recent_30_day_and_forecast_sales(isolated):
    isolated([source(sales_qty_3m=120, sales_qty_30d=0,
                     forecast_sales_quantity=100000, forecast_sales_quantity_2=999999)])
    item = service.list_inventory()["items"][0]
    assert item["average_monthly_sales_3m"] == "40"
    assert item["total_stock_sales_ratio_months"] == "1"  # Backend does not multiply by 100.
    assert item["total_stock_sales_ratio"] == "0"  # Separate 30-day denominator remains zero.


@pytest.mark.parametrize("sales", [None, "", 0, Decimal("0")])
def test_monthly_ratio_missing_or_zero_sales_is_zero_not_null(isolated, sales):
    isolated([source(sales_qty_3m=sales)])
    item = service.list_inventory()["items"][0]
    assert item["sales_qty_3m"] == "0"
    assert item["average_monthly_sales_3m"] == "0"
    assert item["total_stock_sales_ratio_months"] == "0"


@pytest.mark.parametrize("sales,expected", [(None,"0"),(0,"0"),(1,"0.33"),(2,"0.67"),(30,"10"),(Decimal("3.015"),"1.01")])
def test_displayed_three_month_average_uses_fixed_three_and_two_decimal_half_up(isolated, sales, expected):
    isolated([source(sales_qty_3m=sales, sales_qty_30d=9000, active_sales_months=1)])
    item = service.list_inventory()["items"][0]
    assert item["average_monthly_sales_3m"] == expected
    assert item["sales_qty_30d"] == "9000"


def test_monthly_average_sorts_unrounded_values_before_pagination(isolated):
    isolated([source(sku="FRD-A", sales_qty_3m=Decimal("3.001")),
              source(sku="FRD-Z", sales_qty_3m=Decimal("3.014"))])
    result = service.list_inventory(sort_field="average_monthly_sales_3m", sort_order="descending", page_size=1)
    assert result["items"][0]["sku"] == "FRD-Z"
    assert result["items"][0]["average_monthly_sales_3m"] == "1"
    assert result["pagination"]["total"] == 2


def test_monthly_ratio_does_not_round_average_before_dividing():
    rows = [source(sales_qty_3m=Decimal("1"), overseas_sellable_quantity=1,
                   overseas_in_transit_quantity=0, chengdu_in_transit_quantity=0,
                   chengdu_sellable_quantity=0)]
    items, _ = service._build_items(rows, [], {}, {}, {}, {})
    item = items[0]
    assert item["average_monthly_sales_3m"] == Decimal(1) / Decimal(3)
    assert item["total_stock_sales_ratio_months"] == Decimal("3")
    # Rounding 1/3 to six decimals first would give 3.000003 instead of exactly 3.
    assert service._round_item(item)["total_stock_sales_ratio_months"] == "3"


def test_monthly_ratio_rounds_output_to_six_places_only(isolated):
    isolated([source(sales_qty_3m=Decimal("7"), overseas_sellable_quantity=1,
                     overseas_in_transit_quantity=0, chengdu_in_transit_quantity=0,
                     chengdu_sellable_quantity=0)])
    item = service.list_inventory()["items"][0]
    assert item["total_stock_sales_ratio_months"] == "0.428571"


def test_monthly_ratio_zero_cycle_inventory_is_zero_with_sales(isolated):
    isolated([source(sales_qty_3m=30, overseas_sellable_quantity=None,
                     overseas_in_transit_quantity=0, chengdu_in_transit_quantity=0,
                     chengdu_sellable_quantity=0)])
    item = service.list_inventory()["items"][0]
    assert item["cycle_total_quantity"] == "0"
    assert item["total_stock_sales_ratio_months"] == "0"


@pytest.mark.parametrize("direction", ["ascending", "descending"])
def test_monthly_ratio_sorts_numerically_before_pagination(isolated, direction):
    isolated([source(sku=f"FRD-{number}", sales_qty_3m=3,
                     overseas_sellable_quantity=number, overseas_in_transit_quantity=0,
                     chengdu_in_transit_quantity=0, chengdu_sellable_quantity=0,
                     sales_qty_30d=1000-number) for number in (9, 100, 10)])
    result = service.list_inventory(sort_field="total_stock_sales_ratio_months",
                                    sort_order=direction, page=1, page_size=2)
    expected = ["FRD-9", "FRD-10"] if direction == "ascending" else ["FRD-100", "FRD-10"]
    assert [row["sku"] for row in result["items"]] == expected
    assert result["pagination"]["total"] == 3


def aged_source(days=58, **values):
    return source(age_days=days, age_source_rows=2, age_source_products=1,
                  age_invalid_rows=0, **values)


@pytest.mark.parametrize("days", [0, "0", Decimal("0.000000"), 58, Decimal("58.000000")])
def test_overseas_age_keeps_valid_zero_and_integer_days(isolated, days):
    isolated([aged_source(days)], metadata={"age_snapshot_month": "2026-09", "age_batch_count": 1})
    item = service.list_inventory()["items"][0]
    assert item["overseas_max_age_days"] == str(int(Decimal(str(days))))
    assert item["age_warning"] is None
    assert "overseas_max_age_days" not in service.PLACEHOLDER_FIELDS
    assert "overseas_max_age_days" in service.SORT_FIELDS


@pytest.mark.parametrize("row_count", [None, 0])
def test_no_matching_latest_age_row_remains_null_without_historical_fallback(isolated, row_count):
    isolated([source(age_days=None, age_source_rows=row_count, age_source_products=None,
                     age_invalid_rows=None)],
             metadata={"age_snapshot_month": "2026-09", "age_row_count": 100, "age_batch_count": 1})
    item = service.list_inventory()["items"][0]
    assert item["overseas_max_age_days"] is None
    assert "未匹配" in item["age_warning"]
    assert "历史月份" not in item["age_warning"]


@pytest.mark.parametrize("days", [None, "", -1, Decimal("-0.01"), Decimal("1.5"),
                                 Decimal("NaN"), Decimal("Infinity"), float("-inf"),
                                 "invalid-age", True])
def test_invalid_age_is_not_rounded_or_treated_as_zero(isolated, days):
    isolated([aged_source(days)], metadata={"age_batch_count": 1})
    item = service.list_inventory()["items"][0]
    assert item["overseas_max_age_days"] is None
    assert item["age_warning"]


@pytest.mark.parametrize(("invalid_rows", "products", "batches"), [
    (1, 1, 1),  # One malformed batch must not be silently discarded by MAX.
    (0, 1, 2),  # The full latest table contains multiple imported sync batches.
])
def test_partial_invalid_or_ambiguous_age_is_entirely_unknown(isolated, invalid_rows, products, batches):
    isolated([source(age_days=58, age_source_rows=5, age_source_products=products,
                     age_invalid_rows=invalid_rows)], metadata={"age_batch_count": batches})
    item = service.list_inventory()["items"][0]
    assert item["overseas_max_age_days"] is None
    assert item["age_warning"]


def test_many_valid_batches_for_one_source_sku_are_not_ambiguous(isolated):
    # The SQL aggregation already supplies the oldest warehouse/batch value.
    isolated([source(age_days=58, age_source_rows=6, age_source_products=1,
                     age_invalid_rows=0)], metadata={"age_batch_count": 1})
    item = service.list_inventory()["items"][0]
    assert item["overseas_max_age_days"] == "58"
    assert item["age_warning"] is None


def test_merged_product_age_is_available_before_alias_brand_filter(isolated):
    isolated([aged_source(58), aged_source(58, sku="BMW-70618-0687")],
             metadata={"age_batch_count": 1})
    all_rows = service.list_inventory(paginate=False)["items"]
    assert len(all_rows) == 1
    assert all(row["overseas_max_age_days"] == "58" for row in all_rows)
    assert all(row["age_warning"] is None for row in all_rows)
    result = service.list_inventory(brand="FRD")
    assert len(result["items"]) == 1
    assert result["items"][0]["overseas_max_age_days"] == "58"
    assert "FRD-70618-0687" in result["items"][0]["sku_aliases"]


def test_unmatched_age_does_not_report_a_source_collision(isolated):
    rows = [source(sku=sku, age_days=None, age_source_rows=0, age_source_products=0,
                   age_invalid_rows=0) for sku in ("FRD-70618-0687", "BMW-70618-0687")]
    isolated(rows, metadata={"age_snapshot_month": "2026-09", "age_batch_count": 1})
    for item in service.list_inventory(paginate=False)["items"]:
        assert item["overseas_max_age_days"] is None
        assert "冲突" not in (item["age_warning"] or "")
        assert "多个SKU" not in (item["age_warning"] or "")


def test_same_suffix_on_different_sites_uses_separate_age_values(isolated):
    isolated([aged_source(58, site="英国"), aged_source(7, site="德国")],
             metadata={"age_batch_count": 1})
    items = {row["site"]: row for row in service.list_inventory(paginate=False)["items"]}
    assert items["英国"]["overseas_max_age_days"] == "58"
    assert items["德国"]["overseas_max_age_days"] == "7"
    assert all(item["age_warning"] is None for item in items.values())


@pytest.mark.parametrize("direction", ["ascending", "descending"])
def test_overseas_age_sorts_numerically_and_puts_missing_last(isolated, direction):
    rows = [aged_source(age, sku=f"FRD-{name}") for name, age in (("NINE", 9), ("TEN", 10), ("HUNDRED", 100), ("ZERO", 0))]
    rows.append(source(sku="FRD-MISSING", age_days=None, age_source_rows=0))
    isolated(rows, metadata={"age_batch_count": 1})
    items = service.list_inventory(sort_field="overseas_max_age_days", sort_order=direction, paginate=False)["items"]
    expected = ["FRD-ZERO", "FRD-NINE", "FRD-TEN", "FRD-HUNDRED"]
    if direction == "descending":
        expected.reverse()
    assert [item["sku"] for item in items] == expected + ["FRD-MISSING"]


def test_attaching_age_does_not_change_existing_inventory_sales_rent_or_price(isolated):
    original = source(imported_unit_price=Decimal("1.005"), price_source_rows=1, sales_qty_3m=90)
    isolated([original], [rent()], {"EUR": Decimal("7.6")}, {"age_batch_count": 1})
    before = service.list_inventory()["items"][0]
    isolated([{**original, "age_days": 58, "age_source_rows": 2, "age_source_products": 1, "age_invalid_rows": 0}],
             [rent()], {"EUR": Decimal("7.6")}, {"age_batch_count": 1})
    after = service.list_inventory()["items"][0]
    for field in (*service.QUANTITY_FIELDS, *service.PRICE_FIELDS, "warehouse_rent_30d_cny",
                  "average_daily_sales_30d", "average_monthly_sales_3m", "in_stock_sales_ratio",
                  "total_stock_sales_ratio", "total_stock_sales_ratio_months", "owner"):
        if field != "overseas_max_age_days":
            assert after[field] == before[field], field
    assert before["overseas_max_age_days"] is None and after["overseas_max_age_days"] == "58"


@pytest.mark.parametrize(("database", "expected_database"), [
    ("jmh_data_platform", "jmh_data_platform"),
    ("  ", "jmh_data_platform"),
    ("  inventory_source  ", "inventory_source"),
    ("inventory`source", "inventory``source"),
])
def test_age_table_uses_dedicated_latest_table_in_source_database(
        monkeypatch, database, expected_database):
    monkeypatch.setattr(repository, "settings", MagicMock(shop_source_database=database))
    assert repository._inventory_age_table() == (
        f"`{expected_database}`.ods_goodcang_inventory_age_latest"
    )


def test_age_sql_uses_full_latest_raw_snapshot_and_max_not_cost_match():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    repository._source_rows(cursor, sales_window=(date(2026, 6, 1), date(2026, 9, 1)))
    query = cursor.execute.call_args.args[0]
    age_source = query.split("age_source AS (", 1)[1].split("\n        )", 1)[0]
    age_groups = query.split("age_groups AS (", 1)[1].split("\n        )", 1)[0]
    table = repository._inventory_age_table()
    assert f"FROM {table}" in age_source
    assert "ods_goodcang_inventory_age_latest" in age_source
    assert age_source.count(table) == 1
    assert "snapshot_month" not in age_source  # Read every row of the overwritten latest batch.
    assert "sync_batch_id" not in age_source  # Mixed sync batches must remain visible to metadata.
    assert "inventory.sku" not in age_source  # No per-inventory-SKU source fallback.
    assert "ods_goodcang_inventory_age_monthly" not in query
    assert "product_sku" in age_source and "warehouse_age" in age_source
    assert "raw_json" in age_source and "$.warehouse_age" in age_source
    assert "sku_suffix" in age_source and "SUBSTRING" in age_source.upper()
    assert all(f"'{warehouse}'" in age_source for warehouse in ("DE", "CZ", "IT", "UK", "FR"))
    assert "LIKE" in age_source.upper() and "US" in age_source
    assert "MAX(" in age_groups.upper() and "age_days" in age_groups
    assert "GROUP BY" in age_groups.upper() and "site" in age_groups and "sku_suffix" in age_groups
    assert "age_source_rows" in age_groups and "age_source_products" in age_groups and "age_invalid_rows" in age_groups
    assert "COUNT(DISTINCT" in age_groups.upper()
    for field in ("age_days", "age_source_rows", "age_source_products", "age_invalid_rows"):
        assert f"ages.{field}" in query  # The service still receives the same four raw fields.
    assert "match_status" not in (age_source + age_groups).lower()
    assert "MATCHED" not in age_source + age_groups
    assert "inventory_age_cost" not in age_source + age_groups
    age_join = query.split("LEFT JOIN age_groups", 1)[1].split("LEFT JOIN", 1)[0]
    assert "sku_suffix" in age_join and "inventory.sku" in age_join and "inventory.site" in age_join
    assert "SUBSTRING" in age_join.upper()  # Both sides remove exactly the first prefix.
    assert "FROM inventory_summary inventory" in query


def test_source_metadata_reads_full_latest_age_table_with_month_only_as_metadata():
    cursor = MagicMock()
    age_meta = {"age_snapshot_month": "2026-09", "age_pulled_at": "2026-09-01 07:00:00",
                "age_row_count": 2000, "age_batch_count": 1}
    cursor.fetchone.side_effect = [{"sales_anchor_date": None}, {"rent_batch_count": 1},
                                   {"price_imported_at": "2026-09-16 10:00:00", "price_row_count": 1}, age_meta]
    result = repository._source_metadata(cursor)
    assert cursor.execute.call_count == 4
    assert all(result[key] == value for key, value in age_meta.items())
    query = cursor.execute.call_args_list[3].args[0]
    table = repository._inventory_age_table()
    assert f"FROM {table}" in query and query.count(table) == 1
    assert "ods_goodcang_inventory_age_latest" in query
    assert "ods_goodcang_inventory_age_monthly" not in query
    assert "MAX(snapshot_month) age_snapshot_month" in query
    assert "MAX(pulled_at) age_pulled_at" in query
    assert "COUNT(*) age_row_count" in query
    assert "COUNT(DISTINCT sync_batch_id) age_batch_count" in query
    assert not re.search(r"\bWHERE\b|\bGROUP BY\b|\bLIMIT\b", query, re.I)
    assert all("ods_goodcang_inventory_age_monthly" not in call.args[0]
               for call in cursor.execute.call_args_list)


@pytest.mark.parametrize("batch_count", [2, 3])
def test_latest_age_metadata_counts_all_batches_and_service_rejects_mixed_age_only(
        isolated, batch_count):
    cursor = MagicMock()
    # The latest table should be a single overwrite batch. Do not hide an older
    # month's leftover batch behind a MAX(snapshot_month) or latest-id filter.
    age_meta = {"age_snapshot_month": "2026-09", "age_pulled_at": "2026-09-16 07:00:00",
                "age_row_count": 2000, "age_batch_count": batch_count}
    cursor.fetchone.side_effect = [{"sales_anchor_date": None}, {"rent_batch_count": 0},
                                   {"price_imported_at": "2026-09-16 10:00:00", "price_row_count": 1}, age_meta]
    metadata = repository._source_metadata(cursor)
    query = cursor.execute.call_args_list[3].args[0]
    assert "COUNT(DISTINCT sync_batch_id) age_batch_count" in query
    assert not re.search(r"\bWHERE\b", query, re.I)
    assert metadata["age_batch_count"] == batch_count
    isolated([aged_source(58, imported_unit_price=Decimal("25"), price_source_rows=1),
              source(sku="FRD-NO-AGE", age_days=None, age_source_rows=0,
                     imported_unit_price=Decimal("25"), price_source_rows=1)], metadata=metadata)
    result = service.list_inventory(paginate=False)
    assert len(result["items"]) == 2
    for item in result["items"]:
        assert item["overseas_max_age_days"] is None
        assert "多个批次" in item["age_warning"]
        assert item["unit_price_tax"] == "25"  # The independently imported CNY price remains valid.
        assert item["overseas_total_quantity"] == "30"
    assert any("库龄" in warning for warning in result["metadata"]["warnings"])


def test_empty_age_snapshot_is_distinct_from_zero_day_stock(isolated):
    cursor = MagicMock()
    age_meta = {"age_snapshot_month": None, "age_pulled_at": None,
                "age_row_count": 0, "age_batch_count": 0}
    cursor.fetchone.side_effect = [{"sales_anchor_date": None}, {"rent_batch_count": 0},
                                   {"price_imported_at": None, "price_row_count": 0}, age_meta]
    metadata = repository._source_metadata(cursor)
    assert metadata["age_snapshot_month"] is None
    isolated([source(age_days=None, age_source_rows=0, age_source_products=None,
                     age_invalid_rows=None)], metadata=metadata)
    assert service.list_inventory()["items"][0]["overseas_max_age_days"] is None


def price_workbook(rows):
    book = Workbook()
    book.active.append(["产品代码", "单价(默认采购价)"])
    for row in rows:
        book.active.append(row)
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def test_price_import_validates_deduplicates_and_normalizes_audit_fields_before_write(monkeypatch):
    content = price_workbook([("ABC-00123-0001", "10.125"), ("ABC-00123-0001", "10.1250"),
                              ("ABC-00123-0001", "20")])
    writer = MagicMock(return_value=2)
    monkeypatch.setattr(service.price_repository, "replace_prices", writer)
    monkeypatch.setattr(service, "load_calculated_inventory", lambda: pytest.fail("import must not rewrite snapshots"))
    result = service.import_prices(content, r"C:\upload\prices.xlsx", " " + "a" * 80 + " ")
    rows, operator, filename = writer.call_args.args
    assert len(rows) == 2
    assert {row["unit_price"] for row in rows} == {Decimal("10.125"), Decimal("20")}
    assert {row["middle_code"] for row in rows} == {"00123"}
    assert operator == "a" * 64
    assert filename == "prices.xlsx"
    assert result["imported_rows"] == 2
    assert result["duplicate_rows"] == 1
    assert "rows" not in result
    assert "点击刷新" in result["message"]


@pytest.mark.parametrize("invalid_price", ["-0.01", "bad price", None])
def test_invalid_price_rejects_whole_import_before_any_repository_write(monkeypatch, invalid_price):
    writer = MagicMock()
    monkeypatch.setattr(service.price_repository, "replace_prices", writer)
    content = price_workbook([("ABC-00123-0001", "10"), ("ABC-00999-0001", invalid_price)])
    with pytest.raises(ValueError):
        service.import_prices(content, "prices.xlsx", "tester")
    writer.assert_not_called()


def test_price_import_default_operator_and_filename_length_are_bounded(monkeypatch):
    writer = MagicMock(return_value=1)
    monkeypatch.setattr(service.price_repository, "replace_prices", writer)
    service.import_prices(price_workbook([("ABC-00123-0001", "0")]), "/upload/" + "x" * 300 + ".xlsx", " ")
    assert writer.call_args.args[1] == "SYSTEM"
    assert len(writer.call_args.args[2]) == 255


@pytest.fixture
def price_api_client():
    app = FastAPI()
    app.include_router(inventory_api.router)
    app.dependency_overrides[require_internal_access] = lambda: None

    @app.middleware("http")
    async def add_request_id(request, call_next):
        request.state.request_id = "price-import-test"
        return await call_next(request)

    with TestClient(app) as client:
        yield client, app


def test_price_import_api_passes_file_and_operator_to_real_validated_service(price_api_client, monkeypatch):
    client, _ = price_api_client
    writer = MagicMock(return_value=1)
    monkeypatch.setattr(service.price_repository, "replace_prices", writer)
    response = client.post("/api/v1/finance/ebay-inventory-detail/prices/import", params={"operator": "tester"},
                           files={"file": ("prices.xlsx", price_workbook([("ABC-00123-0001", "10.125")]))})
    assert response.status_code == 200
    assert response.json()["data"]["imported_rows"] == 1
    assert writer.call_args.args[1:] == ("tester", "prices.xlsx")


def test_price_import_api_rejects_invalid_and_oversized_uploads_without_writes(price_api_client, monkeypatch):
    client, _ = price_api_client
    writer = MagicMock()
    monkeypatch.setattr(service.price_repository, "replace_prices", writer)
    invalid = client.post("/api/v1/finance/ebay-inventory-detail/prices/import",
                          files={"file": ("prices.xlsx", b"not an excel file")})
    assert invalid.status_code == 400
    monkeypatch.setattr(inventory_api, "MAX_FILE_BYTES", 32)
    oversized = client.post("/api/v1/finance/ebay-inventory-detail/prices/import",
                            files={"file": ("prices.xlsx", b"x" * 33)})
    assert oversized.status_code == 400
    assert "不能超过" in oversized.json()["detail"]
    writer.assert_not_called()


def test_price_import_api_requires_internal_access_before_processing_file(price_api_client, monkeypatch):
    client, app = price_api_client
    processor = MagicMock()
    monkeypatch.setattr(service, "import_prices", processor)

    def deny():
        raise HTTPException(status_code=403, detail="internal access denied")

    app.dependency_overrides[require_internal_access] = deny
    response = client.post("/api/v1/finance/ebay-inventory-detail/prices/import",
                           files={"file": ("prices.xlsx", b"untrusted")})
    assert response.status_code == 403
    processor.assert_not_called()
