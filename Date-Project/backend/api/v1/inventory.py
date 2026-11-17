from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from backend.schemas.responses import success_response
from backend.services.query_service import list_purchase_inventory


router = APIRouter(prefix="/api/v1")


@router.get("/inventory")
async def purchase_inventory_v1(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    keyword: str = Query("", max_length=200),
    available_only: bool = Query(False),
):
    try:
        data = await run_in_threadpool(
            list_purchase_inventory,
            page,
            page_size,
            keyword,
            available_only,
        )
        return success_response(data, request_id=request.state.request_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"库存列表读取失败: {exc}") from exc
