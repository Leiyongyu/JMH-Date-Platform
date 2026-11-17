"""项目利润总表内部接口（财务中心）；终端用户权限由 Java 侧控制。

AMZ 各列按上传的领星「利润报表-MSKU」现算；eBay 列来自上传的财务 eBay 利润明细表；人力、分摊、房租等各组手工录入。
"""
from __future__ import annotations

import logging
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import project_profit_service as service

router = APIRouter(
    prefix="/api/v1/finance/project-profit",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)
MONTH_PATTERN = r"^20\d{2}-(0[1-9]|1[0-2])$"


def _missing_table(exc: Exception) -> bool:
    return bool(exc.args) and exc.args[0] == 1146


def _run(action, label: str):
    try:
        return success_response(action())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        if _missing_table(exc):
            raise HTTPException(400, detail=service.MIGRATION_MESSAGE) from exc
        LOG.exception("项目利润总表%s失败", label)
        raise HTTPException(500, detail=f"项目利润总表{label}失败，请检查服务日志") from exc


@router.get("/months")
def months(limit: int = Query(36, ge=1, le=120)):
    return _run(lambda: service.list_months(limit), "月份查询")


@router.get("/report")
def report(stat_month: str = Query(..., pattern=MONTH_PATTERN)):
    return _run(lambda: service.get_report(stat_month), "查询")


@router.put("/items")
def save_items(payload: dict = Body(...)):
    return _run(lambda: service.save_items(payload, payload.get("operator")), "手工项保存")


async def _upload(file: UploadFile, action, stat_month: str, operator: str | None, default_name: str, label: str):
    try:
        content = await file.read(service.MAX_FILE_BYTES + 1)
        result = await run_in_threadpool(action, content, file.filename or default_name, stat_month, operator)
        return success_response(result)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        if _missing_table(exc):
            raise HTTPException(400, detail=service.MIGRATION_MESSAGE) from exc
        LOG.exception("项目利润总表 %s上传失败", label)
        raise HTTPException(500, detail=f"{label}上传失败，请检查服务日志") from exc
    finally:
        await file.close()


@router.post("/ebay/import")
async def import_ebay(file: UploadFile = File(...), stat_month: str = Query(..., pattern=MONTH_PATTERN),
                      operator: str | None = Query(None, max_length=64)):
    return await _upload(file, service.import_ebay, stat_month, operator, "eBay利润明细表.xlsx", "eBay 利润明细表")


@router.post("/amz/import")
async def import_amz(file: UploadFile = File(...), stat_month: str = Query(..., pattern=MONTH_PATTERN),
                     operator: str | None = Query(None, max_length=64)):
    return await _upload(file, service.import_amz, stat_month, operator, "利润报表-MSKU.xlsx", "领星利润报表")


@router.get("/exports")
def export(stat_month: str = Query(..., pattern=MONTH_PATTERN)):
    try:
        name, content = service.export_report(stat_month)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        if _missing_table(exc):
            raise HTTPException(400, detail=service.MIGRATION_MESSAGE) from exc
        LOG.exception("项目利润总表导出失败")
        raise HTTPException(500, detail="项目利润总表导出失败，请检查服务日志") from exc
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)},
    )
