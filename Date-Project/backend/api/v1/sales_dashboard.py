"""Internal-only finance sales history API; ERP enforces end-user RBAC."""
import logging
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import sales_dashboard_service as service

router = APIRouter(prefix='/api/v1/finance/sales-dashboard', dependencies=[Depends(require_internal_access)])
LOG = logging.getLogger(__name__)


def run(action):
    try:
        return success_response(action())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception('销售看板请求失败')
        raise HTTPException(500, detail='销售看板处理失败，请确认初始化SQL已执行并检查服务日志') from exc


@router.get('/options')
def options():
    return run(service.options)


@router.get('/report')
def report(platform: str, start_month: str, end_month: str, groups_csv: str = Query('', max_length=6500), granularity: str | None = None):
    if granularity is not None:
        from backend.services.sales_dashboard_analytics import analyze
        return run(lambda: analyze(platform, start_month, end_month, groups_csv.split(','), granularity))
    return run(lambda: service.report(platform, start_month, end_month, groups_csv.split(',')))


def read_file(file):
    content = file.file.read(service.MAX_FILE_SIZE + 1)
    if len(content) > service.MAX_FILE_SIZE:
        raise HTTPException(400, detail='文件不能超过10MB')
    return content


@router.post('/preview')
def preview(file: UploadFile = File(...)):
    content = read_file(file)
    return run(lambda: service.preview(content, file.filename or ''))


@router.post('/import')
def import_history(file: UploadFile = File(...), file_sha256: str = Query(..., min_length=64, max_length=64),
                   operator: str = Query(..., min_length=1, max_length=64)):
    content = read_file(file)
    return run(lambda: service.import_history(content, file.filename or '', file_sha256, operator))
