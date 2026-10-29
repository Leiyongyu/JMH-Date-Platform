import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1 import ebay_replenishment_v2 as api
from backend.api.deps import require_internal_access
from backend.services.replenishment_data_scope import owner_predicate, request_scope


def test_parameterized_exact_owner_predicate():
    assert owner_predicate('owner', None) == ('1=1', [])
    assert owner_predicate('owner', []) == ('1=0', [])
    sql, args = owner_predicate('owner', ["x' OR 1=1 --", '甲'])
    assert sql == 'BINARY TRIM(owner) IN (%s,%s)'
    assert args == ["x' OR 1=1 --", '甲']


@pytest.mark.parametrize('value', [None, '{}', 'true', '1', '[null]', '[""]', 'bad'])
def test_invalid_or_missing_scope_denies(value):
    with pytest.raises(Exception) as error:
        request_scope(value)
    assert error.value.status_code == 403


@pytest.mark.parametrize('path', ['/list', '/hierarchy', '/export-data'])
def test_http_scope_is_required_and_passed_before_query(monkeypatch, path):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None
    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = 'scope-test'
        return await call_next(request)
    from backend.services import ebay_replenishment_read_model as model
    seen = []
    def query(**kw):
        seen.append(kw)
        return {'items': []}
    monkeypatch.setattr(model, 'query', query)
    monkeypatch.setattr(api.service, 'list_replenishment', query)
    client = TestClient(app)
    endpoint = '/api/v1/finance/ebay-replenishment-v2' + path
    assert client.get(endpoint).status_code == 403
    assert not seen
    for owners in [None, [], ['甲']]:
        response = client.get(endpoint, params={'allowed_principals': json.dumps(owners), 'principal_name': '乙',
            'operations_note_filled': 'false', 'development_note_filled': 'true'})
        assert response.status_code == 200, response.text
        assert seen[-1]['allowed_principals'] == owners
        assert seen[-1]['principal_name'] == '乙'  # filter intersects; does not replace scope
        assert seen[-1]['operations_note_filled'] is False
        assert seen[-1]['development_note_filled'] is True
