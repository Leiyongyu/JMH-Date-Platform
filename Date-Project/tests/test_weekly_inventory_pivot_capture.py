"""Post-publish history is distinct from extraction and its failure registration."""
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from backend.services import weekly_inventory_sync_service as sync


@pytest.fixture
def history_capture(monkeypatch):
    module = ModuleType('backend.services.ebay_inventory_pivot_service')
    capture = MagicMock(return_value={
        'snapshot_id': 42, 'stat_date': '2026-09-16', 'group_count': 3, 'item_count': 100,
    })
    module.capture_snapshot = capture
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return capture


@pytest.mark.parametrize('trigger_type', ['JOB', 'manual'])
def test_history_capture_runs_after_source_publish_with_exact_batch(monkeypatch, history_capture, trigger_type):
    published = {'sync_batch_id': 'validated-batch', 'ods_rows': 150, 'row_count': 60}
    events = []

    def publish(trigger):
        events.append(('publish', trigger))
        return published.copy()

    def capture(**kwargs):
        assert events == [('publish', trigger_type)]
        events.append(('capture', kwargs))
        return {'snapshot_id': 42, 'group_count': 3}

    monkeypatch.setattr(sync, '_sync_weekly_inventory_sources', publish)
    history_capture.side_effect = capture
    result = sync.sync_weekly_inventory(trigger_type)

    history_capture.assert_called_once_with(
        expected_inventory_batch='validated-batch', trigger_type=trigger_type,
    )
    assert result == {**published, 'pivot_snapshot': {'snapshot_id': 42, 'group_count': 3}}


def test_source_failure_never_attempts_history(monkeypatch, history_capture):
    failure = ValueError('incomplete source snapshot')
    publisher = MagicMock(side_effect=failure)
    monkeypatch.setattr(sync, '_sync_weekly_inventory_sources', publisher)
    with pytest.raises(ValueError) as error:
        sync.sync_weekly_inventory()
    assert error.value is failure
    history_capture.assert_not_called()


def test_history_failure_explicitly_reports_partial_success_without_failure_rewrite(
    monkeypatch, history_capture, caplog,
):
    publisher = MagicMock(return_value={'sync_batch_id': 'committed-batch'})
    failure_registration = MagicMock()
    monkeypatch.setattr(sync, '_sync_weekly_inventory_sources', publisher)
    monkeypatch.setattr(sync.repo, 'finish_export', failure_registration)
    history_capture.side_effect = RuntimeError('internal database detail not for client')

    with pytest.raises(ValueError, match='库存和Excel已成功发布，但历史透视保存失败') as error:
        sync.sync_weekly_inventory()

    assert 'committed-batch' in str(error.value)
    assert '已有历史保留' in str(error.value)
    assert 'internal database detail' not in str(error.value)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert 'Weekly inventory published but pivot history failed' in caplog.text
    failure_registration.assert_not_called()
    publisher.assert_called_once_with('JOB')
