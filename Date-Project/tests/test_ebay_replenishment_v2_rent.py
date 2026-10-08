"""Replenishment rent reads the same GoodCang 30-day source as inventory detail."""
from decimal import Decimal

from backend.repositories import ebay_inventory_detail_repository as rent_repository
from backend.services import ebay_replenishment_v2_service as service


def test_replenishment_rent_uses_inventory_detail_conversion_and_suffix(monkeypatch):
    rows = [
        {"warehouse_code": "DE", "product_sku": "JMH-30001-0001",
         "bill_currency_code": "EUR", "warehouse_rent_amount": Decimal("10.25"),
         "missing_amount_rows": 0},
        {"warehouse_code": "CZ", "product_sku": "LR-30001-0001",
         "bill_currency_code": "EUR", "warehouse_rent_amount": Decimal("1.25"),
         "missing_amount_rows": 0},
        {"warehouse_code": "UK", "product_sku": "JMH-30001-0001",
         "bill_currency_code": "GBP", "warehouse_rent_amount": Decimal("2"),
         "missing_amount_rows": 0},
    ]
    monkeypatch.setattr(service.inventory_detail_repository, "read_rent_snapshot",
                        lambda: (rows, {"EUR": Decimal("7.8"), "GBP": Decimal("9")},
                                 "2026-09", 3))
    items = [
        {"site": "德国", "sku": "BMW-30001-0001"},
        {"site": "英国", "sku": "BMW-30001-0001"},
        {"site": "德国", "sku": "BMW-99999-0001"},
    ]

    service._enrich_warehouse_rent(items)

    assert [item["warehouse_rent_amount_cny"] for item in items] == ["89.700", "18", "0"]


def test_replenishment_rent_missing_source_or_rate_is_not_zero(monkeypatch):
    items = [{"site": "德国", "sku": "BMW-30001-0001"}]
    monkeypatch.setattr(service.inventory_detail_repository, "read_rent_snapshot",
                        lambda: ([], {}, None, 0))
    service._enrich_warehouse_rent(items)
    assert items[0]["warehouse_rent_amount_cny"] is None

    monkeypatch.setattr(service.inventory_detail_repository, "read_rent_snapshot",
                        lambda: ([{"warehouse_code": "DE", "product_sku": "JMH-30001-0001",
                                  "bill_currency_code": "EUR", "warehouse_rent_amount": Decimal("10"),
                                  "missing_amount_rows": 0}], {}, "2026-09", 1))
    service._enrich_warehouse_rent(items)
    assert items[0]["warehouse_rent_amount_cny"] is None


def test_rent_snapshot_reads_pull_month_rates_in_one_transaction(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, query): calls.append(query)
        def fetchone(self):
            return {"rent_row_count": 2, "rent_pull_month": "2026-09", "rent_batch_count": 1}

    class Connection:
        def cursor(self): return Cursor()
        def begin(self): calls.append("begin")
        def commit(self): calls.append("commit")
        def rollback(self): calls.append("rollback")

    from contextlib import contextmanager

    @contextmanager
    def connection(): yield Connection()

    monkeypatch.setattr(rent_repository, "db_connection", connection)
    monkeypatch.setattr(rent_repository, "_rent_rows", lambda _cursor: [{"product_sku": "JMH-1"}])
    monkeypatch.setattr(rent_repository, "_rates", lambda _cursor, month: {month: Decimal("1")})

    rows, rates, month, count = rent_repository.read_rent_snapshot()

    assert rows == [{"product_sku": "JMH-1"}]
    assert rates == {"2026-09": Decimal("1")}
    assert month == "2026-09" and count == 2
    assert calls[-1] == "commit" and "rollback" not in calls
