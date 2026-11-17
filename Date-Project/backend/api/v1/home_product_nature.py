"""Shared routes nested below internally authenticated platform routers."""
import logging
from fastapi import APIRouter, HTTPException, Query, Request
from backend.schemas.responses import success_response
from backend.services import home_product_nature_service as service

LOG = logging.getLogger(__name__)


def run(action, request):
    try:
        return success_response(action(), request_id=getattr(request.state,'request_id',''))
    except ValueError as exc:
        raise HTTPException(400,detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception('首页新老品报表失败')
        raise HTTPException(500,detail='新老品报表暂不可用，请检查初始化SQL和服务日志') from exc


def nature_router(platform):
    router = APIRouter(prefix='/nature')

    @router.get('/summary')
    def summary(request: Request, month: str | None = None):
        return run(lambda:service.get_report(platform,month),request)

    @router.get('/groups')
    def groups(request: Request, month: str | None = None):
        return run(lambda:service.get_report(platform,month,'groups'),request)

    @router.get('/owners')
    def owners(request: Request, month: str | None = None, group_code: str | None = Query(None,max_length=64),
               segment_key: str | None = Query(None,max_length=64), batch_id: str | None = Query(None,max_length=36)):
        return run(lambda:service.get_report(platform,month,'owners',group_code=group_code,
                                            segment_key=segment_key,batch_id=batch_id),request)

    @router.get('/details')
    def details(request: Request, month: str | None = None, group_code: str | None = Query(None,max_length=64),
                owner_key: str | None = Query(None,max_length=64), nature: str | None = None,
                sku: str | None = Query(None,max_length=512),page: int = Query(1,ge=1,le=1000000),
                page_size: int = Query(50,ge=1,le=100)):
        return run(lambda:service.get_report(platform,month,'details',group_code=group_code,owner_key=owner_key,
                       nature=nature,sku=sku,page=page,page_size=page_size),request)

    @router.get('/history')
    def history(request: Request, start_month: str | None = None, end_month: str | None = None,
                include_current: bool = False):
        return run(lambda:service.get_history(platform,start_month,end_month,include_current),request)

    @router.get('/compare')
    def compare(request: Request, base_month: str, target_month: str, scope: str = 'PLATFORM',
                group_code: str | None = Query(None,max_length=64)):
        return run(lambda:service.compare(platform,base_month,target_month,scope,group_code),request)

    return router
