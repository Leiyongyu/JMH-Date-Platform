from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import deps
from backend.api.v1 import internal_scheduler as api
from backend.services import scheduler_service as scheduler
from backend.services import ebay_store_listing_sync_service as service

def test_scheduler_dispatch_holds_global_lock(monkeypatch):
    entered = []
    @contextmanager
    def lock(name):
        entered.append(name)
        yield True
    connection = MagicMock()
    @contextmanager
    def database():
        yield connection
    monkeypatch.setattr(scheduler.repo, 'named_lock', lock)
    monkeypatch.setattr(scheduler.repo, 'performance_connection', database)
    monkeypatch.setattr(scheduler.repo, 'insert_scheduler_run', MagicMock())
    sync = MagicMock(return_value={'extract_rows': 2, 'ods_rows': 2, 'sync_batch_id': 'b'})
    monkeypatch.setattr(scheduler, 'sync_ebay_store_listings', sync)
    result = scheduler.run_scheduler_task(service.TASK_CODE)
    assert result['status'] == 'completed'
    assert entered == ['ebay:store-listing:replace']
    sync.assert_called_once()
    with pytest.raises(ValueError):
        scheduler.run_scheduler_task(service.TASK_CODE, stat_month='2026-01')


def test_endpoint_protected_and_registered(monkeypatch):
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-secret'))
    run = MagicMock(return_value={'status': 'completed'})
    monkeypatch.setattr(api, 'run_scheduler_task', run)
    app = FastAPI()
    @app.middleware('http')
    async def trace(request, call_next):
        request.state.request_id = 'test'
        return await call_next(request)
    app.include_router(api.router)
    with TestClient(app) as client:
        url = f'/api/v1/internal/scheduler/tasks/{service.TASK_CODE}/run'
        assert client.post(url, json={}).status_code == 401
        run.assert_not_called()
        assert client.post(url, json={}, headers={'X-Internal-Token': 'test-secret'}).status_code == 201
    assert service.TASK_CODE in scheduler.TASK_CODES
