from contextlib import contextmanager
from decimal import Decimal

from backend.repositories import inventory_report_etl_repository as repo


class _Cursor:
    def __init__(self, results, all_rows=None):
        self.results = list(results)
        self.all_rows = list(all_rows or [])
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.results.pop(0)

    def fetchall(self):
        return self.all_rows


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _fake_connection(cursor):
    @contextmanager
    def connection():
        yield _Connection(cursor)

    return connection


def test_ebay_sales_amount_reads_unified_performance_profit(monkeypatch):
    cursor = _Cursor([
        {"source_rows": 1073, "sales_amount": Decimal("2748321.42")}
    ])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))

    assert repo.ebay_sales_amount("2026-08") == Decimal("2748321.42")
    assert "FROM dwd_ebay_monthly_profit" in cursor.calls[0][0]


def test_ebay_sales_volume_prefers_profit_file_sold_quantity(monkeypatch):
    cursor = _Cursor([
        {"source_rows": 1073, "sales_volume": Decimal("7252")}
    ])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))

    assert repo.ebay_sales_volume("2026-08") == Decimal("7252")
    assert len(cursor.calls) == 1
    assert "FROM dwd_ebay_monthly_profit" in cursor.calls[0][0]


def test_ebay_sales_volume_falls_back_for_legacy_zero_month(monkeypatch):
    cursor = _Cursor([
        {"source_rows": 900, "sales_volume": Decimal("0")},
        {"source_rows": 800, "sales_volume": Decimal("5667")},
    ])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))

    assert repo.ebay_sales_volume("2026-07") == Decimal("5667")
    assert len(cursor.calls) == 2
    assert "FROM dwd_ebay_monthly_profit" in cursor.calls[0][0]
    assert ".`ebay_sales`" in cursor.calls[1][0]


def test_ebay_sales_volume_returns_none_when_both_sources_are_empty(
    monkeypatch,
):
    cursor = _Cursor([
        {"source_rows": 0, "sales_volume": Decimal("0")},
        {"source_rows": 0, "sales_volume": Decimal("0")},
    ])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))

    assert repo.ebay_sales_volume("2026-05") is None


def test_ebay_owner_actual_achievement_reads_performance_summary(monkeypatch):
    cursor = _Cursor([], [
        {
            "platform_code": "EBAY",
            "department_code": "EBAY-1",
            "principal_name": "陈丽",
            "sales_amount": Decimal("12345.67"),
        }
    ])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))

    result = repo.sales_amount_by_owner("2026-08")

    assert result[("EBAY", "EBAY-1", "陈丽")] == Decimal("12345.67")
    assert "FROM dws_ebay_performance_ranking" in cursor.calls[0][0]


def test_usd_rate_returns_none_for_missing_or_invalid_rate(monkeypatch):
    missing = _Cursor([None])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(missing))
    assert repo.usd_rate("2026-08") is None

    invalid = _Cursor([{"my_rate": Decimal("0")}])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(invalid))
    assert repo.usd_rate("2026-08") is None

    valid = _Cursor([{"my_rate": Decimal("7.1234")}])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(valid))
    assert repo.usd_rate("2026-08") == Decimal("7.1234")
