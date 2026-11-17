from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.config import settings
from backend.customs_declaration import models
from backend.customs_declaration.config import TEMPLATE_PATH
from backend.customs_declaration.models import PRODUCTS_TABLE
from backend.main import app


def _internal_headers() -> dict[str, str]:
    if settings.python_internal_api_token:
        return {"X-Internal-Token": settings.python_internal_api_token}
    return {}


def test_customs_declaration_page_is_mounted_inside_date_project() -> None:
    client = TestClient(app)
    response = client.get(
        "/customs-declaration/",
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert "报关单生成系统" in response.text
    assert 'src="/static/app.js"' in response.text


def test_customs_declaration_static_script_is_available() -> None:
    client = TestClient(app)
    response = client.get(
        "/customs-declaration/static/app.js",
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert "fetch('/api/search" in response.text
    assert "X-JMH-Customs-CSRF" in response.text
    assert response.text.count("customsPostHeaders(") == 6


def test_customs_declaration_search_api_uses_embedded_wsgi_app(monkeypatch) -> None:
    monkeypatch.setattr(
        models,
        "search_products",
        lambda keyword, limit: [{"sku": "BMW-TEST", "description_cn": "测试商品"}],
    )
    client = TestClient(app)
    response = client.get(
        "/customs-declaration/api/search?q=BMW",
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"][0]["sku"] == "BMW-TEST"


def test_customs_declaration_export_uses_packaged_excel_template() -> None:
    client = TestClient(app)
    response = client.post(
        "/customs-declaration/api/export",
        headers=_internal_headers(),
        json={
            "items": [
                {
                    "sku": "BMW-TEST",
                    "quantity": 1,
                    "unit": "个",
                    "description_cn": "测试商品",
                    "currency": "USD",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content.startswith(b"PK")


def test_customs_declaration_export_accepts_chunked_proxy_body() -> None:
    client = TestClient(app)
    payload = json.dumps(
        {
            "items": [
                {
                    "sku": "BMW-TEST",
                    "quantity": 1,
                    "unit": "个",
                    "description_cn": "测试商品",
                    "currency": "USD",
                }
            ]
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", **_internal_headers()}

    response = client.post(
        "/customs-declaration/api/export",
        headers=headers,
        content=iter((payload[:17], payload[17:])),
    )

    assert response.status_code == 200
    assert response.content.startswith(b"PK")


def test_customs_declaration_uses_packaged_template_and_shared_database() -> None:
    assert TEMPLATE_PATH.is_file()
    assert TEMPLATE_PATH.name == "customs-declaration-template.xlsx"
    assert PRODUCTS_TABLE == "`jmh_data_platform`.`products`"
