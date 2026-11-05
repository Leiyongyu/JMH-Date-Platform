"""向领星拉取数据时的店铺筛选：停止拉取 / 领星已移除的店铺排除，整月任务按停止日期保留历史月份。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from backend.repositories import inventory_report_source_repository as source_repo
from backend.repositories import shop_pull


class FakeCursor:
    def __init__(self, columns):
        self.columns = columns
        self.executed = []
        self._rows = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if "information_schema.COLUMNS" in sql:
            self._rows = [{"COLUMN_NAME": c} for c in self.columns]
        else:
            self._rows = [{"sid": "101"}, {"sid": "102"}]

    def fetchall(self):
        return self._rows


@pytest.fixture(autouse=True)
def fresh_cache():
    shop_pull.reset_cache()
    yield
    shop_pull.reset_cache()


FULL = ["sid", "pull_enabled", "pull_stop_date", "lingxing_present"]


def test_snapshot_pull_excludes_stopped_and_removed_stores():
    sql, params = shop_pull.pull_condition(FakeCursor(FULL), "jmh_data_platform")
    assert sql == " AND lingxing_present = 1 AND pull_enabled = 1" and params == ()


def test_monthly_pull_keeps_stores_stopped_after_the_month_started():
    sql, params = shop_pull.pull_condition(FakeCursor(FULL), "jmh_data_platform", month="2026-10", alias="sl")
    assert "sl.lingxing_present = 1" in sql
    assert "(sl.pull_enabled = 1 OR (sl.pull_stop_date IS NOT NULL AND sl.pull_stop_date > %s))" in sql
    assert params == (date(2026, 10, 1),)
    # 停止日期 2026-11-01：10 月（开始于 10-01）仍拉取，11 月（开始于 11-01）不再拉取
    assert date(2026, 11, 1) > date(2026, 10, 1) and not date(2026, 11, 1) > date(2026, 11, 1)


def test_missing_columns_fall_back_to_old_behaviour_and_recheck(caplog):
    cursor = FakeCursor(["sid", "status"])
    assert shop_pull.pull_condition(cursor, "jmh_data_platform") == ("", ())
    assert any("20261105_shop_pull_control.sql" in r.getMessage() for r in caplog.records)
    # 迁移执行后不用重启：下一次重新检查字段
    assert shop_pull.pull_condition(FakeCursor(FULL), "jmh_data_platform")[0]
    cached = FakeCursor([])
    assert shop_pull.pull_condition(cached, "jmh_data_platform")[0]  # 已缓存「有字段」，不再查询
    assert cached.executed == []


def test_amazon_seller_ids_applies_month_condition(monkeypatch):
    cursor = FakeCursor(FULL)

    class Connection:
        def cursor(self):
            @contextmanager
            def manager():
                yield cursor
            return manager()

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(source_repo, "db_connection", fake_connection)
    assert source_repo.amazon_seller_ids("2026-11") == ["101", "102"]
    sql, params = cursor.executed[-1]
    assert "pull_stop_date > %s" in sql and params == (date(2026, 11, 1),)
