"""Execute history grouping SQL against isolated in-memory fixtures, never production.

SQLite covers the common SELECT/aggregation behavior here; its adapter only
translates parameter markers and the MySQL transaction-isolation declaration.
"""
import sqlite3
from datetime import date

import pytest

from backend.repositories import ebay_inventory_pivot_repository as repository


class MemoryCursor:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.raw.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()

    def execute(self, query, params=None):
        self.connection.statements.append((" ".join(query.split()), params))
        if query.startswith("SET TRANSACTION"):
            return
        adapted = tuple(value.isoformat() if isinstance(value, date) else value for value in (params or ()))
        self.cursor.execute(query.replace("%s", "?"), adapted)

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        rows = [dict(row) for row in self.cursor.fetchall()]
        for row in rows:
            for key in ("stat_date", "inventory_snapshot_date"):
                if row.get(key) is not None:
                    row[key] = date.fromisoformat(row[key])
        return rows


class MemoryConnection:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return MemoryCursor(self)

    def begin(self):
        self.raw.execute("BEGIN")

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


@pytest.fixture
def history_db(monkeypatch):
    connection = MemoryConnection()
    connection.raw.execute(f"""CREATE TABLE {repository.HEADER} (
        id INTEGER PRIMARY KEY, stat_date DATE UNIQUE, stat_month TEXT,
        generated_at TEXT, inventory_snapshot_date DATE, inventory_pulled_at TEXT,
        inventory_batch_id TEXT
    )""")
    metrics = ",".join(key + " REAL" for key in repository.METRICS)
    connection.raw.execute(f"CREATE TABLE {repository.DETAIL} (snapshot_id INTEGER, owner TEXT, site TEXT,{metrics})")
    connection.raw.executemany(f"INSERT INTO {repository.HEADER} VALUES (?,?,?,?,?,?,?)", [
        (41, "2026-09-09", "2026-09", "2026-09-09T08:00:00", "2026-09-07", "2026-09-07T16:00:00", "old"),
        (42, "2026-09-16", "2026-09", "2026-09-16T08:00:00", "2026-09-14", "2026-09-14T16:00:00", "new"),
    ])
    # The deliberately bogus per-site ratios must never be added or averaged.
    rows = [
        (42, "Alice", "DE", 2, 10, 20, 1, 999, 999, None, 100, None, 1, 1),
        (42, "Alice", "UK", 3, 9, 18, 9, 999, 999, 12, None, None, 1, 1),
        (42, "Bob", "DE", 1, 6, 9, 0, 999, 999, 0, 0, 0, 0, 0),
        (41, "Alice", "DE", 1, 1, 2, 2, 999, 999, 2, 4, 0.25, 0, 0),
        (41, "Alice", "US", 1, 3, 6, 2, 999, 999, 3, 6, 0.25, 0, 0),
        (41, "Bob", "DE", 1, 2, 4, 1, 999, 999, None, None, 1, 1, 0),
    ]
    placeholders = ",".join(["?"] * (3 + len(repository.METRICS)))
    connection.raw.executemany(f"INSERT INTO {repository.DETAIL} VALUES ({placeholders})", rows)
    connection.raw.commit()
    monkeypatch.setattr(repository, "db_connection", lambda: connection)
    yield connection
    connection.raw.close()


def test_sql_owner_total_recomputes_ratios_and_sums_only_available_money(history_db):
    result = repository.read_history(owner="Alice", start_date=date(2026, 9, 16))
    total, = result["owner_totals"]
    assert (total["owner"], total["site"], total["row_type"], total["site_count"]) == (
        "Alice", "负责人汇总", "OWNER_TOTAL", 2,
    )
    assert total["sku_count"] == 5  # Site SKU counts add even if SKU names overlap.
    assert total["overseas_sellable_quantity"] == 19
    assert total["overseas_total_quantity"] == 38
    assert total["sales_qty_30d"] == 10
    assert total["in_stock_sales_ratio"] == 1.9
    assert total["total_stock_sales_ratio"] == 3.8
    assert total["overseas_sellable_value"] == 12
    assert total["overseas_total_value"] == 100
    assert total["warehouse_rent_30d_cny"] is None
    assert total["missing_price_count"] == total["missing_rent_count"] == 2
    assert total["inventory_batch_id"] == "new"
    assert total["inventory_snapshot_date"] == date(2026, 9, 14)
    assert "sort_site" not in total
    assert [row["site"] for row in result["items"]] == ["DE", "UK"]
    assert all(row["row_type"] == "DETAIL" for row in result["items"])


def test_sql_zero_sales_and_real_zero_amounts_are_preserved(history_db):
    result = repository.read_history(owner="Bob", start_date=date(2026, 9, 16))
    total, = result["owner_totals"]
    assert total["in_stock_sales_ratio"] == total["total_stock_sales_ratio"] == 0
    assert total["overseas_sellable_value"] == total["overseas_total_value"] == 0
    assert total["warehouse_rent_30d_cny"] == 0


def test_sql_owner_ratios_round_after_dividing_sums_to_six_places(history_db):
    history_db.raw.execute(f"""UPDATE {repository.DETAIL}
        SET overseas_sellable_quantity=1,overseas_total_quantity=2,sales_qty_30d=3
        WHERE snapshot_id=42 AND owner='Bob'
    """)
    history_db.raw.commit()
    total, = repository.read_history(owner="Bob", start_date=date(2026, 9, 16))["owner_totals"]
    assert total["in_stock_sales_ratio"] == 0.333333
    assert total["total_stock_sales_ratio"] == 0.666667


def test_sql_pagination_keeps_each_owner_date_group_complete(history_db):
    seen = []
    for page, expected in enumerate([(42, "Alice", 2), (42, "Bob", 1), (41, "Alice", 2), (41, "Bob", 1)], 1):
        history_db.statements.clear()
        result = repository.read_history(page=page, page_size=1)
        total, = result["owner_totals"]
        assert (total["snapshot_id"], total["owner"], len(result["items"])) == expected
        assert total["site_count"] == len(result["items"])
        assert all((row["snapshot_id"], row["owner"]) == expected[:2] for row in result["items"])
        assert result["pagination"] == {"page": page, "page_size": 1, "total": 4}
        assert result["metadata"] == {"snapshot_count": 2, "detail_count": 6,
                                      "owner_total_count": 4, "pagination_unit": "owner_date"}
        seen.extend((row["snapshot_id"], row["owner"], row["site"]) for row in result["items"])
        assert len([query for query, _ in history_db.statements if query.startswith("SELECT s.id AS")]) == 1
    assert len(set(seen)) == 6
    history_db.statements.clear()
    empty = repository.read_history(page=5, page_size=1)
    assert empty["items"] == empty["owner_totals"] == []
    assert not any(query.startswith("SELECT s.id AS") for query, _ in history_db.statements)


def test_sql_site_filter_changes_totals_and_counts_before_pagination(history_db):
    result = repository.read_history(owner="Alice", site="UK")
    total, = result["owner_totals"]
    assert total["site_count"] == 1
    assert total["sku_count"] == 3
    assert total["overseas_sellable_quantity"] == 9
    assert total["in_stock_sales_ratio"] == 1
    assert total["total_stock_sales_ratio"] == 2
    assert total["overseas_total_value"] is None
    assert result["pagination"]["total"] == 1
    assert result["metadata"]["detail_count"] == 1
    assert [row["site"] for row in result["items"]] == ["UK"]


def test_sql_sorting_uses_owner_totals_and_stable_date_owner_ties(history_db):
    result = repository.read_history(sort_field="sku_count", sort_order="desc", page_size=2)
    assert [(row["snapshot_id"], row["owner"], row["sku_count"]) for row in result["owner_totals"]] == [
        (42, "Alice", 5), (41, "Alice", 2),
    ]
    assert len(result["items"]) == 4
    result = repository.read_history(sort_field="overseas_sellable_value", sort_order="asc")
    assert [(row["snapshot_id"], row["owner"]) for row in result["owner_totals"]] == [
        (42, "Bob"), (41, "Alice"), (42, "Alice"), (41, "Bob"),
    ]  # Null money remains last, including ascending order.


@pytest.mark.parametrize("sort_field", sorted(repository.SORT_FIELDS))
def test_all_whitelisted_sorts_produce_valid_group_queries(history_db, sort_field):
    result = repository.read_history(sort_field=sort_field)
    assert len(result["owner_totals"]) == 4
    assert len(result["items"]) == 6


def test_sql_export_uses_same_totals_and_loads_every_matching_detail_once(history_db):
    result = repository.read_history(end_date=date(2026, 9, 9), paginate=False, page_size=1)
    assert len(result["owner_totals"]) == 2
    assert len(result["items"]) == 3
    assert {row["stat_date"] for row in result["items"] + result["owner_totals"]} == {date(2026, 9, 9)}
    assert all("LIMIT" not in query for query, _ in history_db.statements)
    assert len([query for query, _ in history_db.statements if query.startswith("SELECT s.id AS")]) == 1


def test_sql_empty_filter_does_not_invent_snapshots_or_groups(history_db):
    result = repository.read_history(start_date=date(2026, 9, 10), end_date=date(2026, 9, 15))
    assert result["items"] == result["owner_totals"] == []
    assert result["pagination"]["total"] == 0
    assert result["metadata"] == {"snapshot_count": 0, "detail_count": 0,
                                  "owner_total_count": 0, "pagination_unit": "owner_date"}
