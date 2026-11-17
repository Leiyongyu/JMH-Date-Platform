"""Single-batch retention tests: only in-memory DB state and temporary files."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import re
from unittest.mock import MagicMock

import pytest

from backend.repositories import weekly_inventory_repository as repo
from backend.services import weekly_inventory_export_service as export
from backend.services import weekly_inventory_sync_service as sync


DAY = date(2026, 9, 15)
BATCH = 'new-batch'
FILENAME = 'new-export.xlsx'
METRICS = dict(row_count=1, column_count=27, file_size=1024)


def complete_groups():
    return sync.normalize(
        [dict(wid=18677, product_id=2, sku='SKU', product_total=10,
              stock_age_list=[dict(name='0-29天', qty=10)])],
        [dict(wid=18677, whb_id=3, product_id=2, whb_name='A-01', total=10)],
        [dict(id=2, product_name='Product')], DAY, BATCH, datetime(2026, 9, 15),
    )


class TransactionMemory:
    """Model commit/rollback, while rejecting any SQL outside the narrow contract."""

    def __init__(self, fault=None):
        self.fault = fault
        self.state = {
            'tables': {
                table: [dict(sync_batch_id='old-week', snapshot_date=date(2026, 9, 8)),
                        dict(sync_batch_id='old-same-day', snapshot_date=DAY)]
                for table in repo.TABLES.values()
            },
            'exports': {
                'old-week.xlsx': dict(status='SUCCESS', sync_batch_id='old-week',
                                      snapshot_date=date(2026, 9, 8), row_count=10),
                'old-same-day.xlsx': dict(status='SUCCESS', sync_batch_id='old-same-day',
                                          snapshot_date=DAY, row_count=20),
                FILENAME: dict(status='RUNNING', sync_batch_id=BATCH, snapshot_date=DAY),
            },
        }
        self.pending = deepcopy(self.state)
        self.events = []
        self.open_count = self.commit_count = self.rollback_count = 0
        self.begin_count = 0
        self.insert_count = self.delete_count = 0
        self.rowcount = 0
        self.selected = None

    @contextmanager
    def connect(self):
        self.open_count += 1
        self.pending = deepcopy(self.state)
        yield self

    @contextmanager
    def cursor(self):
        yield self

    def begin(self):
        self.begin_count += 1
        self.events.append(('begin',))

    def execute(self, sql, params):
        sql = ' '.join(sql.replace('`', '').split())
        self.events.append(('execute', sql, params))
        if sql.startswith('SELECT status'):
            assert 'FROM ops_weekly_export_file ' in sql
            assert params[0] == repo.EXPORT_CODE
            record = self.pending['exports'].get(params[-1])
            self.selected = record if record and record['sync_batch_id'] == params[-2] else None
            return
        if sql.startswith('DELETE FROM '):
            match = re.fullmatch(r'DELETE FROM (\w+) WHERE sync_batch_id\s*<>\s*%s', sql)
            assert match, 'Deletion must be restricted to non-current batches'
            table = match.group(1)
            assert table in repo.TABLES.values(), 'Only the four weekly ODS tables may be pruned'
            self.delete_count += 1
            if self.fault == 'delete_second' and self.delete_count == 2:
                raise RuntimeError('injected second DELETE failure')
            previous = self.pending['tables'][table]
            current = [row for row in previous if row['sync_batch_id'] == params[0]]
            self.pending['tables'][table] = current
            self.rowcount = len(previous) - len(current)
            return
        assert sql.startswith('UPDATE ops_weekly_export_file SET '), sql
        assert 'WHERE export_code=%s AND sync_batch_id=%s AND file_name=%s' in sql
        assert params[-3] == repo.EXPORT_CODE
        success = "status='SUCCESS'" in sql
        if success and self.fault == 'update':
            raise RuntimeError('injected SUCCESS update failure')
        record = self.pending['exports'].get(params[-1])
        guarded = "AND status='RUNNING'" in sql
        self.rowcount = int(bool(record and record['sync_batch_id'] == params[-2]
                                 and (not guarded or record['status'] == 'RUNNING')))
        if success and self.fault == 'update_zero':
            self.rowcount = 0
        if self.rowcount:
            fields = re.findall(r'(\w+)=%s', sql.split(' WHERE ')[0])
            record.update(zip(fields, params))
            if success:
                record.update(status='SUCCESS', error_message=None)

    def executemany(self, sql, values):
        self.events.append(('insert', sql, values))
        self.insert_count += 1
        if self.fault == 'insert' and self.insert_count == 3:
            raise RuntimeError('injected third INSERT failure')
        match = re.fullmatch(r'INSERT INTO `(\w+)` \(([^)]+)\) VALUES \(.+\)', sql)
        assert match, sql
        table, columns = match.groups()
        assert table in repo.TABLES.values()
        columns = [column.strip('` ') for column in columns.split(',')]
        self.pending['tables'][table].extend(dict(zip(columns, values_row)) for values_row in values)
        self.rowcount = len(values)

    def fetchone(self):
        return deepcopy(self.selected)

    def commit(self):
        self.events.append(('commit',))
        self.commit_count += 1
        if self.fault == 'commit':
            raise RuntimeError('injected COMMIT failure')
        self.state = deepcopy(self.pending)
        if self.fault == 'commit_response':
            self.fault = None
            raise RuntimeError('injected lost COMMIT response')

    def rollback(self):
        self.events.append(('rollback',))
        self.rollback_count += 1
        self.pending = deepcopy(self.state)


def replace(groups=None, **changes):
    return repo.replace_snapshot_and_finish_export(
        complete_groups() if groups is None else groups,
        **dict(dict(file_name=FILENAME, **METRICS), **changes),
    )


@pytest.fixture
def memory(monkeypatch):
    connection = TransactionMemory()
    monkeypatch.setattr(repo, 'db_connection', connection.connect)
    return connection


def test_one_transaction_replaces_all_four_tables_and_keeps_archives_and_audit(memory, tmp_path):
    archive = tmp_path / 'old-week.xlsx'
    archive.write_bytes(b'old archived export')
    old_records = deepcopy(memory.state['exports'])
    result = replace()
    assert result == dict(ods_rows=4, deleted_rows=8)
    assert memory.open_count == memory.begin_count == memory.commit_count == 1
    assert memory.rollback_count == 0
    for table in repo.TABLES.values():
        assert len(memory.state['tables'][table]) == 1
        assert {row['sync_batch_id'] for row in memory.state['tables'][table]} == {BATCH}
    assert memory.state['exports'][FILENAME]['status'] == 'SUCCESS'
    assert all(memory.state['exports'][FILENAME][key] == value for key, value in METRICS.items())
    assert set(memory.state['exports']) == set(old_records)
    assert all(memory.state['exports'][name] == old_records[name]
               for name in old_records if name != FILENAME)
    assert archive.read_bytes() == b'old archived export'
    assert memory.events[0] == ('begin',)
    assert memory.events[1][1].endswith('FOR UPDATE')
    assert memory.events[1][2] == (repo.EXPORT_CODE, BATCH, FILENAME)
    inserts = [index for index, event in enumerate(memory.events) if event[0] == 'insert']
    deletes = [index for index, event in enumerate(memory.events)
               if event[0] == 'execute' and event[1].startswith('DELETE')]
    assert len(inserts) == len(deletes) == 4
    assert max(inserts) < min(deletes)
    assert all(memory.events[index][2] == (BATCH,) for index in deletes)
    assert memory.events[-2][1].startswith('UPDATE ops_weekly_export_file ')
    assert "AND status='RUNNING'" in memory.events[-2][1]
    assert memory.events[-1] == ('commit',)


@pytest.mark.parametrize('fault', ['insert', 'delete_second', 'update', 'update_zero', 'commit'])
def test_failure_restores_all_four_previous_tables_and_running_registration(memory, fault):
    before = deepcopy(memory.state)
    memory.fault = fault
    with pytest.raises(RuntimeError):
        replace()
    assert memory.state == before
    assert memory.rollback_count == 1
    assert memory.commit_count == int(fault == 'commit')
    assert memory.events[-1] == ('rollback',)
    if fault == 'insert':
        assert memory.delete_count == 0
    else:
        assert memory.insert_count == 4
    if fault == 'delete_second':
        assert memory.delete_count == 2
        assert not any(event[0] == 'execute' and event[1].startswith('UPDATE')
                       for event in memory.events)


@pytest.mark.parametrize('damage', ['missing', 'success', 'failed', 'wrong_date', 'wrong_batch'])
def test_nonrunning_or_mismatched_registration_cannot_touch_ods(memory, damage):
    if damage == 'missing':
        memory.state['exports'].pop(FILENAME)
    elif damage == 'wrong_date':
        memory.state['exports'][FILENAME]['snapshot_date'] = date(2026, 9, 8)
    elif damage == 'wrong_batch':
        memory.state['exports'][FILENAME]['sync_batch_id'] = 'another-batch'
    else:
        memory.state['exports'][FILENAME]['status'] = damage.upper()
    before = deepcopy(memory.state)
    with pytest.raises(ValueError):
        replace()
    assert memory.insert_count == memory.delete_count == memory.commit_count == 0
    assert memory.rollback_count == 1
    assert memory.state == before


@pytest.mark.parametrize('group', list(repo.TABLES))
@pytest.mark.parametrize('field,value', [('sync_batch_id', 'wrong-batch'),
                                        ('snapshot_date', date(2026, 9, 8))])
def test_mixed_batch_or_date_rejected_before_connecting(monkeypatch, group, field, value):
    groups = complete_groups()
    groups[group][0][field] = value
    connect = MagicMock(side_effect=AssertionError('invalid groups must not open DB'))
    monkeypatch.setattr(repo, 'db_connection', connect)
    with pytest.raises(ValueError):
        replace(groups)
    connect.assert_not_called()


@pytest.mark.parametrize('damage', ['empty', 'empty_inventory', 'empty_products', 'missing_group',
                                    'extra_group', 'product_coverage', 'product_id_missing',
                                    'blank_batch', 'missing_date'])
def test_incomplete_snapshots_rejected_before_connecting(monkeypatch, damage):
    groups = complete_groups()
    if damage == 'empty': groups = {}
    elif damage == 'empty_inventory': groups['inventory'] = []
    elif damage == 'empty_products': groups['products'] = []
    elif damage == 'missing_group': groups.pop('age')
    elif damage == 'extra_group': groups['unrelated_table'] = []
    elif damage == 'product_coverage': groups['inventory'][0]['product_id'] = 999
    elif damage == 'product_id_missing': groups['products'][0]['product_id'] = None
    elif damage == 'blank_batch':
        for rows in groups.values():
            for row in rows: row['sync_batch_id'] = '  '
    elif damage == 'missing_date':
        for rows in groups.values():
            for row in rows: row['snapshot_date'] = None
    connect = MagicMock(side_effect=AssertionError('invalid groups must not open DB'))
    monkeypatch.setattr(repo, 'db_connection', connect)
    with pytest.raises(ValueError):
        replace(groups)
    connect.assert_not_called()


@pytest.mark.parametrize('field', list(METRICS))
@pytest.mark.parametrize('value', [None, 0, -1, True, False, 1.5, '1', Decimal('1')])
def test_excel_metrics_must_be_positive_integers_before_connecting(monkeypatch, field, value):
    connect = MagicMock(side_effect=AssertionError('unfinished export must not open DB'))
    monkeypatch.setattr(repo, 'db_connection', connect)
    with pytest.raises(ValueError):
        replace(**{field: value})
    connect.assert_not_called()


def test_missing_filename_rejected_before_connecting(monkeypatch):
    connect = MagicMock(side_effect=AssertionError('missing file must not open DB'))
    monkeypatch.setattr(repo, 'db_connection', connect)
    with pytest.raises(ValueError):
        replace(file_name='')
    connect.assert_not_called()


def test_legitimate_empty_age_and_bins_still_prune_their_previous_rows(memory):
    groups = complete_groups()
    groups['age'] = []
    groups['bins'] = []
    assert replace(groups) == dict(ods_rows=2, deleted_rows=8)
    assert memory.delete_count == 4
    assert memory.state['tables'][repo.TABLES['age']] == []
    assert memory.state['tables'][repo.TABLES['bins']] == []


def test_insert_column_inconsistency_rolls_back_without_pruning(memory):
    groups = complete_groups()
    groups['products'].append({**groups['products'][0], 'product_id': 3, 'unexpected': 'field'})
    before = deepcopy(memory.state)
    with pytest.raises(ValueError, match='字段不一致'):
        replace(groups)
    assert memory.state == before
    assert memory.delete_count == memory.commit_count == 0
    assert memory.rollback_count == 1


def test_lost_commit_response_cannot_downgrade_committed_success(memory):
    memory.fault = 'commit_response'
    with pytest.raises(RuntimeError, match='lost COMMIT response'):
        replace()
    committed = deepcopy(memory.state)
    assert committed['exports'][FILENAME]['status'] == 'SUCCESS'
    repo.finish_export(BATCH, file_name=FILENAME, error='caller saw uncertain COMMIT')
    assert memory.state == committed
    failure_updates = [event for event in memory.events
                       if event[0] == 'execute' and event[1].startswith('UPDATE')
                       and event[2][0] == 'FAILED']
    assert len(failure_updates) == 1
    assert "AND status='RUNNING'" in failure_updates[0][1]


def test_failure_registration_updates_running_only_and_keeps_prior_snapshot(memory):
    previous_tables = deepcopy(memory.state['tables'])
    repo.finish_export(BATCH, file_name=FILENAME, error='Excel generation failed')
    assert memory.state['exports'][FILENAME]['status'] == 'FAILED'
    assert memory.state['tables'] == previous_tables
    assert memory.insert_count == memory.delete_count == 0


def test_new_extraction_excel_failure_never_replaces_or_reads_snapshot(monkeypatch, tmp_path):
    archive = tmp_path / 'previous.xlsx'
    archive.write_bytes(b'previous successful workbook')
    client = MagicMock()
    client.post_signed_query_auth.side_effect = [
        dict(code=0, total=1, data=[dict(wid=18677, product_id=2, product_total=10)]),
        dict(code=0, total=0, data=[]),
        dict(code=0, data=[dict(id=2, product_name='Product')]),
    ]
    monkeypatch.setattr(sync, 'LingXingClient', lambda **kwargs: client)
    monkeypatch.setattr(repo, 'require_bin_identity_schema', MagicMock())
    begin, finish, publish, snapshot = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(repo, 'begin_export', begin)
    monkeypatch.setattr(repo, 'finish_export', finish)
    monkeypatch.setattr(repo, 'replace_snapshot_and_finish_export', publish)
    monkeypatch.setattr(repo, 'snapshot', snapshot)
    monkeypatch.setattr(repo, 'warehouse_names', lambda: {18677: 'Warehouse'})
    monkeypatch.setattr(export, 'export_root', lambda: tmp_path)
    writer = MagicMock(side_effect=OSError('injected Excel disk full'))
    monkeypatch.setattr(export, 'write_export', writer)
    no_database = MagicMock(side_effect=AssertionError('no real DB is allowed'))
    monkeypatch.setattr(repo, 'db_connection', no_database)
    with pytest.raises(OSError, match='Excel disk full'):
        sync.sync_weekly_inventory()
    publish.assert_not_called()
    snapshot.assert_not_called()
    no_database.assert_not_called()
    finish.assert_called_once()
    assert finish.call_args.kwargs['error']
    assert finish.call_args.kwargs['file_name'] == begin.call_args.args[2]
    groups = writer.call_args.args[0]
    assert set(groups) == set(repo.TABLES)
    assert groups['inventory'][0]['product_id'] == 2
    assert list(tmp_path.glob('*.xlsx')) == [archive]
    assert archive.read_bytes() == b'previous successful workbook'
