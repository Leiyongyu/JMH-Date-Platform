from contextlib import contextmanager
from datetime import date, timedelta
import re
import sqlite3

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
    assert "ROW_NUMBER() OVER" in combined_sql
    assert "PARTITION BY site_name,inventory_sku" in combined_sql
    assert "ORDER BY payment_time DESC,id DESC" in combined_sql
    assert "source.source_rank=1" in combined_sql
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
    assert params[9:16] == [
        service.rolling_periods()[-1]["start_date"],
        service.rolling_periods()[0]["end_date"],
        "德国",
        "%ABC-123%",
        service.rolling_periods()[0]["end_date"],
        "德国",
        "%ABC-123%",
    ]


def test_actual_rolling_sql_includes_boundaries_once_and_excludes_today(monkeypatch):
    captured = []
    reference = date(2026, 10, 15)
    periods = service.rolling_periods(reference)

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params): captured.append((sql, params))
        def fetchall(self): return []

    class Connection:
        def cursor(self): return Cursor()

    @contextmanager
    def connection(): yield Connection()

    monkeypatch.setattr(service, 'db_connection', connection)
    monkeypatch.setattr(service, 'rolling_periods', lambda: periods)
    monkeypatch.setattr(service.sku_analysis_service, '_ensure_tables', lambda: None)
    service.list_replenishment()
    query, params = captured[0]
    # Run production aggregation CTEs using an already-normalized in-memory source.
    prefix = query.split('product_orders AS (', 1)[0]
    windows = query.split('), period_rows AS (', 1)[1].split('        period_keys AS (', 1)[0].rstrip().removesuffix(',')
    monthly = query.split('        monthly AS (', 1)[1].split('        base AS (', 1)[0].rstrip().removesuffix(',')
    sql = prefix + 'period_rows AS (' + windows + ', monthly AS (' + monthly + '''
        SELECT monthly.*,recent_windows.sales_qty_7d,recent_windows.sales_qty_15d,
               recent_windows.sales_qty_30d
        FROM monthly JOIN recent_windows USING(site_name,inventory_sku)'''
    sql = sql.replace('%%', '%').replace('%s', '?').replace('CAST(? AS DATE)', '?')
    sql = re.sub(r'DATE_SUB\(anchor.anchor_date,INTERVAL (\d+) DAY\)',
                 lambda m: f"date(anchor.anchor_date,'-{m[1]} days')", sql)
    offsets = [-1, 0, 1, 7, 8, 15, 16, 30, 31, 60, 61, 90, 91]
    quantities = {days: 2 ** index for index, days in enumerate(offsets)}
    with sqlite3.connect(':memory:') as db:
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE product_orders (
                id INTEGER, site_name TEXT, inventory_sku TEXT, payment_time TEXT,
                purchase_quantity INTEGER, paid_amount_cny INTEGER, order_profit_cny INTEGER,
                refund_quantity INTEGER, refund_amount_cny INTEGER, shipping_status TEXT,
                platform_order_no TEXT);
            CREATE TABLE ebay_sku_analysis_return_classification (
                platform_order_no TEXT PRIMARY KEY, big_category TEXT);
        ''')
        db.executemany('INSERT INTO product_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)', [
            (i, '德国', 'BMW-1-2', (reference - timedelta(days=days)).isoformat() + ' 00:00:00',
             qty, qty * 10, qty * 2, qty, 0, '已发货', str(i))
            for i, (days, qty) in enumerate(quantities.items())
        ])
        # Include the final second before today, not just midnight fixtures.
        db.execute('INSERT INTO product_orders VALUES (99,?,?,?,?,?,?,?,?,?,?)',
                   ('德国', 'BMW-1-2', '2026-10-14 23:59:59', 3, 30, 6, 3, 0, '已发货', '99'))
        data = {row['stat_month']: dict(row) for row in db.execute(
            sql, [value.isoformat() if isinstance(value, date) else value for value in params[:12]])}
    assert len(data) == 3
    for index, period in enumerate(periods):
        row = data[period['month']]
        expected = sum(qty for days, qty in quantities.items() if 30 * index < days <= 30 * (index + 1))
        if index == 0:
            expected += 3
        assert row['sales_qty'] == row['return_qty'] == expected
        assert row['gross_profit_amount'] == expected * 2
        assert row['paid_amount'] == expected * 10
        for days in (7, 15, 30):
            assert row[f'sales_qty_{days}d'] == sum(q for age, q in quantities.items() if 0 < age <= days) + 3
