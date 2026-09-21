import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from backend.api.deps import require_internal_access
from backend.repositories.listing_price_tier_repository import ReportBusy
from backend.schemas.responses import success_response
from backend.services.ebay_price_tier_service import read_report, refresh_report

LOG = logging.getLogger(__name__)
router = APIRouter(prefix='/api/v1/finance/ebay-price-tier', dependencies=[Depends(require_internal_access)])


def _run(action, request):
    try:
        return success_response(action(), request_id=getattr(request.state, 'request_id', ''))
    except ReportBusy as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception('eBay美元价格分层报表失败')
        raise HTTPException(500, detail='价格分层报表失败，请检查统计表是否初始化及服务日志') from exc


@router.get('/summary')
def summary(request: Request):
    return _run(read_report, request)


@router.post('/refresh')
def refresh(request: Request):
    return _run(refresh_report, request)
