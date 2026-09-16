"""Offline transaction-contract cases; fake connections never reach MySQL."""
from contextlib import contextmanager

import pytest

from backend.repositories import goodcang_storage_repository as repository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        self.connection.events.append(("execute", sql))
        if sql.startswith("DELETE FROM"):
            self.rowcount = 7 if repository.DETAIL_TABLE in sql else 3

    def executemany(self, sql, rows):
        rows = list(rows)
        self.connection.events.append(("executemany", sql, rows))
        if self.connection.fail_on_detail and repository.DETAIL_TABLE in sql:
            raise RuntimeError("simulated detail insert failure")
        self.rowcount = len(rows)


class FakeConnection:
    def __init__(self, fail_on_detail=False):
        self.events = []
        self.fail_on_detail = fail_on_detail

    def begin(self):
        self.events.append(("begin",))

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.events.append(("commit",))

    def rollback(self):
        self.events.append(("rollback",))


def use_connection(monkeypatch, fail_on_detail=False):
    connection = FakeConnection(fail_on_detail=fail_on_detail)

    @contextmanager
    def open_connection():
        yield connection

    monkeypatch.setattr(repository, "db_connection", open_connection)
    return connection


def make_row(fields, number):
    row = dict.fromkeys(fields)
    row["source_row_no"] = number
    return row


def test_both_tables_replaced_in_one_transaction_with_chunked_detail_stream(monkeypatch):
    connection = use_connection(monkeypatch)
    summary_rows = [make_row(repository.FIELDS, 1)]
    consumed = []

    def detail_rows():
        for number in range(1, 502):
            consumed.append(number)
            yield make_row(repository.DETAIL_FIELDS, number)

    result = repository.replace_storage_snapshot(summary_rows, detail_rows())
    events = connection.events
    assert events[0] == ("begin",)
    assert events[-1] == ("commit",)
    assert not any(event[0] == "rollback" for event in events)
    deletes = [event for event in events if event[0] == "execute" and event[1].startswith("DELETE")]
    assert {event[1] for event in deletes} == {
        f"DELETE FROM `{repository.TABLE}`",
        f"DELETE FROM `{repository.DETAIL_TABLE}`",
    }
    assert all("TRUNCATE" not in event[1] for event in events if event[0] == "execute")
    inserts = [event for event in events if event[0] == "executemany"]
    detail_inserts = [event for event in inserts if repository.DETAIL_TABLE in event[1]]
    assert [len(event[2]) for event in detail_inserts] == [500, 1]
    assert consumed == list(range(1, 502))
    assert result["ods_rows"] == result["inserted_rows"] == 502
    assert result["deleted_rows"] == 10

def test_detail_insert_failure_rolls_back_summary_and_both_deletes(monkeypatch):
    connection = use_connection(monkeypatch, fail_on_detail=True)
    with pytest.raises(RuntimeError, match="simulated detail insert failure"):
        repository.replace_storage_snapshot(
            [make_row(repository.FIELDS, 1)],
            iter([make_row(repository.DETAIL_FIELDS, 1)]),
        )
    assert connection.events[0] == ("begin",)
    assert connection.events[-1] == ("rollback",)
    assert not any(event[0] == "commit" for event in connection.events)


def test_detail_stream_failure_rolls_back_entire_snapshot(monkeypatch):
    connection = use_connection(monkeypatch)

    def broken_rows():
        yield make_row(repository.DETAIL_FIELDS, 1)
        raise RuntimeError("simulated temporary spool failure")

    with pytest.raises(RuntimeError, match="simulated temporary spool failure"):
        repository.replace_storage_snapshot([make_row(repository.FIELDS, 1)], broken_rows())
    assert connection.events[-1] == ("rollback",)
    assert not any(event[0] == "commit" for event in connection.events)


def test_confirmed_empty_replacement_clears_both_without_insert(monkeypatch):
    connection = use_connection(monkeypatch)
    result = repository.replace_storage_snapshot([], iter(()))
    assert connection.events[0] == ("begin",)
    assert connection.events[-1] == ("commit",)
    assert len([event for event in connection.events if event[0] == "execute"]) == 2
    assert not any(event[0] == "executemany" for event in connection.events)
    assert result["ods_rows"] == result["inserted_rows"] == 0
    assert result["deleted_rows"] == 10
