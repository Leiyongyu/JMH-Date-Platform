"""谷仓区域仓库存同步：V1 分页校验、空快照保护、单事务整表替换、调度注册、迁移脚本。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from backend.config import PROJECT_ROOT
from backend.integrations.goodcang import client as gc_client
from backend.services import goodcang_product_inventory_sync_service as svc
from backend.services import scheduler_service
from backend.sql_statements import split_sql_statements

MIGRATION = PROJECT_ROOT / "migrations" / "20261110_goodcang_product_inventory.sql"


def item(wh, sku, sellable=1, **extra):
    return {"warehouse_code": wh, "warehouse_desc": f"{wh}区", "product_sku": sku,
            "product_title": "t", "sellable": sellable, "reserved": 0, "onway": 2,
            "transfer_onway": 0, "total_onway": 2, "pending": 0, "unsellable": 0, **extra}


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def fetch_product_inventory_page(self, page, warehouse_codes=None):
        self.calls.append(page)
        return self.pages[page - 1]


def run(pages, replaced=None):
    replaced = replaced if replaced is not None else []
    client = FakeClient(pages)

    def replace(rows):
        replaced.append(rows)
        return {"ods_rows": len(rows), "inserted_rows": len(rows), "deleted_rows": 7}

    result = svc.sync_goodcang_product_inventory(client_factory=lambda: client, replace=replace)
    return result, replaced, client


def page(data, count):
    return {"ask": "Success", "message": "ok", "count": count, "data": data}


def test_full_pull_replaces_table_once_and_reports_per_warehouse(monkeypatch):
    monkeypatch.setattr(svc, "INVENTORY_PAGE_SIZE", 2)
    pages = [page([item("DE", "JMH-1-1", 5), item("UK", "JMH-1-1", 3)], 5),
             page([item("USEA", "JMH-2-2", 1), item("CZ", "JMH-3-3", 0)], 5),
             page([item("USWE", "JMH-2-2", None, reserved=None)], 5)]
    result, replaced, client = run(pages)
    assert client.calls == [1, 2, 3]
    assert len(replaced) == 1 and len(replaced[0]) == 5, "整表只替换一次"
    assert result["extract_rows"] == result["ods_rows"] == 5
    assert result["sync_batch_id"] and result["deleted_rows"] == 7
    assert result["warehouse_counts"] == {"CZ": 1, "DE": 1, "UK": 1, "USEA": 1, "USWE": 1}
    assert result["warehouse_sellable"]["DE"] == 5
    last = replaced[0][-1]
    assert last["sellable"] is None and last["reserved"] is None, "缺值留 NULL，不补零"
    assert last["pi_freeze"] is None
    assert '"product_sku":"JMH-2-2"' in last["raw_json"]


@pytest.mark.parametrize("pages,message", [
    ([page([], 0)], "空快照"),
    ([page(None, 0)], "空快照"),
    ([{"ask": "Failure", "message": "x", "count": 0, "data": []}], "ask=Success"),
    ([page([item("DE", "JMH-1-1")], 3)], "分页提前结束"),
    ([page([item("DE", "JMH-1-1"), item("DE", "JMH-1-1")], 2)], "重复"),
    ([page([item("DE", "JMH-1-1", "1.5")], 1)], "整数"),
    ([page([item("", "JMH-1-1")], 1)], "缺少"),
])
def test_invalid_or_empty_snapshot_fails_without_replacing(pages, message):
    replaced = []
    with pytest.raises(svc.GoodcangProductInventorySyncError) as error:
        run(pages, replaced)
    assert message in str(error.value)
    assert error.value.stage == "EXTRACT"
    assert replaced == [], "失败时不替换表"


def test_count_changing_between_pages_fails(monkeypatch):
    monkeypatch.setattr(svc, "INVENTORY_PAGE_SIZE", 1)
    replaced = []
    with pytest.raises(svc.GoodcangProductInventorySyncError, match="count发生变化"):
        run([page([item("DE", "JMH-1-1")], 3), page([item("DE", "JMH-1-2")], 4)], replaced)
    assert replaced == []


def test_null_data_after_all_rows_ends_paging(monkeypatch):
    monkeypatch.setattr(svc, "INVENTORY_PAGE_SIZE", 1)
    result, replaced, client = run([page([item("DE", "JMH-1-1")], 2), page([item("UK", "JMH-1-1")], 2)])
    assert result["extract_rows"] == 2 and client.calls == [1, 2]


class FakeCursor:
    def __init__(self, log, stored):
        self.log, self.stored, self.rowcount = log, stored, 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.log.append(sql.split()[0])
        if sql.startswith("DELETE"):
            self.rowcount = 9

    def executemany(self, sql, rows):
        self.log.append(f"INSERT×{len(rows)}")

    def fetchone(self):
        return {"n": self.stored}


class FakeConnection:
    def __init__(self, stored):
        self.log = []
        self.stored = stored

    def begin(self):
        self.log.append("BEGIN")

    def cursor(self):
        return FakeCursor(self.log, self.stored)

    def commit(self):
        self.log.append("COMMIT")

    def rollback(self):
        self.log.append("ROLLBACK")


def _rows(n):
    return [svc._row(item("DE", f"JMH-1-{i}"), batch_id="b", pulled_at=date(2026, 11, 10)) for i in range(n)]


def test_replace_is_one_transaction_delete_then_insert(monkeypatch):
    connection = FakeConnection(stored=501)

    @contextmanager
    def fake_db():
        yield connection

    monkeypatch.setattr(svc, "db_connection", fake_db)
    result = svc.replace_snapshot(_rows(501))
    assert connection.log == ["BEGIN", "DELETE", "INSERT×500", "INSERT×1", "SELECT", "COMMIT"]
    assert result == {"ods_rows": 501, "inserted_rows": 501, "deleted_rows": 9}


def test_replace_rolls_back_when_row_count_does_not_match(monkeypatch):
    connection = FakeConnection(stored=3)

    @contextmanager
    def fake_db():
        yield connection

    monkeypatch.setattr(svc, "db_connection", fake_db)
    with pytest.raises(ValueError, match="行数校验失败"):
        svc.replace_snapshot(_rows(4))
    assert connection.log[-1] == "ROLLBACK" and "COMMIT" not in connection.log


def test_load_failure_is_staged_as_load():
    def broken(rows):
        raise RuntimeError("db down")

    client = FakeClient([page([item("DE", "JMH-1-1")], 1)])
    with pytest.raises(svc.GoodcangProductInventorySyncError) as error:
        svc.sync_goodcang_product_inventory(client_factory=lambda: client, replace=broken)
    assert error.value.stage == "LOAD"
    assert error.value.metrics["extract_rows"] == 1


def test_client_requests_inventory_path_with_200_per_page(monkeypatch):
    seen = {}

    def fake_request(self, path, body, page, context=""):
        seen.update(path=path, body=body, page=page)
        return {"ask": "Success"}

    monkeypatch.setattr(gc_client.GoodcangClient, "_request_page", fake_request)
    instance = gc_client.GoodcangClient.__new__(gc_client.GoodcangClient)
    instance.fetch_product_inventory_page(3, ["DE", "UK"])
    assert seen == {"path": "/inventory/get_product_inventory",
                    "body": {"page": 3, "pageSize": 200, "warehouse_code_arr": ["DE", "UK"]}, "page": 3}


def test_scheduler_registers_task_with_its_own_lock():
    spec = scheduler_service.TASK_SPECS["goodcang_product_inventory_sync"]
    assert spec.name == "谷仓区域仓库存同步"
    assert spec.lock_name(None) == "goodcang:product-inventory:replace"
    assert svc.GoodcangProductInventorySyncError in scheduler_service._STAGED_ERRORS
    for args in (("2026-10", None, None), (None, date(2026, 10, 1), None), (None, None, date(2026, 10, 31))):
        with pytest.raises(ValueError, match="不接受历史月份或日期"):
            scheduler_service._prepare_run("goodcang_product_inventory_sync", *args, "req", "job", False)


def test_migration_only_creates_the_ods_table_with_every_loaded_column():
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [s.strip() for s in split_sql_statements(sql) if s.strip()]
    creates = [s for s in statements if "CREATE TABLE" in s.upper()]
    assert len(creates) == 1 and "CREATE TABLE IF NOT EXISTS `ods_goodcang_product_inventory_latest`" in creates[0]
    upper = sql.upper()
    for forbidden in ("DROP ", "ALTER ", "TRUNCATE", "INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in upper
    for column in svc.COLUMNS:
        assert f"`{column}`" in sql, column
    assert "UNIQUE KEY `uk_gc_inventory_wh_sku` (`warehouse_code`, `product_sku`)" in sql
