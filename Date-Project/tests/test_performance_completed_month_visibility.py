from contextlib import contextmanager
from datetime import date

from backend.repositories import performance_repository as repo


class _Cursor:
    def __init__(self, one=None, all_rows=None):
        self.one = one
        self.all_rows = all_rows or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.one

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


def test_september_first_defaults_to_august_complete_natural_month():
    assert repo.last_complete_stat_month(date(2026, 9, 1)) == "2026-08"


def test_latest_default_ranking_month_excludes_current_incomplete_month(monkeypatch):
    cursor = _Cursor(one={"stat_month": "2026-08"})
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))
    monkeypatch.setattr(repo, "last_complete_stat_month", lambda: "2026-08")

    assert repo.latest_ranking_month("ebay") == "2026-08"
    sql, params = cursor.calls[0]
    assert "WHERE stat_month <= %s" in sql
    assert params == ("2026-08",)


def test_month_dropdown_query_excludes_current_incomplete_month(monkeypatch):
    cursor = _Cursor(all_rows=[])
    monkeypatch.setattr(repo, "db_connection", _fake_connection(cursor))
    monkeypatch.setattr(repo, "last_complete_stat_month", lambda: "2026-08")

    assert repo.months_status(60) == []
    sql, params = cursor.calls[0]
    assert "WHERE stat_month <= %s" in sql
    assert params == ("2026-08", 60)
