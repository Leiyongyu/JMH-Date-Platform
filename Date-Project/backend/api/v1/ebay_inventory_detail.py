from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ebay_inventory_detail_service as service
from backend.services import ebay_inventory_pivot_service as pivot_service
from backend.services import ebay_inventory_age_ratio_service as age_ratio_service
from backend.services import ebay_inventory_history_import_service as history_import_service
from backend.services.ebay_inventory_pivot_export_service import export_pivot
from backend.services.ebay_inventory_detail_export_service import EXCEL_CONTENT_TYPE
from backend.services.ebay_inventory_bundle_export_service import export_inventory
from backend.services.ebay_inventory_workbook import MAX_FILE_BYTES

LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/finance/ebay-inventory-detail", dependencies=[Depends(require_internal_access)])


class InventoryKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site: str = Field(min_length=1, max_length=100)
    sku: str = Field(default="", max_length=255)
    record_key: str = Field(default="", max_length=80)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stat_date: str | None = Field(default=None, max_length=10)
    start_date: str | None = Field(default=None, max_length=10)
    end_date: str | None = Field(default=None, max_length=10)
    site: str | None = Field(default=None, max_length=100)
    sku: str | None = Field(default=None, max_length=2048, description="核心码（数字或字母数字组合），英文逗号分隔，精确匹配")
    brand: str | None = Field(default=None, max_length=2048, description="品牌多选，英文逗号分隔")
    grade: str | None = Field(default=None, max_length=2048, description="等级多选，英文逗号分隔")
    sort_field: str | None = Field(default=None, max_length=80)
    sort_order: str | None = Field(default=None, max_length=16)
    selected_keys: list[InventoryKey] = Field(default_factory=list, max_length=50000)


def _failure(exc: Exception, label: str):
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    LOG.exception("eBay库存明细%s失败", label)
    return HTTPException(status_code=500, detail=f"eBay库存明细{label}失败，请检查Python日志及部署SQL")


@router.get("/list")
def list_inventory(request: Request, site: str | None = Query(None, max_length=100),
                   stat_date: str | None = Query(None, max_length=10),
                   start_date: str | None = Query(None, max_length=10),
                   end_date: str | None = Query(None, max_length=10),
                   sku: str | None = Query(None, max_length=2048, description="核心码（数字或字母数字组合），英文逗号分隔，精确匹配"),
                   brand: str | None = Query(None, max_length=2048),
                   grade: str | None = Query(None, max_length=2048), page: int = Query(1, ge=1),
                   page_size: int = Query(50, ge=1, le=200), sort_field: str | None = Query(None, max_length=80),
                   sort_order: str | None = Query(None, max_length=16)):
    try:
        data = service.list_inventory(site=site, sku=sku, brand=brand, grade=grade, page=page,
                                      page_size=page_size, sort_field=sort_field, sort_order=sort_order,
                                      stat_date=stat_date, start_date=start_date, end_date=end_date)
        return success_response(data, request_id=request.state.request_id)
    except Exception as exc:
        raise _failure(exc, "查询") from exc


@router.post("/snapshot/recalculate")
def recalculate_snapshot(request: Request):
    """Explicit write action: all current data, today's date, never client filters/dates."""
    try:
        result = pivot_service.capture_all_snapshots()
        return success_response(result, request_id=request.state.request_id,
                                message="今日库存明细、历史透视及海外仓库龄占比已统一保存")
    except Exception as exc:
        raise _failure(exc, "重新计算") from exc


@router.get("/age-ratio")
def read_age_ratio(request: Request, stat_date: str | None = Query(None, max_length=10),
                   start_date: str | None = Query(None, max_length=10),
                   end_date: str | None = Query(None, max_length=10)):
    try:
        if start_date is not None or end_date is not None:
            return success_response(age_ratio_service.read_range(start_date, end_date), request_id=request.state.request_id)
        return success_response(age_ratio_service.read_snapshot(stat_date), request_id=request.state.request_id)
    except Exception as exc:
        raise _failure(exc, "海外仓库龄占比查询") from exc


@router.post("/age-ratio/recalculate")
def recalculate_age_ratio(request: Request):
    # Never accept client dates, values, owners or filters for a published snapshot.
    try:
        result = age_ratio_service.capture_snapshot()
        return success_response(result, request_id=request.state.request_id)
    except Exception as exc:
        raise _failure(exc, "海外仓库龄占比刷新") from exc


@router.post("/export")
def export_rows(payload: ExportRequest):
    try:
        filename, content = export_inventory(**payload.model_dump())
        return Response(content, media_type=EXCEL_CONTENT_TYPE, headers={
            "Content-Disposition": f"attachment; filename=ebay-inventory-detail.xlsx; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        })
    except Exception as exc:
        raise _failure(exc, "导出") from exc


@router.get("/pivot")
def list_history(request: Request, start_date: str | None = Query(None, max_length=10),
                 end_date: str | None = Query(None, max_length=10), owner: str | None = Query(None, max_length=128),
                 site: str | None = Query(None, max_length=32), page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=200), sort_field: str | None = Query(None, max_length=80),
                 sort_order: str | None = Query(None, max_length=16)):
    try:
        data = pivot_service.list_pivot(start_date=start_date, end_date=end_date, owner=owner, site=site,
                                       page=page, page_size=page_size, sort_field=sort_field, sort_order=sort_order)
        return success_response(data, request_id=request.state.request_id)
    except Exception as exc:
        raise _failure(exc, "历史透视查询") from exc


@router.get("/pivot/export")
def export_history(start_date: str | None = Query(None, max_length=10), end_date: str | None = Query(None, max_length=10),
                   owner: str | None = Query(None, max_length=128), site: str | None = Query(None, max_length=32),
                   sort_field: str | None = Query(None, max_length=80), sort_order: str | None = Query(None, max_length=16)):
    try:
        filename, content = export_pivot(start_date=start_date, end_date=end_date, owner=owner, site=site,
                                         sort_field=sort_field, sort_order=sort_order)
        return Response(content, media_type=EXCEL_CONTENT_TYPE, headers={
            "Content-Disposition": f"attachment; filename=ebay-inventory-history.xlsx; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        })
    except Exception as exc:
        raise _failure(exc, "历史透视导出") from exc


@router.post("/prices/import")
async def import_prices(request: Request, file: UploadFile = File(...), operator: str | None = Query(None, max_length=64)):
    filename = file.filename or "prices.xlsx"
    try:
        content = await file.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("单价文件不能超过10MB")
        result = await run_in_threadpool(service.import_prices, content, filename, operator)
        return success_response(result, request_id=request.state.request_id, message="产品单价导入完成")
    except Exception as exc:
        raise _failure(exc, "单价导入") from exc
    finally:
        await file.close()


@router.post("/history/import")
async def import_history(request: Request, file: UploadFile = File(...), operator: str | None = Query(None, max_length=64)):
    filename = file.filename or "history.xlsx"
    try:
        content = await file.read(history_import_service.MAX_FILE_BYTES + 1)
        if len(content) > history_import_service.MAX_FILE_BYTES:
            raise ValueError("历史文件不能超过50MB")
        result = await run_in_threadpool(history_import_service.import_history, content, filename, operator)
        return success_response(result, request_id=request.state.request_id, message="历史数据导入完成")
    except Exception as exc:
        raise _failure(exc, "历史导入") from exc
    finally:
        await file.close()
