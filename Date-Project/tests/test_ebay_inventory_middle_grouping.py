"""Product grouping before paging/export/capture; no real DB writes or upstream requests."""
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from backend.services import ebay_inventory_detail_service as service
from backend.services import ebay_inventory_detail_export_service as export
from backend.services import ebay_inventory_pivot_service as pivot
from datetime import date

from test_ebay_inventory_detail import graded, isolated, source, rent


def product(sku="DAS-10053-0121", site="英国", **extra):
    return source(sku=sku, site=site, imported_unit_price=Decimal("10"),
                  sales_qty_3m=Decimal("30"), **extra)


def test_group_totals_recalculate_averages_ratios_and_round_purchase_only_once(isolated):
    a = product(sales_qty_30d=1, overseas_sellable_quantity=1,
                overseas_in_transit_quantity=0, chengdu_in_transit_quantity=0,
                chengdu_sellable_quantity=0, pending_outbound_quantity=2)
    b = {**a, "sku": "DAS-10053-0121-YXQ", "sales_qty_30d": 3,
         "sales_qty_3m": Decimal("1"), "overseas_sellable_quantity": 3,
         "pending_outbound_quantity": 4}
    a["sales_qty_3m"] = Decimal("1")
    isolated([b, a])
    data = service.list_inventory()
    row = data["items"][0]
    assert data["pagination"]["total"] == 1
    assert row["sku"] == "DAS-10053-0121"
    assert row["sku_aliases"] == [a["sku"], b["sku"]]
    assert row["merged_sku_count"] == 2
    assert row["pending_outbound_quantity"] == "6"
    assert row["cycle_total_quantity"] == "10"
    assert row["sales_qty_30d"] == "4"
    assert row["average_monthly_sales_3m"] == "0.67"
    assert row["in_stock_sales_ratio"] == "1"
    assert row["total_stock_sales_ratio"] == "1"
    assert row["total_stock_sales_ratio_months"] == "15"
    assert row["total_duration_months"] == "4.03"  # not 8.06
    assert row["purchase_quantity"] == "-7"  # rounding each member then adding gives -8
    assert data["metadata"]["source_sku_count"] == 2
    assert data["metadata"]["grouping_policy"] == "site_middle_code_v1"


def test_middle_code_uses_minimum_price_not_inventory_weighted_price(isolated):
    a = product(overseas_sellable_quantity=2, overseas_in_transit_quantity=1)
    b = {**a, "sku": "DAS-10053-9999", "imported_unit_price": Decimal("20"),
         "overseas_sellable_quantity": 1, "overseas_in_transit_quantity": 6}
    isolated([a, b])
    row = service.list_inventory()["items"][0]
    assert row["unit_price_tax"] == "10"  # MIN(10,20), no longer (3*10 + 7*20)/10.
    assert row["overseas_total_value"] == "100"
    assert row["overseas_sellable_value"] == "30"
    assert row["grade"] == "A"


@pytest.mark.parametrize(("prices", "stocks", "expected", "total_value"), [
    ((0, 10), (1, 1), "0", "0"),  # explicit zero wins the minimum
    ((10, None), (1, 0), "10", "10"),
    ((10, None), (1, 1), "10", "20"),  # a matching middle-code price covers all aliases
    ((None, None), (1, 1), None, None),
    ((10, 10), (0, 0), "10", "0"),
    ((10, 20), (0, 0), "10", "0"),  # no weight or division is needed
    ((10, 20), (-1, 2), "10", "10"),  # stock is not a price selection factor
])
def test_middle_minimum_price_missing_zero_and_empty_stock(isolated, prices, stocks, expected, total_value):
    rows = []
    for index in range(2):
        rows.append({**product(), "sku": "DAS-10053-0121" + ("-YXQ" if index else ""),
                     "imported_unit_price": prices[index], "overseas_sellable_quantity": stocks[index],
                     "overseas_in_transit_quantity": 0})
    isolated(rows)
    row = service.list_inventory()["items"][0]
    assert row["unit_price_tax"] == expected
    assert row["overseas_total_value"] == total_value
    if expected is None:
        assert row["price_warning"]
        assert row["missing_price_sku_count"] == 2
    else:
        assert row["price_warning"] is None
        assert row["missing_price_sku_count"] == 0


def test_rent_same_key_once_distinct_keys_sum_and_missing_rate_not_zero(isolated):
    rows = [product(), product(sku="JMH-10053-0121"), product(sku="DAS-10053-0121-YXQ")]
    rents = [rent("UK", sku="JMH-10053-0121", currency="GBP", amount="10"),
             rent("UK", sku="JMH-10053-0121-YXQ", currency="EUR", amount="5")]
    isolated(rows, rents, {"GBP": Decimal("8"), "EUR": Decimal("7")})
    row = service.list_inventory()["items"][0]
    assert row["warehouse_rent_30d_cny"] == "115"  # not 195
    assert row["rent_match_keys"] == ["10053-0121", "10053-0121-YXQ"]
    isolated(rows, rents, {"GBP": Decimal("8")})
    partial = service.list_inventory()["items"][0]
    assert partial["warehouse_rent_30d_cny"] == "80"
    assert partial["missing_rent_key_count"] == 1
    assert "缺失金额未计入" in partial["rent_warning"]
    assert pivot.aggregate_inventory(service.load_calculated_inventory()[0])[0]["missing_rent_count"] == 1
    isolated(rows, rents, {})
    assert service.list_inventory()["items"][0]["warehouse_rent_30d_cny"] is None


@pytest.mark.parametrize(("earlier", "later"), [
    ("2025-12-31", "2026-02-01"),
    ("2026-08-09", "2026-08-31"),
    (None, "2026-08-31"),
])
def test_max_age_and_latest_sale_date_from_members(isolated, earlier, later):
    a = product(age_days=59, age_source_rows=2, age_source_products=2,
                last_sold_at=earlier)
    b = product(sku="DAS-10053-0121-YXQ", age_days=70, age_source_rows=1,
                last_sold_at=later)
    isolated([a, b])
    row = service.list_inventory()["items"][0]
    assert row["overseas_max_age_days"] == "70"
    assert row["age_warning"] is None
    assert row["last_sold_at"] == later
    b["age_source_rows"] = 0
    isolated([a, b])
    row = service.list_inventory()["items"][0]
    assert row["overseas_max_age_days"] == "59"
    assert "已匹配" in row["age_warning"]


def test_sites_leading_zeros_and_invalid_middle_codes_do_not_coalesce(isolated):
    isolated([product(), product(site="德国"), product(sku="DAS-010053-0121"),
              product(sku="2PC-DAS-10053-0121"), product(sku="2PC-DAS-10053-0121-YXQ"),
              product(sku="PLAIN"), product(sku="OTHER")])
    assert service.list_inventory()["pagination"]["total"] == 7


def test_stable_representative_alias_filters_keep_whole_group_and_sort_before_page(isolated):
    rows = [product(sku="BMW-10053-0121", sales_qty_30d=1),
            product(sku="JMH-10053-0121-YXQ", sales_qty_30d=30),
            product(sku="DAS-20000-0121", sales_qty_30d=25)]
    isolated(rows)
    first = service.list_inventory(page_size=1)
    second = service.list_inventory(page=2, page_size=1)
    assert first["items"][0]["sku"] == "BMW-10053-0121"
    assert first["items"][0]["sales_qty_30d"] == "31"
    assert first["pagination"]["total"] == second["pagination"]["total"] == 2
    assert second["items"][0]["sku"] == "DAS-20000-0121"
    # 合并后观测值 1+30=31 跨进「≥30」档，同样的利润率下等级由A升为S。
    for filters in ({"sku": "10053"}, {"brand": "JMH"}, {"sku": "10053", "grade": "S"}):
        data = service.list_inventory(**filters)
        assert data["pagination"]["total"] == 1
        assert data["items"][0]["sales_qty_30d"] == "31"
    isolated(list(reversed(rows)))
    assert service.list_inventory(page_size=1)["items"][0] == first["items"][0]


def test_merged_grade_recalculates_from_pooled_profit_and_pooled_monthly_sales(isolated):
    """合并行的等级必须用合计重算，不能取任一成员SKU的等级。

    两个成员各自 K=10、J=0.25（单独看都是A）；合并后同月销量相加 K=20，
    利润率仍是 50/200=0.25，落到 K<=29 档 → 仍是A。关键是等级来自合计值，
    而不是从成员那里继承。
    """
    a = product(**graded("A"))
    b = product(sku="DAS-10053-0121-YXQ", **graded("A"))
    isolated([a, b])
    row = service.list_inventory()["items"][0]
    assert row["merged_sku_count"] == 2
    assert row["max_monthly_sales"] == "20"        # 10+10，同一自然月相加
    assert row["profit_rate"] == "0.25"            # 50/200，不是两个0.25取平均
    assert row["grade"] == "A"


def test_merged_grade_can_differ_from_every_member_grade(isolated):
    """成员单看都不是S，合并后销量够高就该评S；这正是不能继承成员等级的原因。"""
    a = product(**graded("C"))                      # K=10, J=0.15 → C
    b = product(sku="DAS-10053-0121-YXQ", **graded("A"))   # K=10, J=0.25 → A
    isolated([a, b])
    row = service.list_inventory()["items"][0]
    assert row["max_monthly_sales"] == "20"
    assert row["profit_rate"] == "0.2"             # (15+25)/(100+100)
    assert row["grade"] == "A"                     # K<=29 且 J>=0.2


def test_zero_sales_amount_gives_no_grade_instead_of_lowest_grade(isolated):
    """三月销售额为0时除不出利润率，页面显示--，不能当成"利润率低"评到E。"""
    isolated([product(three_month_profit_cny=Decimal("0"),
                      three_month_paid_amount_cny=Decimal("0"))])
    row = service.list_inventory()["items"][0]
    assert row["profit_rate"] is None
    assert row["grade"] is None


def test_observation_is_the_rolling_30_day_window_not_a_calendar_month(isolated):
    """本次观测值就是「近30天销量」那个滚动窗口，不再按自然月汇总。"""
    isolated([product(sales_qty_30d=Decimal("47"))])
    item = service.list_inventory()["items"][0]
    assert item["max_monthly_sales"] == "47" == item["sales_qty_30d"]
    assert item["max_monthly_sales_source"] == "ORDERS"


def test_duplicate_full_sku_is_not_silently_double_counted(isolated):
    isolated([product(), product()])
    with pytest.raises(ValueError, match="重复站点"):
        service.list_inventory()


def test_pivot_uses_shared_middle_price_for_all_merged_inventory(isolated):
    isolated([product(), {**product(sku="DAS-10053-0121-YXQ"), "imported_unit_price": None}])
    rows, _, _, _ = service.load_calculated_inventory()
    assert rows[0]["missing_price_sku_count"] == 0
    group = pivot.aggregate_inventory(rows)[0]
    assert group["sku_count"] == 1
    assert group["missing_price_count"] == 0
    assert group["overseas_total_value"] == Decimal("600")


def test_pivot_keeps_missing_price_count_when_no_middle_price_exists(isolated):
    isolated([{**product(), "imported_unit_price": None},
              {**product(sku="DAS-10053-0121-YXQ"), "imported_unit_price": None}])
    rows, _, _, _ = service.load_calculated_inventory()
    assert rows[0]["missing_price_sku_count"] == 2
    group = pivot.aggregate_inventory(rows)[0]
    assert group["sku_count"] == 1
    assert group["missing_price_count"] == 1  # Pivot counts merged products, not full-SKU aliases.
    assert group["overseas_total_value"] is None


def test_pivot_and_selected_excel_use_the_same_merged_values(isolated, monkeypatch):
    isolated([product(), product(sku="DAS-10053-0121-YXQ"), product(site="德国")])
    rows, _, _, _ = service.load_calculated_inventory()
    groups = pivot.aggregate_inventory(rows)
    assert sum(group["sku_count"] for group in groups) == 2
    assert sum(group["overseas_total_quantity"] for group in groups) == Decimal(90)
    monkeypatch.setattr(export, "list_inventory", service.list_inventory)
    _, content = export.export_inventory(selected_keys=[{"site": "英国", "sku": "DAS-10053-0121"}])
    book = load_workbook(BytesIO(content))
    try:
        assert book.active.max_row == 2
        columns = {key: index for index, (key, _, _) in enumerate(export.COLUMNS, 1)}
        assert book.active.cell(2, columns["overseas_total_quantity"]).value == 60
        assert book.active.cell(2, columns["sales_qty_30d"]).value == 24
    finally:
        book.close()


def test_old_history_not_rewritten_and_grouped_history_alias_search_is_read_only(monkeypatch):
    old = {**product(), "brand": "DAS", "overseas_total_quantity": Decimal(30),
           "cycle_total_quantity": Decimal(40), "warehouse_rent_30d_cny": None}
    frozen = [old, {**old, "sku": "DAS-10053-0121-YXQ"}]
    monkeypatch.setattr(service.history_repository, "read_inventory_day", lambda day: (frozen, {}, []))
    monkeypatch.setattr(service, "load_calculated_inventory", lambda: pytest.fail("no live recompute"))
    assert service.list_inventory(stat_date="2026-09-15")["pagination"]["total"] == 2
    frozen[:] = [{**old, "sku_aliases": [old["sku"], old["sku"] + "-YXQ"],
                  "merged_sku_count": 2, "sales_qty_30d": Decimal(24)}]
    row = service.list_inventory(stat_date="2026-09-16", sku="10053")["items"][0]
    assert row["sales_qty_30d"] == "24"


def floor(site, key_type, key, value):
    return {"site": site, "product_key_type": key_type, "product_key": key,
            "max_monthly_sales": Decimal(value)}


def test_high_water_wins_when_orders_no_longer_contain_the_peak_month(isolated):
    """只升不降：订单表里算得到的最大值低于已存高水位时，保持高水位。

    业务场景就是这个——订单表只有2026-05起的数据，更早的历史高点只存在
    于高水位表里，重算不能把它抹掉。
    """
    isolated([product(sku="DAS-10756-0121", site="德国", sales_qty_30d=Decimal("35"))],
             max_floor=[floor("德国", "MIDDLE", "10756", "197")])
    item = service.list_inventory()["items"][0]
    assert item["max_monthly_sales"] == "197"
    assert item["max_monthly_sales_source"] == "HISTORY_HIGH_WATER"


def test_current_orders_win_when_they_exceed_the_stored_high_water(isolated):
    isolated([product(sku="DAS-10756-0121", site="德国", sales_qty_30d=Decimal("240"))],
             max_floor=[floor("德国", "MIDDLE", "10756", "197")])
    item = service.list_inventory()["items"][0]
    assert item["max_monthly_sales"] == "240"
    assert item["max_monthly_sales_source"] == "ORDERS"


def test_high_water_raises_the_grade_it_would_otherwise_lower(isolated):
    """销量偏低会把等级整体拉低，这正是要存高水位的原因。"""
    row = product(sku="DAS-10756-0121", site="德国", sales_qty_30d=Decimal("3"),
                  three_month_profit_cny=Decimal("21"), three_month_paid_amount_cny=Decimal("100"))
    isolated([row])
    assert service.list_inventory()["items"][0]["grade"] == "D"   # K=3 → ≤4档，0.21≥0.15
    isolated([row], max_floor=[floor("德国", "MIDDLE", "10756", "197")])
    assert service.list_inventory()["items"][0]["grade"] == "S"   # K=197 → ≥30档，0.21≥0.2


def test_high_water_key_falls_back_to_full_sku_without_a_numeric_middle_code(isolated):
    isolated([product(sku="PLAIN", site="德国", sales_qty_30d=Decimal("0"))],
             max_floor=[floor("德国", "SKU", "PLAIN", "88")])
    assert service.list_inventory()["items"][0]["max_monthly_sales"] == "88"


def test_high_water_candidates_use_merged_key_and_statistics_date(isolated):
    """候选按合并键提交，观测值是合并后的近30天销量，窗口右端即统计日期。"""
    isolated([product(sku="BMW-10053-0121", site="德国", sales_qty_30d=Decimal("20")),
              product(sku="JMH-10053-0121", site="德国", sales_qty_30d=Decimal("20"))])
    _, _, _, candidates = service.load_calculated_inventory()
    assert candidates == [{"site": "德国", "product_key_type": "MIDDLE", "product_key": "10053",
                           "max_monthly_sales": Decimal("40"), "peak_window_end": date(2026, 9, 22)}]
