from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.api.deps import require_internal_access
from backend.api.upload_helpers import read_excel_upload
from backend.schemas.responses import success_response
from backend.services import ebay_sku_analysis_service as service

router = APIRouter(prefix="/api/v1/finance/ebay-sku-analysis", dependencies=[Depends(require_internal_access)])


@router.get("/dates")
def dates(request: Request):
    try:
        return success_response(service.date_bounds(), request_id=request.state.request_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay SKU分析日期范围查询失败: {exc}") from exc


@router.get("/summary")
def summary(request: Request, start_date: str | None = None, end_date: str | None = None,
            sku: str | None = None, site: str | None = None, chart_metric: str | None = None,
            chart_order: str | None = None, page: int = 1, page_size: int = 50):
    try:
        data = service.list_summary(start_date, end_date, sku, site, chart_metric, chart_order, page, page_size)
        return success_response(data, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay SKU分析汇总查询失败: {exc}") from exc


@router.post("/imports", status_code=201)
async def imports(request: Request, file: UploadFile = File(...), operator: str | None = None):
    content, file_name = await read_excel_upload(file)
    try:
        data = await run_in_threadpool(service.import_orders, content, file_name, operator)
        return success_response(data, request_id=request.state.request_id, message="eBay SKU分析订单导入完成")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay SKU分析导入失败: {exc}") from exc


@router.post("/profit-imports", status_code=201)
async def profit_imports(request: Request, file: UploadFile = File(...), operator: str | None = None):
    content, file_name = await read_excel_upload(file)
    try:
        data = await run_in_threadpool(service.import_profit_orders, content, file_name, operator)
        return success_response(data, request_id=request.state.request_id, message="eBay SKU分析订单利润导入完成")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay SKU分析订单利润导入失败: {exc}") from exc
