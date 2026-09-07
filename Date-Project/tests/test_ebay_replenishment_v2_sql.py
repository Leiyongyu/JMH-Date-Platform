from contextlib import contextmanager

from backend.services import ebay_replenishment_v2_service as service


def test_list_query_avoids_mysql_reserved_keys_alias(monkeypatch):
    executed_sql = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params):
            assert sql.count("%s") == len(_params)
            executed_sql.append(sql)

        def fetchall(self):
            return []

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    @contextmanager
    def fake_connection():
        yield FakeConnection()

    monkeypatch.setattr(service.sku_analysis_service, "_ensure_tables", lambda: None)
    monkeypatch.setattr(service, "db_connection", fake_connection)

    result = service.list_replenishment(page=1, page_size=20)

    combined_sql = "\n".join(executed_sql)
    assert "period_keys keys" not in combined_sql
    assert "period_keys period_key" in combined_sql
    assert "jmh_data_platform.warehouse_inventory_detail source" in combined_sql
    assert "TRIM(source.sku) sku" in combined_sql
    assert "inventory_summary.sku USING utf8mb4" in combined_sql
    assert "base.sku USING utf8mb4" in combined_sql
    assert "SUBSTRING_INDEX(source.sku" not in combined_sql
    assert "SUM(paid_amount_cny)" in combined_sql
    assert "paid_amount_m1" in combined_sql
    assert "ROW_NUMBER() OVER" not in combined_sql
    assert "SELECT source.product_name_cn" in combined_sql
    assert "ORDER BY source.payment_time DESC,source.id DESC" in combined_sql
    assert service._SORT_COLUMNS["returnRate"] == (
        "(return_qty_m1+return_qty_m2+return_qty_m3)/"
        "NULLIF((sales_qty_m1+sales_qty_m2+sales_qty_m3),0)"
    )
    assert service._SORT_COLUMNS["profitRate"] == (
        "(gross_profit_amount_m1+gross_profit_amount_m2+gross_profit_amount_m3)/"
        "NULLIF((paid_amount_m1+paid_amount_m2+paid_amount_m3),0)"
    )
    assert result["items"] == []


def test_source_filters_are_pushed_down_without_changing_outer_filters(monkeypatch):
    executed = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            assert sql.count("%s") == len(params)
            executed.append((sql, list(params)))

        def fetchall(self):
            return []

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    @contextmanager
    def fake_connection():
        yield FakeConnection()

    monkeypatch.setattr(service.sku_analysis_service, "_ensure_tables", lambda: None)
    monkeypatch.setattr(service, "db_connection", fake_connection)

    service.list_replenishment(
        site=" 德国 ", sku=" abc-123 ", product_name="电机", page=1, page_size=20
    )

    query, params = executed[0]
    assert "AND site_name=%s" in query
    assert "AND inventory_sku LIKE %s" in query
    assert "AND recent.site_name=%s" in query
    assert "AND recent.inventory_sku LIKE %s" in query
    assert "WHERE base.site=%s AND base.sku LIKE %s" in query
    assert "COALESCE(base.product_name,'') LIKE %s" in query
    assert params[:6] == [
        service._complete_months()[-1]["start_date"],
        service._complete_months()[0]["end_date"],
        "德国",
        "%ABC-123%",
        "德国",
        "%ABC-123%",
    ]
