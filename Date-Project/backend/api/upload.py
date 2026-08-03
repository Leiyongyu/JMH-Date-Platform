from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.api.upload_helpers import read_excel_upload, run_import
from backend.services.import_service import (
    import_customs_declaration_excel,
    import_customs_declaration_excel_batch,
    import_foreign_exchange_receipts,
    import_purchase_invoice_summary,
)


router = APIRouter()


@router.post("/api/upload/foreign-exchange-receipts")
async def upload_foreign_exchange_receipts(file: UploadFile = File(...)):
    return await run_import(import_foreign_exchange_receipts, file, "外汇回款")


@router.post("/api/upload/purchase-invoice-summary")
async def upload_purchase_invoice_summary(file: UploadFile = File(...)):
    return await run_import(import_purchase_invoice_summary, file, "采购发票汇总")


@router.post("/api/upload/customs-declaration-items")
async def upload_customs_declaration_items(file: UploadFile = File(...)):
    return await run_import(import_customs_declaration_excel, file, "报关单Excel")


@router.post("/api/upload/customs-declaration-items/batch")
async def upload_customs_declaration_items_batch(
    files: list[UploadFile] = File(...),
):
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="单次最多上传50个报关单Excel")
    excel_files = [await read_excel_upload(file) for file in files]
    try:
        return await run_in_threadpool(
            import_customs_declaration_excel_batch, excel_files
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"报关单Excel批量上传失败: {exc}"
        ) from exc
