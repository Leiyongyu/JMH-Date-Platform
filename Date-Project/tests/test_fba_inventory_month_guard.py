from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from backend.services import clearance_service, scheduler_service


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 2, 12, 0, 0)
        return value if tz is None else value.replace(tzinfo=tz)


@pytest.fixture(autouse=True)
def _freeze_clearance_month(monkeypatch):
    monkeypatch.setattr(clearance_service, "datetime", _FixedDateTime)


def test_none_uses_current_natural_month():
    assert clearance_service.resolve_fba_inventory_pull_month() == "2026-09"


def test_explicit_current_month_is_allowed():
    assert (
        clearance_service.resolve_fba_inventory_pull_month("2026-09")
        == "2026-09"
    )


@pytest.mark.parametrize("pull_month", ["2026-08", "2026-10", "2025-09"])
def test_non_current_month_is_rejected(pull_month):
    with pytest.raises(ValueError) as exc_info:
        clearance_service.resolve_fba_inventory_pull_month(pull_month)

    message = str(exc_info.value)
    assert pull_month in message
    assert "2026-09" in message
    assert "不可恢复" in message


@pytest.mark.parametrize(
    "pull_month",
    ["2026-8", "202608", "abc", "2026-00", "2026-13", " 2026-09 "],
)
def test_invalid_month_format_is_rejected(pull_month):
    with pytest.raises(ValueError, match="YYYY-MM"):
        clearance_service.resolve_fba_inventory_pull_month(pull_month)


def test_historical_month_is_rejected_before_domain_or_network(monkeypatch):
    domain_instance = Mock()
    domain_factory = Mock(return_value=domain_instance)
    monkeypatch.setattr(
        clearance_service,
        "LingXingInventoryDomain",
        domain_factory,
    )

    with pytest.raises(ValueError):
        clearance_service.sync_fba_inventory("2026-08")

    domain_factory.assert_not_called()
    domain_instance.request.assert_not_called()


def test_scheduler_rejects_history_before_writing_run_log(monkeypatch):
    uuid4 = Mock()
    performance_connection = Mock()
    insert_scheduler_run = Mock()
    named_lock = Mock()
    sync_fba_inventory = Mock()
    monkeypatch.setattr(scheduler_service, "uuid4", uuid4)
    monkeypatch.setattr(
        scheduler_service.repo,
        "performance_connection",
        performance_connection,
    )
    monkeypatch.setattr(
        scheduler_service.repo,
        "insert_scheduler_run",
        insert_scheduler_run,
    )
    monkeypatch.setattr(scheduler_service.repo, "named_lock", named_lock)
    monkeypatch.setattr(
        scheduler_service,
        "sync_fba_inventory",
        sync_fba_inventory,
    )

    with pytest.raises(ValueError):
        scheduler_service.run_scheduler_task(
            scheduler_service.CLEARANCE_TASK_CODE,
            stat_month="2026-08",
        )

    uuid4.assert_not_called()
    performance_connection.assert_not_called()
    insert_scheduler_run.assert_not_called()
    named_lock.assert_not_called()
    sync_fba_inventory.assert_not_called()
