from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from backend.image_sop.app import _validate_external_url, app
from backend.image_sop.config import get_settings


def test_image_sop_routes_are_embedded() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/sop/generate" in paths
    assert "/api/sop/export" in paths
    assert "/api/ebay/parse-url" in paths
    assert "/api/nas/search" in paths


def test_image_sop_uses_mysql_and_project_output_directories() -> None:
    settings = get_settings()
    assert settings.db_path == "mysql"
    assert "image_sop" in str(settings.upload_path)
    assert "image_sop" in str(settings.export_path)


def test_external_url_guard_rejects_loopback() -> None:
    with pytest.raises(HTTPException) as error:
        asyncio.run(_validate_external_url("http://127.0.0.1/internal"))
    assert error.value.status_code == 403
