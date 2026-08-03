from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services.query_service import database_status


router = APIRouter()


@router.get("/api/health")
def health():
    try:
        return {"ok": True, **database_status()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"数据库连接失败: {exc}") from exc
