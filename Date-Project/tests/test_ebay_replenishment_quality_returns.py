from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import sqlite3

from backend.services import ebay_replenishment_v2_service as service


def test_quality_rate_uses_sales_and_aggregate_is_not_average_of_rates():
    row = {
        "site": "德国", "sku": "SKU-A",
        "sales_qty_m1": 10, "return_qty_m1": 3, "quality_return_qty_m1": 2,
        "sales_qty_m2": 90, "return_qty_m2": 6, "quality_return_qty_m2": 3,
        "unclassified_return_qty_m1": 1,
        "unclassified_return_qty_m2": 2,
    }
    item = service._assemble_items([row], service._complete_months(date(2026, 9, 9)))[0]
    assert item["monthly_metrics"][0]["quality_return_rate"] == "0.200000"
    assert item["monthly_metrics"][1]["quality_return_rate"] == "0.033333"
    assert item["monthly_metrics"][2]["quality_return_rate"] is None
    assert item["quality_return_summary"] == {
        "return_qty": "9", "quality_return_qty": "5",
        "quality_return_rate": "0.050000", "unclassified_return_qty": "3",
    }
    assert item["return_qty"] == "3"
    assert item["return_rate"] == "0.090000"
    # 观察指标不得改变原退货、销量、预测、分级及补货字段。
    baseline = service._assemble_items(
        [{k: v for k, v in row.items() if not k.startswith(("quality_", "unclassified_"))}],
        service._complete_months(date(2026, 9, 9)),
    )[0]
    for key in baseline.keys() - {"monthly_metrics", "quality_return_summary"}:
        assert item[key] == baseline[key], key


def test_quality_quantity_kept_but_zero_sales_rate_is_unknown():
    item = service._assemble_items(
        [{"site": "英国", "sku": "A", "quality_return_qty_m1": Decimal("2"), "sales_qty_m1": 0}],
        service._complete_months(date(2026, 9, 9)),
    )[0]
    assert item["monthly_metrics"][0]["quality_return_qty"] == "2"
    assert item["monthly_metrics"][0]["quality_return_rate"] is None
    assert item["quality_return_summary"]["quality_return_rate"] is None


def test_actual_monthly_sql_counts_pieces_without_join_duplication(monkeypatch):
    queries = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            assert sql.count("%s") == len(params)
            queries.append(sql)
        def fetchall(self): return []

    class Connection:
        def cursor(self): return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(service, "db_connection", connection)
    monkeypatch.setattr(service.sku_analysis_service, "_ensure_tables", lambda: None)
    service.list_replenishment()
    query = queries[0]
    # Execute the actual period/monthly CTEs against a disposable in-memory fixture.
    # The full production query's placeholder order is checked above.
    period = query.split("        anchor AS (", 1)[0]
    monthly = query.split("        monthly AS (", 1)[1].split("        base AS (", 1)[0].rstrip().removesuffix(",")
    sql = (period + " monthly AS (" + monthly + " SELECT * FROM monthly").replace("%%", "%").replace("%s", "?")
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.create_function("DATE_FORMAT", 2, lambda value, _: value[:7])
        db.executescript("""
            CREATE TABLE dwd_ebay_sku_analysis_order (
                id INTEGER PRIMARY KEY, site_name TEXT, inventory_sku TEXT,
                payment_time TEXT, purchase_quantity INTEGER, paid_amount_cny INTEGER,
                order_profit_cny INTEGER, refund_quantity INTEGER, refund_amount_cny INTEGER,
                shipping_status TEXT, platform_order_no TEXT);
            CREATE TABLE ebay_sku_analysis_return_classification (
                platform_order_no TEXT PRIMARY KEY, big_category TEXT, small_category TEXT);
        """)
        db.executemany("INSERT INTO ebay_sku_analysis_return_classification VALUES (?,?,?)", [
            ("Q", "产品质量问题", "产品质量差"), ("OTHER", "客户自身原因", "客户主观退换货"),
            ("UNUSABLE", " 产品质量问题 ", "产品无法使用"), ("OLD", "产品质量问题", "产品质量差"),
        ])
        rows = [
            ("德国", "A", "2026-08-31 23:59:59", 2, 2, "Q"),
            ("德国", "A", "2026-08-15", 3, 3, "Q"),  # 同订单两行，累计件数，不按订单COUNT
            ("德国", "A", "2026-08-15", 86, 0, "Q"),  # 同订单未退商品不能算质量退货
            ("德国", "A", "2026-08-15", 1, 1, "OTHER"),
            ("德国", "A", "2026-08-15", 2, 2, "UNCLASSIFIED"),
            ("德国", "A", "2026-08-15", 6, 6, "UNUSABLE"),  # 同一中间分类的其他小类也必须计入
            ("德国", "B", "2026-08-15", 4, 4, "Q"),
            ("英国", "A", "2026-08-15", 1, 1, "Q"),
            ("德国", "A", "2026-07-01", 7, 7, "OLD"),
            ("德国", "A", "2026-09-01", 100, 100, "Q"),  # 未完整月份排除
        ]
        db.executemany("INSERT INTO dwd_ebay_sku_analysis_order VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            (i, site, sku, month, qty, 100, 10, refund, 5,
             "已退款" if refund else "已发货", order)
            for i, (site, sku, month, qty, refund, order) in enumerate(rows, 1)
        ])
        def result():
            return {(r["site_name"], r["inventory_sku"], r["stat_month"]): dict(r)
                    for r in db.execute(sql, ("2026-06-01", "2026-09-01"))}
        data = result()
        august = data[("德国", "A", "2026-08")]
        assert august["sales_qty"] == 100
        assert august["return_qty"] == 14
        assert august["quality_return_qty"] == 11
        assert august["unclassified_return_qty"] == 2
        assert data[("德国", "B", "2026-08")]["quality_return_qty"] == 4
        assert data[("英国", "A", "2026-08")]["quality_return_qty"] == 1
        assert data[("德国", "A", "2026-07")]["quality_return_qty"] == 7
        # 中间分类不变，即使新增或改名的小类也计入，不能硬编码两个小类名称。
        db.execute("UPDATE ebay_sku_analysis_return_classification SET small_category='新的质量小类' WHERE platform_order_no='Q'")
        assert result()[("德国", "A", "2026-08")]["quality_return_qty"] == 11
        # 人工修改中间分类后即时更新，原销量和总退货量不变。
        db.execute("UPDATE ebay_sku_analysis_return_classification SET big_category='客户自身原因' WHERE platform_order_no='Q'")
        updated = result()[("德国", "A", "2026-08")]
        assert updated["quality_return_qty"] == 6
        assert updated["sales_qty"] == 100 and updated["return_qty"] == 14
        db.execute("UPDATE ebay_sku_analysis_return_classification SET big_category='其他' WHERE platform_order_no='UNUSABLE'")
        assert result()[("德国", "A", "2026-08")]["quality_return_qty"] == 0
