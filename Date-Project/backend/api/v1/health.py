from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.database import db_connection
from backend.schemas.responses import success_response
from backend.services.query_service import database_status


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health_v1(request: Request):
    try:
        return success_response(
            {"ok": True, **database_status()},
            request_id=request.state.request_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"数据库连接失败: {exc}") from exc


@router.get("/health/dependencies")
def health_dependencies(request: Request):
    checks = [
        _mysql_check(),
        _directory_check("export_output_dir", settings.export_output_dir),
        _lingxing_config_check(),
        _ebay_config_check(),
        _internal_token_check(),
    ]
    ok = all(check["status"] != "error" for check in checks)
    payload = {"ok": ok, "items": checks}
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "依赖检查未全部通过",
                "data": payload,
            },
        )
    return success_response(payload, request_id=request.state.request_id)


def _mysql_check() -> dict[str, Any]:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS db, VERSION() AS version")
                row = cursor.fetchone()
        return {
            "name": "mysql",
            "status": "ok",
            "database": row.get("db"),
            "version": row.get("version"),
        }
    except Exception as exc:
        return {"name": "mysql", "status": "error", "message": str(exc)}


def _directory_check(name: str, path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"name": name, "status": "ok", "path": str(path)}
    except Exception as exc:
        return {
            "name": name,
            "status": "error",
            "path": str(path),
            "message": str(exc),
        }


def _lingxing_config_check() -> dict[str, Any]:
    missing = []
    if not settings.lingxing_endpoint:
        missing.append("LINGXING_ENDPOINT")
    if not settings.lingxing_app_id:
        missing.append("LINGXING_APP_ID")
    if not settings.lingxing_app_secret:
        missing.append("LINGXING_APP_SECRET")
    return _config_check("lingxing", missing)


def _ebay_config_check() -> dict[str, Any]:
    missing = []
    if not settings.ebay_client_id:
        missing.append("EBAY_CLIENT_ID")
    if not settings.ebay_client_secret:
        missing.append("EBAY_CLIENT_SECRET")
    return _config_check("ebay", missing)


def _internal_token_check() -> dict[str, Any]:
    if settings.python_internal_api_token:
        return {"name": "python_internal_token", "status": "ok", "configured": True}
    return {
        "name": "python_internal_token",
        "status": "warning",
        "configured": False,
        "message": "未配置内部接口令牌，仅允许本机访问受保护接口",
    }


def _config_check(name: str, missing: list[str]) -> dict[str, Any]:
    if not missing:
        return {"name": name, "status": "ok", "configured": True}
    return {
        "name": name,
        "status": "error",
        "configured": False,
        "missing": missing,
    }
