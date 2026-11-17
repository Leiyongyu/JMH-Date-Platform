from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.v1 import weekly_inventory as api
from backend.repositories import weekly_inventory_repository as repo
from backend.services import weekly_inventory_delete_service as service
from backend.services.weekly_inventory_export_service import download_path


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    root = tmp_path / 'weekly_inventory'
    root.mkdir()
    path = root / 'selected.xlsx'
    path.write_bytes(b'generated-test-file')
    other = root / 'keep.xlsx'
    other.write_bytes(b'keep-this-file')
    record = dict(id=7, status='SUCCESS', file_path=str(path), file_name=path.name,
                  export_code=repo.EXPORT_CODE, sync_batch_id='retained-batch')
    locks, events = [], []
    @contextmanager
    def lock(name):
        locks.append(name)
        yield True
    def mark_pending(file_id):
        assert file_id == 7 and path.exists()
        events.append('pending')
        record['status'] = 'DELETE_PENDING'
    def mark_deleted(file_id):
        assert file_id == 7 and not path.exists()
        events.append('deleted')
        record['status'] = 'DELETED'
    lookup = MagicMock(side_effect=lambda file_id: dict(record) if file_id == 7 else None)
    pending, deleted = MagicMock(side_effect=mark_pending), MagicMock(side_effect=mark_deleted)
    monkeypatch.setattr(service, 'export_root', lambda: root)
    monkeypatch.setattr(service, 'named_lock', lock)
    monkeypatch.setattr(repo, 'file_record', lookup)
    monkeypatch.setattr(repo, 'mark_file_delete_pending', pending)
    monkeypatch.setattr(repo, 'mark_file_deleted', deleted)
    return root, path, other, record, locks, events, lookup, pending, deleted


def test_permanent_delete_selected_file_only_and_repeat_is_safe(prepared):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    result = service.delete_weekly_inventory_file(7)
    assert result['file_id'] == 7 and not result['already_missing']
    assert not path.exists() and other.read_bytes() == b'keep-this-file'
    assert record['status'] == 'DELETED' and record['sync_batch_id'] == 'retained-batch'
    assert events == ['pending', 'deleted']
    assert locks == ['inventory:weekly-export']
    assert service.delete_weekly_inventory_file(7)['already_deleted']
    pending.assert_called_once()
    deleted.assert_called_once()
    with pytest.raises(FileNotFoundError):
        download_path(record)


def test_global_generation_lock_blocks_deletion(prepared, monkeypatch):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    @contextmanager
    def busy(name): yield False
    monkeypatch.setattr(service, 'named_lock', busy)
    with pytest.raises(service.WeeklyFileDeleteConflict):
        service.delete_weekly_inventory_file(7)
    assert path.exists()
    lookup.assert_not_called()


@pytest.mark.parametrize('status', ['RUNNING', 'FAILED', 'INTERRUPTED', 'OTHER'])
def test_only_previously_successful_files_can_be_deleted(prepared, status):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    record['status'] = status
    with pytest.raises(service.WeeklyFileDeleteConflict):
        service.delete_weekly_inventory_file(7)
    assert path.exists()
    pending.assert_not_called()


def test_missing_record_cannot_touch_files(prepared):
    with pytest.raises(FileNotFoundError): service.delete_weekly_inventory_file(99)
    assert prepared[1].exists()


@pytest.mark.parametrize('damage', ['outside', 'filename', 'suffix', 'directory', 'relative'])
def test_unsafe_registered_path_rejected_before_status_change(prepared, damage):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    if damage == 'outside':
        outside = root.parent / 'outside.xlsx'
        outside.write_bytes(b'outside')
        record.update(file_path=str(outside), file_name=outside.name)
    elif damage == 'filename': record['file_name'] = '../selected.xlsx'
    elif damage == 'suffix':
        text = root / 'secret.txt'
        text.write_text('keep', encoding='utf-8')
        record.update(file_path=str(text), file_name=text.name)
    elif damage == 'directory':
        directory = root / 'directory.xlsx'
        directory.mkdir()
        record.update(file_path=str(directory), file_name=directory.name)
    else: record['file_path'] = 'selected.xlsx'
    with pytest.raises(ValueError, match='路径不合法'):
        service.delete_weekly_inventory_file(7)
    assert path.exists() and other.exists()
    assert Path(record['file_path']).exists() or damage == 'relative'
    pending.assert_not_called()


def test_symlink_cannot_delete_its_target(prepared):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    link = root / 'link.xlsx'
    try:
        link.symlink_to(other)
    except OSError:
        pytest.skip('Creating symlinks is unavailable on this host')
    record.update(file_path=str(link), file_name=link.name)
    with pytest.raises(ValueError, match='路径不合法'):
        service.delete_weekly_inventory_file(7)
    assert other.exists() and link.is_symlink()
    pending.assert_not_called()


def test_missing_file_can_finish_pending_delete(prepared):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    record['status'] = 'DELETE_PENDING'
    path.unlink()
    assert service.delete_weekly_inventory_file(7)['already_missing']
    pending.assert_not_called()
    assert record['status'] == 'DELETED'


def test_db_intent_failure_keeps_file(prepared):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    pending.side_effect = RuntimeError('database unavailable')
    with pytest.raises(RuntimeError): service.delete_weekly_inventory_file(7)
    assert path.exists()
    deleted.assert_not_called()


def test_file_in_use_keeps_pending_intent_and_can_retry(prepared, monkeypatch):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    original = Path.unlink
    def busy(self, *args, **kwargs):
        if self == path: raise PermissionError('RAW-SECRET')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', busy)
    with pytest.raises(service.WeeklyFileDeleteConflict) as caught:
        service.delete_weekly_inventory_file(7)
    assert 'RAW-SECRET' not in str(caught.value)
    assert path.exists() and record['status'] == 'DELETE_PENDING'
    deleted.assert_not_called()
    monkeypatch.setattr(Path, 'unlink', original)
    service.delete_weekly_inventory_file(7)
    assert not path.exists() and record['status'] == 'DELETED'


def test_final_db_failure_can_retry_after_file_is_gone(prepared):
    root, path, other, record, locks, events, lookup, pending, deleted = prepared
    finish = deleted.side_effect
    deleted.side_effect = RuntimeError('database unavailable')
    with pytest.raises(RuntimeError): service.delete_weekly_inventory_file(7)
    assert not path.exists() and record['status'] == 'DELETE_PENDING'
    deleted.side_effect = finish
    assert service.delete_weekly_inventory_file(7)['already_missing']
    assert record['status'] == 'DELETED'


def test_deleted_files_hidden_from_both_count_and_list(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {'total': 0}
    cursor.fetchall.return_value = []
    @contextmanager
    def connect(): yield connection
    monkeypatch.setattr(repo, 'db_connection', connect)
    assert repo.list_files(1, 20) == {'items': [], 'total': 0}
    for call in cursor.execute.call_args_list:
        assert "status<>'DELETED'" in call.args[0]


@pytest.mark.parametrize('method,previous,status', [
    ('mark_file_delete_pending', 'SUCCESS', 'DELETE_PENDING'),
    ('mark_file_deleted', 'DELETE_PENDING', 'DELETED'),
])
def test_status_update_scoped_and_committed_without_deleting_rows(monkeypatch, method, previous, status):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1
    @contextmanager
    def connect(): yield connection
    monkeypatch.setattr(repo, 'db_connection', connect)
    getattr(repo, method)(7)
    sql, params = cursor.execute.call_args.args
    assert sql.startswith('UPDATE ops_weekly_export_file')
    assert 'WHERE export_code=%s AND id=%s AND status=%s' in sql
    assert params[0] == status and params[-3:] == (repo.EXPORT_CODE, 7, previous)
    connection.commit.assert_called_once()


def test_delete_api_requires_internal_auth_before_service(monkeypatch):
    runner = MagicMock()
    monkeypatch.setattr(api, 'delete_weekly_inventory_file', runner)
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).post('/api/v1/weekly-inventory/files/7/delete')
    assert response.status_code in (401, 403)
    runner.assert_not_called()


@pytest.mark.parametrize('error,status', [(ValueError('bad'),400), (FileNotFoundError('missing'),404),
    (service.WeeklyFileDeleteConflict('busy'),409), (RuntimeError('RAW-SECRET'),500)])
def test_api_safe_error_statuses(monkeypatch, error, status):
    monkeypatch.setattr(api, 'delete_weekly_inventory_file', MagicMock(side_effect=error))
    with pytest.raises(HTTPException) as caught: api.delete_file(7)
    assert caught.value.status_code == status
    assert 'RAW-SECRET' not in caught.value.detail
