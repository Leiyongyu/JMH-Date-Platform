import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import home_inventory_service as service

router = APIRouter(prefix='/api/v1/finance/home-inventory', dependencies=[Depends(require_internal_access)])
LOG = logging.getLogger(__name__)


def run(action, request):
    try:
        return success_response(action(), request_id=getattr(request.state, 'request_id', ''))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception('首页库存分析查询失败')
        raise HTTPException(500, detail='库存分析失败，请检查初始化SQL与服务日志') from exc


@router.get('/summary')
def summary(request: Request, month: str | None = None):
    return run(lambda: service.inventory_summary(month), request)


@router.get('/sku')
def sku(request: Request, month: str):
    return run(lambda: service.sku_summary(month), request)


@router.post('/sku-snapshot')
def snapshot(request: Request):
    return run(service.capture_sku, request)


@router.post('/product-nature-snapshot')
def product_nature_snapshot(request: Request):
    from backend.services.home_product_nature_service import capture_monthly
    return run(capture_monthly, request)
