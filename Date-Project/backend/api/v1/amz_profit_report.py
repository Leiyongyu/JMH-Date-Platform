"""Internal-only AMZ profit report API; ERP enforces end-user RBAC."""
import logging
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import amz_profit_report_service as service

router = APIRouter(
    prefix="/api/v1/finance/amz-profit-report",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)
MONTH_PATTERN = r"^20\d{2}-(0[1-9]|1[0-2])$"


def run(action):
    try:
        return success_response(action())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("AMZ利润报表请求失败")
        raise HTTPException(500, detail="AMZ利润报表处理失败，请确认迁移已执行并检查服务日志") from exc


@router.get("/months")
def months(limit: int = Query(24, ge=1, le=120)):
    return run(lambda: service.list_months(limit))


@router.get("/report")
def report(
    stat_month: str = Query(..., pattern=MONTH_PATTERN),
    dimension: str = Query("STORE", pattern="^(GROUP|STORE|OWNER)$"),
):
    return run(lambda: service.get_report(stat_month, dimension))


@router.get("/exports")
def export(
    start_month: str = Query(..., pattern=MONTH_PATTERN),
    end_month: str = Query(..., pattern=MONTH_PATTERN),
    dimensions: str = Query("GROUP,STORE,OWNER", max_length=30),
):
    try:
        name, content = service.export_report(start_month, end_month, dimensions.split(","))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("AMZ利润报表导出失败")
        raise HTTPException(500, detail="AMZ利润报表导出失败，请检查服务日志") from exc
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)},
    )
