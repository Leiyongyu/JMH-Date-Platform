"""Internal month-end snapshot endpoint for the home product-nature charts."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services.home_product_nature_service import capture_monthly

router = APIRouter(
    prefix="/api/v1/finance/product-nature",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)


@router.post("/snapshot")
def capture_snapshot(request: Request):
    try:
        return success_response(
            capture_monthly(), request_id=getattr(request.state, "request_id", "")
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("首页商品性质月末快照采集失败")
        raise HTTPException(500, detail="商品性质月末快照采集失败，请检查服务日志") from exc
