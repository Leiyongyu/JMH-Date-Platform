from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import deps
from backend.api.v1 import internal_scheduler as api
from backend.services import scheduler_service as scheduler

TOKEN = {"X-Internal-Token": "test-secret"}
TASK = "currency_month_sync"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(deps, "settings", SimpleNamespace(python_internal_api_token="test-secret"))
    monkeypatch.setattr(scheduler, "_ASYNC_RUNS", {})
    app = FastAPI()

    @app.middleware("http")
    async def trace(request, call_next):
        request.state.request_id = "test"
        return await call_next(request)

    app.include_router(api.router)
    with TestClient(app) as test_client:
        yield test_client


def _gate(monkeypatch, outcome):
    """让后台执行停在闸门上，便于先观察 running 状态。"""
    gate = threading.Event()
    done = threading.Event()

    def execute(spec, context, run_id):
        gate.wait(5)
        try:
            if isinstance(outcome, Exception):
                raise outcome
            return {"run_id": run_id, "task_code": context.task_code,
                    "status": "completed", "result": outcome}
        finally:
            done.set()

    monkeypatch.setattr(scheduler, "_execute_run", execute)
    return gate, done


def _wait_finished(run_id):
    for _ in range(200):
        if scheduler._ASYNC_RUNS[run_id].get("finished_at"):
            return
        threading.Event().wait(0.01)
    raise AssertionError("后台任务未结束")


def test_async_run_reports_running_then_completed(client, monkeypatch):
    gate, _ = _gate(monkeypatch, {"extract_rows": 3})
    accepted = client.post(f"/api/v1/internal/scheduler/tasks/{TASK}/runs",
                           json={"stat_month": "2026-09"}, headers=TOKEN)
    assert accepted.status_code == 202
    run_id = accepted.json()["data"]["run_id"]

    running = client.get(f"/api/v1/internal/scheduler/runs/{run_id}", headers=TOKEN)
    assert running.status_code == 202 and running.json()["data"]["status"] == "running"

    gate.set()
    _wait_finished(run_id)
    finished = client.get(f"/api/v1/internal/scheduler/runs/{run_id}", headers=TOKEN)
    assert finished.status_code == 200
    body = finished.json()["data"]
    # 完成后的结果体与同步接口一致，Java 侧可沿用同一套校验。
    assert body["status"] == "completed" and body["result"] == {"extract_rows": 3}


@pytest.mark.parametrize("error,status", [
    (scheduler.SchedulerTaskAlreadyRunning("正在执行"), 409),
    (RuntimeError("领星超时"), 502),
])
def test_async_run_failures_map_to_status(client, monkeypatch, error, status):
    gate, _ = _gate(monkeypatch, error)
    gate.set()
    run_id = client.post(f"/api/v1/internal/scheduler/tasks/{TASK}/runs",
                         json={"stat_month": "2026-09"}, headers=TOKEN).json()["data"]["run_id"]
    _wait_finished(run_id)
    response = client.get(f"/api/v1/internal/scheduler/runs/{run_id}", headers=TOKEN)
    assert response.status_code == status


def test_invalid_arguments_rejected_before_any_run(client, monkeypatch):
    called = []
    monkeypatch.setattr(scheduler, "_execute_run", lambda *a: called.append(a))
    response = client.post("/api/v1/internal/scheduler/tasks/no_such_task/runs", json={}, headers=TOKEN)
    assert response.status_code == 400
    assert called == [] and scheduler._ASYNC_RUNS == {}


def test_unknown_run_after_restart_falls_back_to_run_table(client, monkeypatch):
    rows = {
        "lost": {"run_id": "lost", "task_code": TASK, "status": "running"},
        "done": {"run_id": "done", "task_code": TASK, "status": "completed", "extract_rows": 9},
    }
    monkeypatch.setattr(scheduler.repo, "get_scheduler_run", lambda run_id: rows.get(run_id))
    assert client.get("/api/v1/internal/scheduler/runs/lost", headers=TOKEN).status_code == 502
    done = client.get("/api/v1/internal/scheduler/runs/done", headers=TOKEN)
    assert done.status_code == 200 and done.json()["data"]["result"]["extract_rows"] == 9
    assert client.get("/api/v1/internal/scheduler/runs/nope", headers=TOKEN).status_code == 404


def test_endpoints_require_internal_token(client):
    assert client.post(f"/api/v1/internal/scheduler/tasks/{TASK}/runs", json={}).status_code == 401
    assert client.get("/api/v1/internal/scheduler/runs/x").status_code == 401
