import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services.amz_owner_sku_service import get_owner_sku_counts
from backend.api.v1.home_product_nature import nature_router

LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/finance/amz-owner-sku", dependencies=[Depends(require_internal_access)])
router.include_router(nature_router('amz'))


@router.get("/summary")
def summary(request: Request):
    try:
        return success_response(get_owner_sku_counts(), request_id=getattr(request.state, "request_id", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("AMZ负责人在售SKU统计失败")
        raise HTTPException(status_code=500, detail="AMZ负责人在售SKU统计失败，请检查服务日志") from exc
