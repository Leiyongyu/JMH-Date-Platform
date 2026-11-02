from __future__ import annotations

import json

import pytest

from backend.services import data_quality as dq


def _history(*extracts):
    return [{"extract_rows": value} for value in extracts]


def test_normal_run_has_no_issues():
    result = {"extract_rows": 1000, "skipped_rows": 10}
    assert dq.evaluate("any_task", result, _history(950, 1020, 990)) == []


def test_skip_ratio_over_limit_blocks():
    issues = dq.evaluate("any_task", {"extract_rows": 1000, "skipped_rows": 80}, [])
    assert [(i.rule, i.severity) for i in issues] == [("skip_ratio", "block")]
    assert "8.0%" in issues[0].message


def test_small_batches_skip_ratio_checks():
    # 只有 20 行时 50% 跳过没有统计意义，不应误报。
    assert dq.evaluate("any_task", {"extract_rows": 20, "skipped_rows": 10}, []) == []


def test_empty_extract_after_history_blocks():
    issues = dq.evaluate("any_task", {"extract_rows": 0}, _history(5, 6, 7))
    assert [i.rule for i in issues] == ["empty_extract"]


def test_volume_drop_and_spike_against_median():
    drop = dq.evaluate("any_task", {"extract_rows": 300}, _history(1000, 1100, 900, 50000))
    assert [(i.rule, i.severity) for i in drop] == [("volume_drop", "block")]
    spike = dq.evaluate("any_task", {"extract_rows": 5000}, _history(1000, 1000, 1000))
    assert [(i.rule, i.severity) for i in spike] == [("volume_spike", "warn")]


def test_task_overrides_and_skip():
    assert dq.evaluate("feishu_bad_transaction_sync", {"extract_rows": 200}, _history(1000, 1000)) == []
    assert dq.evaluate("ebay_token_health_check", {"extract_rows": 0}, _history(10)) == []


class _Repo:
    def __init__(self, history=None, fail_history=False, fail_insert=False):
        self.history = history or []
        self.fail_history = fail_history
        self.fail_insert = fail_insert
        self.saved = []

    def recent_completed_runs(self, task_code, limit):
        if self.fail_history:
            raise RuntimeError("db down")
        return self.history

    def insert_quality_check(self, run_id, task_code, status, issues_json):
        if self.fail_insert:
            raise RuntimeError("table missing")
        self.saved.append((run_id, task_code, status, json.loads(issues_json)))


def test_warn_mode_records_but_does_not_raise(monkeypatch):
    monkeypatch.setenv("DATA_QUALITY_MODE", "warn")
    repo = _Repo(_history(1000, 1000, 1000))
    issues = dq.check("t", "run-1", {"extract_rows": 0}, repo)
    assert [i.rule for i in issues] == ["empty_extract"]
    assert repo.saved[0][:3] == ("run-1", "t", "failed")
    assert repo.saved[0][3][0]["rule"] == "empty_extract"


def test_block_mode_raises_staged_error(monkeypatch):
    monkeypatch.setenv("DATA_QUALITY_MODE", "block")
    result = {"extract_rows": 0, "sync_batch_id": "b"}
    with pytest.raises(dq.DataQualityError) as error:
        dq.check("t", "run-1", result, _Repo(_history(1000)))
    assert error.value.stage == "QUALITY"
    assert error.value.metrics is result


def test_block_mode_still_passes_warnings(monkeypatch):
    monkeypatch.setenv("DATA_QUALITY_MODE", "block")
    issues = dq.check("t", "run-1", {"extract_rows": 9000}, _Repo(_history(1000, 1000)))
    assert [i.severity for i in issues] == ["warn"]


def test_check_infrastructure_failures_never_fail_the_task(monkeypatch):
    monkeypatch.setenv("DATA_QUALITY_MODE", "block")
    repo = _Repo(fail_history=True, fail_insert=True)
    assert dq.check("t", "run-1", {"extract_rows": 1000, "skipped_rows": 0}, repo) == []


def test_off_mode_skips_everything(monkeypatch):
    monkeypatch.setenv("DATA_QUALITY_MODE", "off")
    repo = _Repo(_history(1000))
    assert dq.check("t", "run-1", {"extract_rows": 0}, repo) == []
    assert repo.saved == []
