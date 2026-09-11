"""导出分页回归：全部使用内存桩，不连接数据库。"""
from contextlib import contextmanager

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

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            assert sql.count("%s") == len(params)
            calls.append((sql, params))
            self.sql, self.params = sql, params
        def fetchall(self):
            if self.sql.lstrip().startswith("SELECT DISTINCT site_name"):
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
