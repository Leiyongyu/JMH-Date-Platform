"""AMZ 月度利润表内部接口（财务中心）；终端用户权限由 Java 侧控制。

数据只由定时任务 amz_monthly_profit_sync 按月拉取；页面只读报表、维护手工补充费用、导出。
"""
from __future__ import annotations

import logging
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import amz_monthly_profit_service as service

router = APIRouter(
    prefix="/api/v1/finance/amz-monthly-profit",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)
MONTH_PATTERN = r"^20\d{2}-(0[1-9]|1[0-2])$"


def _run(action, label: str):
    try:
        return success_response(action())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("AMZ月度利润表%s失败", label)
        raise HTTPException(500, detail=f"AMZ月度利润表{label}失败，请确认 20261111_amz_monthly_profit.sql "
                                        "已执行并检查服务日志") from exc


@router.get("/months")
def months(limit: int = Query(36, ge=1, le=120)):
    return _run(lambda: service.list_months(limit), "月份查询")


@router.get("/report")
def report(stat_month: str = Query(..., pattern=MONTH_PATTERN)):
    return _run(lambda: service.get_report(stat_month), "查询")


@router.get("/exports")
def export(stat_month: str = Query(..., pattern=MONTH_PATTERN)):
    try:
        name, content = service.export_report(stat_month)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("AMZ月度利润表导出失败")
        raise HTTPException(500, detail="AMZ月度利润表导出失败，请检查服务日志") from exc
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)},
    )


@router.get("/adjustments")
def adjustments(stat_month: str = Query(..., pattern=MONTH_PATTERN)):
    return _run(lambda: service.list_adjustments(stat_month), "补充费用查询")


@router.post("/adjustments")
def create_adjustment(payload: dict = Body(...)):
    return _run(lambda: service.create_adjustment(payload, payload.get("operator")), "补充费用新增")


@router.put("/adjustments/{adjustment_id}")
def update_adjustment(adjustment_id: int, payload: dict = Body(...)):
    return _run(lambda: service.update_adjustment(adjustment_id, payload, payload.get("operator")), "补充费用修改")


@router.delete("/adjustments/{adjustment_id}")
def delete_adjustment(adjustment_id: int):
    return _run(lambda: service.delete_adjustment(adjustment_id), "补充费用删除")
