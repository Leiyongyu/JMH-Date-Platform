from fastapi import APIRouter, Depends, Request
from backend.api.deps import require_internal_access
from backend.api.v1.ebay_price_tier import _run
from backend.services import listing_price_tier_service as service

router = APIRouter(prefix='/api/v1/finance/amz-price-tier', dependencies=[Depends(require_internal_access)])


@router.get('/summary')
def summary(request: Request):
    return _run(lambda: service.read_report('amz'), request)


@router.post('/refresh')
def refresh(request: Request):
    return _run(lambda: service.refresh_report('amz'), request)
