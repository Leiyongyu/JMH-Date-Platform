"""导出分页回归：全部使用内存桩，不连接数据库。"""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from backend.services import ebay_replenishment_v2_service as service


@pytest.fixture
def fake_rows(monkeypatch):
    rows = [
        {"sku": f"SKU-{index:04}", "site": "德国", "total_count": 510,
         "product_level": "S" if index % 3 == 0 else "B",
         "product_nature": "新品" if index % 2 == 0 else "老品",
         "forecast_sales_quantity_2": str(index), "sales_type": "NORMAL"}
        for index in range(510)
    ]
    calls = []
    owner_rules = [
        {"match_key": "SKU", "principal_name": "当月负责人", "rule_type": "EBAY_BRAND"},
        {"match_key": "EMPTY", "principal_name": "", "rule_type": "EBAY_BRAND"},
    ]

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            assert sql.count("%s") == len(params)
            calls.append((sql, params))
            self.sql, self.params = sql, params
        def fetchall(self):
            if "FROM dwd_performance_owner_rule" in self.sql:
                return owner_rules
            if "SELECT DISTINCT site_name" in self.sql and "period_rows AS" not in self.sql:
                return [{"site_name": "德国"}]
            if "LIMIT %s OFFSET %s" in self.sql:
                size, offset = self.params[-2:]
                return rows[offset:offset + size]
            return rows

    class Connection:
        def cursor(self): return Cursor()

    @contextmanager
    def connection(): yield Connection()

    monkeypatch.setattr(service, "db_connection", connection)
    monkeypatch.setattr(service.sku_analysis_service, "_ensure_tables", lambda: None)
    for name in ("lead_time_days_by_sku", "formula_by_level", "first_listing_date_by_sku",
                 "overseas_inventory_age_by_sku", "forecast_rules"):
        monkeypatch.setattr(service.repository, name, lambda: {})
    monkeypatch.setattr(service.repository, "list_level_rules", lambda **_: [])
    monkeypatch.setattr(service, "prepare_rules", lambda _: service.PreparedRules())
    monkeypatch.setattr(service.level_service, "prepare_levels", lambda _: None)
    monkeypatch.setattr(service, "_assemble_items", lambda rows, *_, **__: list(rows))
    monkeypatch.setattr(service, "_enrich_warehouse_rent", lambda _items: None)
    return rows, calls


def test_export_returns_more_than_200_without_sql_or_python_pagination(fake_rows):
    rows, calls = fake_rows
    data = service.list_replenishment(page=9, page_size=1, paginate=False)
    assert len(data["items"]) == 510
    assert data["items"] == rows
    assert data["pagination"] == {"page": 1, "page_size": 510, "total": 510}
    assert "LIMIT %s OFFSET %s" not in calls[0][0]


def test_export_combines_derived_filters_and_forecast_sort(fake_rows):
    rows, _ = fake_rows
    data = service.list_replenishment(product_level="S", product_nature="新品",
                                     sort_field="forecastSalesQuantity2", sort_order="desc",
                                     page_size=1, paginate=False)
    expected = list(reversed([r for r in rows if r["product_level"] == "S"
                             and r["product_nature"] == "新品"]))
    assert data["items"] == expected
    assert data["pagination"]["total"] == 85


def test_normal_list_keeps_sql_pagination(fake_rows):
    rows, calls = fake_rows
    data = service.list_replenishment(page=2, page_size=50)
    assert data["items"] == rows[50:100]
    assert data["pagination"]["total"] == 510
    assert "LIMIT %s OFFSET %s" in calls[0][0]


def test_normal_derived_list_keeps_memory_pagination(fake_rows):
    rows, _ = fake_rows
    data = service.list_replenishment(product_level="S", product_nature="新品",
                                     page=2, page_size=20)
    matching = [r for r in rows if r["product_level"] == "S" and r["product_nature"] == "新品"]
    assert data["items"] == matching[20:40]
    assert data["pagination"]["total"] == 85


@pytest.mark.parametrize("sort_field,field", [
    ("safetyStockQty", "safety_stock_quantity"),
    ("suggestedReplenishmentQty", "suggested_replenishment_quantity"),
    ("safetyStockQty2", "safety_stock_quantity_2"),
    ("suggestedReplenishmentQty2", "suggested_replenishment_quantity_2"),
])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_four_derived_sorts_are_numeric_global_and_nulls_last(fake_rows, sort_field, field, direction):
    rows, calls = fake_rows
    for i, row in enumerate(rows):
        row[field] = None if i >= 508 else str(i)
    data = service.list_replenishment(sort_field=sort_field, sort_order=direction, page=2, page_size=50)
    expected = sorted(rows[:508], key=lambda r: int(r[field]), reverse=direction == "desc") + rows[508:]
    assert data["items"] == expected[50:100]
    assert "LIMIT %s OFFSET %s" not in calls[0][0]
    exported = service.list_replenishment(sort_field=sort_field, sort_order=direction, paginate=False)
    assert exported["items"] == expected
    assert exported["items"][-2:] == rows[508:]


def test_level_totals_sum_all_matching_quantities_before_grade_filter_and_pagination(fake_rows):
    rows, calls = fake_rows
    for i, row in enumerate(rows):
        row["suggested_replenishment_quantity"] = str(i)
        row["suggested_replenishment_quantity_2"] = str(i * 2)
    data = service.list_replenishment(include_level_summary=True, product_level="S",
                                     product_nature="新品", page=2, page_size=20)
    eligible = [r for r in rows if r["product_nature"] == "新品"]
    summary = data["level_summary"]
    assert summary["ALL"]["suggested_replenishment_quantity"] == str(sum(int(r["suggested_replenishment_quantity"]) for r in eligible))
    for level in ("S", "B"):
        total = sum(int(r["suggested_replenishment_quantity"]) for r in eligible if r["product_level"] == level)
        assert summary[level] == {"suggested_replenishment_quantity": str(total), "suggested_replenishment_quantity_2": str(total * 2)}
    assert len(data["items"]) == 20
    assert data["pagination"]["total"] == 85
    assert "LIMIT %s OFFSET %s" not in calls[0][0]


def test_ungraded_records_can_be_filtered_and_counted(fake_rows):
    rows, _ = fake_rows
    rows[0].update(product_level=None, suggested_replenishment_quantity=None)
    rows[1].update(product_level="", suggested_replenishment_quantity="7", suggested_replenishment_quantity_2="11")
    rows[2].update(product_level="--", suggested_replenishment_quantity="0")
    data = service.list_replenishment(product_level="--", include_level_summary=True)
    assert data["items"] == rows[:3]
    assert data["pagination"]["total"] == 3
    assert data["level_summary"]["--"] == {"suggested_replenishment_quantity": "7", "suggested_replenishment_quantity_2": "11"}


def test_owner_uses_current_month_including_first_day_without_previous_month_fallback(fake_rows, monkeypatch):
    rows, calls = fake_rows
    periods = service.rolling_periods(date(2026, 10, 1))
    monkeypatch.setattr(service, "rolling_periods", lambda: periods)
    rows[0]["site"] = "英国"
    for i, sku in enumerate(["EMPTY-1-1", "UNKNOWN-1-1", "FLL-1-1", "LEJ-1-1", "CL-1-1"], 2):
        rows[i]["sku"] = sku
    data = service.list_replenishment(include_level_summary=True)
    assert data["owner_rule_month"] == "2026-10"
    assert [r["principal_name"] for r in data["items"][:7]] == [
        "当月负责人", "当月负责人", "未分配", "未分配", "方黎力", "方黎力", "陈丽"]
    rule_calls = [(sql, params) for sql, params in calls if "FROM dwd_performance_owner_rule" in sql]
    assert len(rule_calls) == 1
    assert rule_calls[0][1] == ("2026-10",)
    assert "platform='ebay'" in rule_calls[0][0]
    assert "rule_type='EBAY_BRAND'" in rule_calls[0][0]


def test_list_api_requests_full_grade_summary_and_forwards_sort(monkeypatch):
    from backend.api.v1 import ebay_replenishment_v2 as api
    captured = {}
    def fake_list(**kwargs):
        captured.update(kwargs)
        return {"items": []}
    monkeypatch.setattr(api.service, "list_replenishment", fake_list)
    api.list_replenishment(SimpleNamespace(state=SimpleNamespace(request_id="test")),
                           sort_field="suggestedReplenishmentQty2", product_level="--")
    assert captured["include_level_summary"] is True
    assert captured["sort_field"] == "suggestedReplenishmentQty2"
    assert captured["product_level"] == "--"
