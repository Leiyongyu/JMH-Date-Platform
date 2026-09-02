from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ebay_replenishment_v2_service as service


router = APIRouter(
    prefix="/api/v1/finance/ebay-replenishment-v2",
    dependencies=[Depends(require_internal_access)],
)


@router.get("/list")
def list_replenishment(
    request: Request,
    site: str | None = None,
    sku: str | None = None,
    product_name: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_field: str | None = None,
    sort_order: str | None = None,
):
    try:
        data = service.list_replenishment(
            site=site,
            sku=sku,
            product_name=product_name,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
        )
        return success_response(data, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"eBay补货2.0列表查询失败: {exc}"
        ) from exc
