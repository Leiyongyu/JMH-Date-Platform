from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from backend.api.upload_helpers import read_excel_upload
from backend.schemas.ebay_price_requests import EbayPriceExportRequest, EbayPriceSearchRequest
from backend.schemas.responses import success_response
from backend.services.ebay_price_service import (
    export_search_results,
    import_sku_oe_mapping,
    search_prices,
)


router = APIRouter(prefix="/api/v1/ebay-price")


@router.post("/sku-oe-imports", status_code=201)
async def post_sku_oe_import(request: Request, file: UploadFile = File(...)):
    content, file_name = await read_excel_upload(file)
    try:
        result = await run_in_threadpool(import_sku_oe_mapping, content, file_name)
        return success_response(result, request_id=request.state.request_id, message="ebay sku oe mapping imported")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay SKU-OE 对照表导入失败: {exc}") from exc


@router.post("/searches")
def post_search(payload: EbayPriceSearchRequest, request: Request):
    try:
        result = search_prices(payload.keywords, payload.site, payload.input_type)
        return success_response(result, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay 价格查询失败: {exc}") from exc


@router.post("/exports")
def post_export(payload: EbayPriceExportRequest):
    try:
        file_path, download_name = export_search_results(payload.items)
        return FileResponse(
            file_path,
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay 价格结果导出失败: {exc}") from exc
