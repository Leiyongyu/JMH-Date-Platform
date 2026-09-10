from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.api.v1 import weekly_inventory as api
from backend.repositories import weekly_inventory_repository as repo
from backend.services import scheduler_service as scheduler
from backend.services import weekly_inventory_regenerate_service as regenerate
from backend.services import weekly_inventory_sync_service as sync


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    day = date(2026, 9, 1)
    source = dict(sync_batch_id='existing-batch', snapshot_date=day, pulled_at=datetime(2026, 9, 1))
    groups = sync.normalize(
        [dict(wid=1,product_id=2,sku='SKU',product_total=10,purchase_price=2)], [],
        [dict(id=2,product_name='Product')],day,'existing-batch',datetime(2026,9,1))
    monkeypatch.setattr(repo, 'latest_completed_snapshot', lambda: source)
    monkeypatch.setattr(repo, 'snapshot', lambda batch: groups)
    monkeypatch.setattr(repo, 'warehouse_names', lambda: {1:'Warehouse'})
    monkeypatch.setattr(regenerate, 'export_root', lambda: tmp_path)
    begin, finish, insert, client = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(repo, 'begin_export', begin)
    monkeypatch.setattr(repo, 'finish_export', finish)
    monkeypatch.setattr(repo, 'insert_snapshot', insert)
    monkeypatch.setattr(sync, 'LingXingClient', client)
    return groups, begin, finish, insert, client, tmp_path


def test_repeat_export_keeps_source_date_and_does_not_extract_or_write_ods(prepared):
    groups, begin, finish, insert, client, root = prepared
    first = regenerate.regenerate_weekly_inventory()
    original = (root/first['file_name']).read_bytes()
    second = regenerate.regenerate_weekly_inventory()
    assert first['sync_batch_id'] == second['sync_batch_id'] == 'existing-batch'
    assert first['snapshot_date'] == second['snapshot_date'] == '2026-09-01'
    assert first['file_name'] != second['file_name']
    assert first['extract_rows'] == first['ods_rows'] == 0
    assert first['column_count'] == 25
    assert len(list(root.glob('*.xlsx'))) == 2
    assert (root/first['file_name']).read_bytes() == original
    client.assert_not_called()
    insert.assert_not_called()
    assert begin.call_args.args[-1] == 'manual_snapshot'
    assert finish.call_args.kwargs['file_name'] == second['file_name']


def test_no_successful_snapshot_rejects_without_any_writes(prepared, monkeypatch):
    groups, begin, finish, insert, client, root = prepared
    monkeypatch.setattr(repo, 'latest_completed_snapshot', lambda: None)
    with pytest.raises(ValueError, match='成功库存快照'):
        regenerate.regenerate_weekly_inventory()
    begin.assert_not_called()
    finish.assert_not_called()
    insert.assert_not_called()
    client.assert_not_called()


@pytest.mark.parametrize('damage', ['empty', 'product', 'batch', 'date'])
def test_incomplete_or_mixed_snapshot_fails_only_new_export(prepared, damage):
    groups, begin, finish, insert, client, root = prepared
    if damage == 'empty': groups['inventory'] = []
    elif damage == 'product': groups['products'] = []
    elif damage == 'batch': groups['inventory'][0]['sync_batch_id'] = 'wrong'
    else: groups['inventory'][0]['snapshot_date'] = date(2026,8,1)
    with pytest.raises(ValueError):
        regenerate.regenerate_weekly_inventory()
    assert finish.call_args.kwargs['error']
    assert finish.call_args.kwargs['file_name'] == begin.call_args.args[2]
    assert not list(root.glob('*.xlsx'))
    client.assert_not_called()
    insert.assert_not_called()


def test_finish_updates_one_filename_instead_of_entire_snapshot(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1
    @contextmanager
    def connect(): yield conn
    monkeypatch.setattr(repo, 'db_connection', connect)
    repo.finish_export('batch', file_name='only-new.xlsx', row_count=1)
    sql, params = cursor.execute.call_args.args
    assert 'AND file_name=%s' in sql
    assert params[-2:] == ('batch','only-new.xlsx')
    conn.commit.assert_called_once()


def test_latest_snapshot_orders_by_original_pull_not_regeneration(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    @contextmanager
    def connect(): yield conn
    monkeypatch.setattr(repo, 'db_connection', connect)
    repo.latest_completed_snapshot()
    sql, params = cursor.execute.call_args.args
    assert "f.status='SUCCESS'" in sql
    assert 'MAX(i.pulled_at)' in sql and 'ORDER BY pulled_at DESC' in sql
    assert 'generated_at' not in sql


def test_page_background_command_uses_snapshot_flag(monkeypatch):
    runner = MagicMock(return_value={'status':'completed'})
    monkeypatch.setattr(scheduler, 'run_scheduler_task', runner)
    api._run('request-test')
    assert runner.call_args.kwargs == dict(request_id='request-test',trigger_type='manual_snapshot',weekly_snapshot_only=True)


def test_page_rejects_no_snapshot_before_enqueue(monkeypatch):
    monkeypatch.setattr(api, '_future', None)
    monkeypatch.setattr(repo, 'latest_completed_snapshot', lambda: None)
    executor = MagicMock()
    monkeypatch.setattr(api, '_executor', executor)
    with pytest.raises(HTTPException) as error: api.run()
    assert error.value.status_code == 400
    executor.submit.assert_not_called()


def test_scheduler_reuses_global_lock_and_logs_without_calling_sync(monkeypatch):
    conn, logs, locks = MagicMock(), [], []
    @contextmanager
    def connect(): yield conn
    @contextmanager
    def locked(name):
        locks.append(name)
        yield True
    monkeypatch.setattr(scheduler.repo, 'performance_connection', connect)
    monkeypatch.setattr(scheduler.repo, 'named_lock', locked)
    monkeypatch.setattr(scheduler.repo, 'insert_scheduler_run', lambda connection,row: logs.append(row))
    sync_call = MagicMock()
    generate = MagicMock(return_value=dict(sync_batch_id='old',extract_rows=0,ods_rows=0))
    monkeypatch.setattr(scheduler, 'sync_weekly_inventory', sync_call)
    monkeypatch.setattr(scheduler, 'regenerate_weekly_inventory', generate)
    result = scheduler.run_scheduler_task(sync.TASK_CODE,trigger_type='manual_snapshot',weekly_snapshot_only=True)
    assert result['status'] == 'completed'
    assert locks == ['inventory:weekly-export']
    assert [row['status'] for row in logs] == ['running','completed']
    assert logs[-1]['extract_rows'] == logs[-1]['ods_rows'] == 0
    sync_call.assert_not_called()
    generate.assert_called_once()
