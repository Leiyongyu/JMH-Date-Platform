from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_ebay_tool_mount_requires_internal_token(monkeypatch) -> None:
    import backend.api.deps as deps
    import backend.main as main

    monkeypatch.setattr(
        deps,
        "settings",
        SimpleNamespace(python_internal_api_token="unit-secret"),
    )
    client = TestClient(main.create_app())

    assert client.get("/ebay-tool/api/check").status_code == 401
    assert client.get("/ebay-tool/index.html").status_code == 401
    assert client.get("/ebay-tool-api/api/check").status_code == 401

    headers = {"X-Internal-Token": "unit-secret"}
    current = client.get("/ebay-tool/api/check", headers=headers)
    assert current.status_code == 200
    assert "configured" in current.json()

    page = client.get("/ebay-tool/index.html", headers=headers)
    assert page.status_code == 200
    assert "text/html" in page.headers.get("content-type", "")

    legacy = client.get("/ebay-tool-api/api/check", headers=headers)
    assert legacy.status_code == 200

    business_error = client.get(
        "/ebay-tool/api/status/not-found", headers=headers
    )
    assert business_error.status_code == 404
    assert business_error.json() == {"error": "任务未找到"}

    validation_error = client.post(
        "/ebay-tool/api/sku/import", headers=headers
    )
    assert validation_error.status_code == 422
    assert set(validation_error.json()) == {"error"}
