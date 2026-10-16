from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services import ebay_replenishment_review_service as service
from backend.services import ebay_replenishment_v2_service as listing
from backend.services.ebay_replenishment_periods import rolling_periods
from backend.repositories import ebay_replenishment_review_repository as repo


def test_rollover_windows_have_exactly_90_days_and_never_include_today():
    for today in (date(2026, 10, 15), date(2026, 1, 1), date(2024, 3, 1)):
        periods = rolling_periods(today)
        days = [p['start_date'] + timedelta(days=i) for p in periods for i in range(30)]
        assert len(days) == len(set(days)) == 90
        assert min(days) == today - timedelta(days=90)
        assert max(days) == today - timedelta(days=1)
        assert all(p['end_date'] - p['start_date'] == timedelta(days=30) for p in periods)


def test_note_service_uses_canonical_site_sku_and_preserves_full_text(monkeypatch):
    calls = []
    monkeypatch.setattr(repo, 'save', lambda *args, **kwargs: calls.append((args, kwargs)))
    service.save_review(' 德国 ', 'bmw-001-002-YXR', 'operations', 0, text='完整运营备注超过5字', operator='actual')
    assert calls == [(('德国', 'BMW-001-002', 'operations', '完整运营备注超过5字', 0, 'actual'), {'confirm': False})]


@pytest.mark.parametrize('field,text,version', [('invalid', '', 0), ('operations', 'a' * 2001, 0),
                                              ('operations', '', -1), ('operations', '', True)])
def test_note_service_rejects_invalid_input(field, text, version):
    with pytest.raises(ValueError):
        service.save_review('德国', 'BMW-1-2', field, version, text, 'actual')


def fake_review_database(monkeypatch):
    state = {**repo.DEFAULTS}
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            queries.append((sql, params))
            if sql.startswith('UPDATE'):
                if 'operations_confirmed=1' in sql:
                    state.update(operations_confirmed=1, operations_confirmed_by=params[0], operations_confirmed_at='now')
                    state['operations_version'] += 1
                else:
                    field = 'operations' if 'SET operations_note' in sql else 'development'
                    state[f'{field}_note'] = params[0]
                    state[f'{field}_version'] += 1
                    if field == 'operations':
                        assert 'operations_confirmed=0' in sql
                        state.update(operations_confirmed=0, operations_confirmed_by=None, operations_confirmed_at=None)
        def fetchone(self): return dict(state)
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
        def rollback(self): pass
    @contextmanager
    def connect(): yield Connection()
    monkeypatch.setattr(repo, 'db_connection', connect)
    return state, queries


def test_confirmation_conflicts_and_editing_notes_do_not_overwrite_other_field(monkeypatch):
    state, queries = fake_review_database(monkeypatch)
    repo.save('德国', 'BMW-1-2', 'operations', '运营备注', 0, 'ops')
    repo.save('德国', 'BMW-1-2', 'operations', '', 1, 'ops', confirm=True)
    assert state['operations_confirmed'] == 1
    assert state['operations_version'] == 2
    repo.save('德国', 'BMW-1-2', 'development', '开发备注', 0, 'dev')
    assert state['operations_note'] == '运营备注'
    assert state['operations_confirmed'] == 1
    with pytest.raises(ValueError, match='其他人修改'):
        repo.save('德国', 'BMW-1-2', 'operations', '旧页面覆盖', 1, 'ops')
    repo.save('德国', 'BMW-1-2', 'operations', '运营更新', 2, 'ops')
    assert state['operations_confirmed'] == 0
    assert state['development_note'] == '开发备注'
    assert any('FOR UPDATE' in sql for sql, _ in queries)


def test_confirmation_filter_applies_before_pagination_and_export(monkeypatch):
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params):
            assert sql.count('%s') == len(params)
            statements.append((sql, params))
        def fetchall(self): return []
    class Connection:
        def cursor(self): return Cursor()
    @contextmanager
    def connect(): yield Connection()
    monkeypatch.setattr(listing, 'db_connection', connect)
    monkeypatch.setattr(listing.sku_analysis_service, '_ensure_tables', lambda: None)
    listing.list_replenishment(operations_confirmed=True, page_size=50)
    assert 'COALESCE(review.operations_confirmed,0)=%s' in statements[0][0]
    assert statements[0][1][-3:] == [1, 50, 0]
    statements.clear()
    listing.list_replenishment(operations_confirmed=False, paginate=False)
    assert 'LIMIT %s OFFSET' not in statements[0][0]
    assert statements[0][1][-1] == 0


def test_review_api_auth_payload_and_confirmation_filter(monkeypatch):
    from backend.api import deps
    from backend.api.v1 import ebay_replenishment_v2 as api
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-internal'))
    calls = []
    monkeypatch.setattr(service, 'save_review', lambda **kwargs: calls.append(kwargs) or {'operations_confirmed': True})
    app = FastAPI()
    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = 'test'
        return await call_next(request)
    app.include_router(api.router)
    headers = {'X-Internal-Token': 'test-internal'}
    payload = {'site': '德国', 'sku': 'BMW-1-2', 'expected_version': 0, 'operator': 'actual'}
    with TestClient(app) as client:
        url = '/api/v1/finance/ebay-replenishment-v2/review/confirm'
        assert client.post(url, json=payload).status_code == 401
        assert client.post(url, headers=headers, json=payload).status_code == 200
        assert calls[-1]['confirm'] is True
        assert calls[-1]['field'] == 'operations'
        assert client.post(url, headers=headers, json={**payload, 'expected_version': True}).status_code == 422
        note_url = '/api/v1/finance/ebay-replenishment-v2/review/note'
        assert client.post(note_url, headers=headers, json={**payload, 'field': 'development', 'text': '长备注'}).status_code == 200
        assert client.post(note_url, headers=headers, json={**payload, 'field': 'development', 'text': 'a' * 2001}).status_code == 422
