from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
