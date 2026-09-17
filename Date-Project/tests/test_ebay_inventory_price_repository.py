from decimal import Decimal
from unittest.mock import MagicMock

from pymysql.err import ProgrammingError
import pytest

from backend.repositories import ebay_inventory_price_repository as repo


def price(sku="ABC-00123-0001", value="10", middle_code="00123"):
    return {"sku": sku, "middle_code": middle_code, "unit_price": Decimal(value)}


@pytest.fixture
def storage(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    db = MagicMock(return_value=connection)
    monkeypatch.setattr(repo, "db_connection", db)
    lock = MagicMock()
    lock.return_value.__enter__.return_value = True
    monkeypatch.setattr(repo, "named_lock", lock)
    return connection, cursor, db, lock


def test_empty_import_opens_neither_lock_nor_connection(storage):
    connection, cursor, db, lock = storage
    assert repo.replace_prices([], "tester", "prices.xlsx") == 0
    lock.assert_not_called()
    db.assert_not_called()


def test_oversized_import_is_rejected_before_database(storage):
    _, _, db, lock = storage
    with pytest.raises(ValueError, match="超过50000行"):
        repo.replace_prices([price()] * 50_001, "tester", "prices.xlsx")
    lock.assert_not_called()
    db.assert_not_called()


def test_busy_import_lock_rejects_without_opening_transaction(storage):
    connection, _, db, lock = storage
    lock.return_value.__enter__.return_value = False
    with pytest.raises(ValueError, match="正在导入产品单价"):
        repo.replace_prices([price()], "tester", "prices.xlsx")
    lock.assert_called_once_with("ebay_inventory_detail_price_import")
    db.assert_not_called()
    connection.begin.assert_not_called()


def test_deletes_distinct_uploaded_full_skus_then_inserts_exact_decimal_pairs(storage):
    connection, cursor, _, lock = storage
    rows = [price(value="10.123456"), price(value="11"),
            price("IDD-LMM-310002-0047", "0", None)]
    timeline = MagicMock()
    timeline.attach_mock(connection.begin, "begin")
    timeline.attach_mock(cursor.execute, "delete")
    timeline.attach_mock(cursor.executemany, "insert")
    timeline.attach_mock(connection.commit, "commit")
    assert repo.replace_prices(rows, "tester", r"C:\upload\prices.xlsx") == 3
    assert [item[0] for item in timeline.mock_calls] == ["begin", "delete", "insert", "commit"]
    delete_sql, keys = cursor.execute.call_args.args
    assert "WHERE sku IN (%s,%s)" in delete_sql
    assert keys == ("ABC-00123-0001", "IDD-LMM-310002-0047")
    assert "middle_code" not in delete_sql
    query, inserted = cursor.executemany.call_args.args
    assert "INSERT INTO ebay_inventory_detail_price" in query
    assert len(inserted) == 3
    assert inserted[0]["unit_price"] == Decimal("10.123456")
    assert isinstance(inserted[0]["unit_price"], Decimal)
    assert inserted[2]["middle_code"] is None
    assert inserted[2]["unit_price"] == 0
    assert {row["source_file"] for row in inserted} == {"prices.xlsx"}
    assert {row["updated_by"] for row in inserted} == {"tester"}
    connection.rollback.assert_not_called()
    lock.return_value.__exit__.assert_called_once()


def test_every_delete_and_insert_batch_shares_one_transaction(storage):
    connection, cursor, _, _ = storage
    rows = [price(f"ABC-{index:05d}-0001", middle_code=f"{index:05d}") for index in range(1001)]
    assert repo.replace_prices(rows, "tester", "prices.xlsx") == 1001
    assert [len(item.args[1]) for item in cursor.execute.call_args_list] == [500, 500, 1]
    assert [len(item.args[1]) for item in cursor.executemany.call_args_list] == [500, 500, 1]
    connection.begin.assert_called_once_with()
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize("failed_operation", ["execute", "executemany"])
def test_any_delete_or_insert_failure_rolls_back_every_batch(storage, failed_operation):
    connection, cursor, _, lock = storage
    failure = RuntimeError("simulated database failure")
    getattr(cursor, failed_operation).side_effect = failure
    with pytest.raises(RuntimeError, match="simulated database failure"):
        repo.replace_prices([price()], "tester", "prices.xlsx")
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
    lock.return_value.__exit__.assert_called_once()


def test_missing_price_table_is_actionable_and_rolled_back(storage):
    connection, cursor, _, _ = storage
    failure = ProgrammingError(1146, "Table 'date-project.ebay_inventory_detail_price' doesn't exist")
    cursor.execute.side_effect = failure
    with pytest.raises(ValueError, match="先执行.*建表 SQL") as exc_info:
        repo.replace_prices([price()], "tester", "prices.xlsx")
    assert exc_info.value.__cause__ is failure
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()


def test_other_missing_tables_are_not_misreported(storage):
    connection, cursor, _, _ = storage
    failure = ProgrammingError(1146, "Table 'date-project.unrelated_table' doesn't exist")
    cursor.execute.side_effect = failure
    with pytest.raises(ProgrammingError) as exc_info:
        repo.replace_prices([price()], "tester", "prices.xlsx")
    assert exc_info.value is failure
    connection.rollback.assert_called_once_with()


def test_filename_is_basename_and_bounded(storage):
    _, cursor, _, _ = storage
    repo.replace_prices([price()], "tester", "/private/path/" + "x" * 300)
    assert cursor.executemany.call_args.args[1][0]["source_file"] == "x" * 255


def test_repeat_upload_is_idempotent_and_reprices_only_uploaded_sku(storage):
    _, cursor, _, _ = storage
    existing = {
        ("ABC-00123-0001", Decimal("5")),
        ("DEF-00123-0002", Decimal("7")),
        ("XYZ-00999-0001", Decimal("20")),
    }

    def delete(sql, keys):
        existing.difference_update([key for key in existing if key[0] in keys])

    def insert(sql, rows):
        existing.update((row["sku"], row["unit_price"]) for row in rows)

    cursor.execute.side_effect = delete
    cursor.executemany.side_effect = insert
    upload = [price(value="10"), price(value="11")]
    repo.replace_prices(upload, "tester", "prices.xlsx")
    expected = {
        ("ABC-00123-0001", Decimal("10")),
        ("ABC-00123-0001", Decimal("11")),
        ("DEF-00123-0002", Decimal("7")),
        ("XYZ-00999-0001", Decimal("20")),
    }
    assert existing == expected
    repo.replace_prices(upload, "tester", "prices.xlsx")
    assert existing == expected
