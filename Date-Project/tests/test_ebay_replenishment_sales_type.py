from contextlib import contextmanager
import sqlite3

import pytest
from pymysql.err import ProgrammingError

from backend.services import ebay_replenishment_v2_service as listing
from backend.services import ebay_replenishment_sales_type_service as service
from backend.repositories import ebay_replenishment_sales_type_repository as repo


def test_save_normalizes_keys_without_stripping_sku_prefix_and_validates(monkeypatch):
    saved = []
    monkeypatch.setattr(repo, "save", lambda *args: saved.append(args))
    result = service.save_sales_type(" 德国 ", " 2PC-BMW-001-A ", "BRUSH", "leiyongyu")
    assert saved == [("德国", "2PC-BMW-001-A", "BRUSH", "leiyongyu")]
    assert result["sales_type"] == "BRUSH"
    for bad in ("INVALID", "", None, 1):
        with pytest.raises(ValueError):
            service.save_sales_type("德国", "SKU", bad)
    with pytest.raises(ValueError):
        service.save_sales_type(" ", "SKU", "NORMAL")
    with pytest.raises(ValueError):
        service.save_sales_type("德国", "X" * 256, "NORMAL")
    assert len(saved) == 1


def install_listing_cursor(monkeypatch, error=None):
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            assert sql.count("%s") == len(params)
            calls.append((sql, list(params)))
            if error is not None and len(calls) == 1:
                raise error
        def fetchall(self): return []
        def fetchone(self): return {"total": 5}
    class Connection:
        def cursor(self): return Cursor()
    @contextmanager
    def connection():
        yield Connection()
    monkeypatch.setattr(listing, "db_connection", connection)
    monkeypatch.setattr(listing.sku_analysis_service, "_ensure_tables", lambda: None)
    return calls


def test_filter_is_before_pagination_and_out_of_range_count_uses_same_join(monkeypatch):
    calls = install_listing_cursor(monkeypatch)
    result = listing.list_replenishment(site="德国", sales_type="BRUSH", page=3, page_size=2)
    main, params = calls[0]
    assert "COALESCE(sales_type.sales_type,'NORMAL')=%s" in main
    assert main.index("COALESCE(sales_type.sales_type,'NORMAL')=%s") < main.index("LIMIT %s OFFSET %s")
    assert params[-3:] == ["BRUSH", 2, 4]
    count, count_params = calls[1]
    assert repo.TABLE_NAME in count and "COALESCE(sales_type.sales_type,'NORMAL')=%s" in count
    assert count_params[-1] == "BRUSH"
    assert result["pagination"]["total"] == 5
    assert result["sales_type_available"] is True


def test_sales_type_combines_with_derived_filters(monkeypatch):
    calls = install_listing_cursor(monkeypatch)
    monkeypatch.setattr(listing, "_assemble_items", lambda *args, **kwargs: [
        {"sku": "A", "product_level": "S", "product_nature": "新品", "sales_type": "NORMAL"},
        {"sku": "B", "product_level": "S", "product_nature": "老品", "sales_type": "NORMAL"},
        {"sku": "C", "product_level": "S", "product_nature": "新品", "sales_type": "NORMAL"},
        {"sku": "D", "product_level": "B", "product_nature": "新品", "sales_type": "NORMAL"},
    ])
    result = listing.list_replenishment(sales_type="NORMAL", product_level="S", product_nature="新品", page=2, page_size=1)
    assert "LIMIT %s OFFSET %s" not in calls[0][0]
    assert calls[0][1][-1] == "NORMAL"
    assert result["pagination"]["total"] == 2
    assert [item["sku"] for item in result["items"]] == ["C"]


def test_missing_table_retains_old_list_but_does_not_pretend_normal(monkeypatch):
    error = ProgrammingError(1146, f"Table jmh_data_platform.{repo.TABLE_NAME} doesn't exist")
    calls = install_listing_cursor(monkeypatch, error)
    result = listing.list_replenishment()
    assert result["sales_type_available"] is False
    assert "NULL AS sales_type" in calls[1][0]
    assert repo.TABLE_NAME not in calls[1][0]
    install_listing_cursor(monkeypatch, error)
    with pytest.raises(ValueError, match="配置表未部署"):
        listing.list_replenishment(sales_type="BRUSH")


def test_unrelated_database_error_is_not_hidden(monkeypatch):
    install_listing_cursor(monkeypatch, ProgrammingError(1146, "Table other_table missing"))
    with pytest.raises(ProgrammingError):
        listing.list_replenishment()


def test_join_matches_full_site_and_sku_and_defaults_unmarked_to_normal():
    with sqlite3.connect(":memory:") as db:
        db.create_collation("utf8mb4_unicode_ci", lambda a, b: (a > b) - (a < b))
        db.execute("ATTACH DATABASE ':memory:' AS jmh_data_platform")
        db.execute("CREATE TABLE base (site TEXT, sku TEXT)")
        db.execute(f"CREATE TABLE jmh_data_platform.{repo.TABLE_NAME} (site TEXT, sku TEXT, sales_type TEXT, PRIMARY KEY(site,sku))")
        db.executemany("INSERT INTO base VALUES (?,?)", [("德国", "A"), ("德国", "A-2"), ("英国", "A")])
        db.execute(f"INSERT INTO jmh_data_platform.{repo.TABLE_NAME} VALUES ('德国','A','BRUSH')")
        query = "SELECT base.site,base.sku FROM base " + repo.join_sql() + " WHERE COALESCE(sales_type.sales_type,'NORMAL')=? ORDER BY base.site,base.sku"
        assert list(db.execute(query, ("BRUSH",))) == [("德国", "A")]
        assert len(list(db.execute(query, ("NORMAL",)))) == 2
        db.execute(f"UPDATE jmh_data_platform.{repo.TABLE_NAME} SET sales_type='NORMAL' WHERE site='德国' AND sku='A'")
        assert len(list(db.execute(query, ("NORMAL",)))) == 3


@pytest.mark.parametrize("exists,error,commits,rollbacks", [
    (True, None, 1, 0),
    (False, None, 0, 1),
    (True, ProgrammingError(1146, f"Table {repo.TABLE_NAME} missing"), 0, 1),
])
def test_repository_save_is_transactional(monkeypatch, exists, error, commits, rollbacks):
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            calls.append((sql, params))
            if sql.startswith("INSERT") and error:
                raise error
        def fetchone(self): return {"1": 1} if exists else None
    class Connection:
        committed = 0
        rolled_back = 0
        def cursor(self): return Cursor()
        def commit(self): self.committed += 1
        def rollback(self): self.rolled_back += 1
    connection = Connection()
    @contextmanager
    def connect():
        yield connection
    monkeypatch.setattr(repo, "db_connection", connect)
    if exists and error is None:
        repo.save("德国", "FULL-SKU", "BRUSH", "operator")
        assert "ON DUPLICATE KEY UPDATE" in calls[-1][0]
        assert calls[-1][1] == ("德国", "FULL-SKU", "BRUSH", "operator")
    else:
        with pytest.raises(ValueError):
            repo.save("德国", "FULL-SKU", "BRUSH", "operator")
    assert connection.committed == commits and connection.rolled_back == rollbacks
