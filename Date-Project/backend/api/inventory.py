from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from backend.services.query_service import list_purchase_inventory


router = APIRouter()


@router.get("/api/inventory")
async def purchase_inventory(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    keyword: str = Query("", max_length=200),
    available_only: bool = Query(False),
):
    try:
        return await run_in_threadpool(
            list_purchase_inventory,
            page,
            page_size,
            keyword,
            available_only,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"库存列表读取失败: {exc}") from exc
