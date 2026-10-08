from unittest.mock import MagicMock

from backend.services import inventory_report_etl_service as service


def test_rebuild_replaces_only_requested_source_month(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"total": 0}
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(service.repo, "db_connection", lambda: connection)
    monkeypatch.setattr(service.repo, "_insert_rows", lambda *_args: None)

    service.repo.replace_clean_month("2026-08", [], [], [], [], [], [])

    deletes = [call.args for call in cursor.execute.call_args_list
               if call.args[0].startswith("DELETE FROM")]
    assert len(deletes) == 6
    assert all(params == ("2026-08",) for _query, params in deletes)
    connection.commit.assert_called_once()
