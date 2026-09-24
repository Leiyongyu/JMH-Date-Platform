import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from backend.api.deps import require_internal_access
from backend.repositories.listing_price_tier_repository import ReportBusy
from backend.schemas.responses import success_response
from backend.services.ebay_price_tier_service import product_structure, read_report, refresh_report

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
def summary(request: Request, month: str = '', shop: str = ''):
    """month 为空取最新统计月份；shop 为空返回全部店铺。"""
    return _run(lambda: read_report(month, shop), request)


@router.post('/refresh')
def refresh(request: Request, month: str = '', shop: str = ''):
    return _run(lambda: refresh_report(month, shop), request)


@router.get('/product-structure')
def structure(request: Request, year: str = '', shops: str = ''):
    """产品结构：销售数量占比、不良交易率、转化率。

    year 为空取最新一年；shops 是逗号分隔的店铺名，留空为整个eBay合计。
    """
    return _run(lambda: product_structure(year, shops), request)
