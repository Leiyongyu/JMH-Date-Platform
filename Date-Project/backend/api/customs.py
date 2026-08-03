from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.services.customs_service import (
    convert_customs_declaration_to_export_details,
    convert_customs_declarations_to_export_details,
    list_customs_declaration_options,
)
from backend.schemas.requests import CustomsBatchExportRequest, CustomsExportRequest


router = APIRouter()


@router.get("/api/customs-declarations/options")
async def customs_declaration_options():
    try:
        return await run_in_threadpool(list_customs_declaration_options)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"报关单列表读取失败: {exc}"
        ) from exc


@router.post("/api/customs-declarations/convert-to-export-details")
async def convert_customs_declaration(payload: CustomsExportRequest):
    try:
        return await run_in_threadpool(
            convert_customs_declaration_to_export_details,
            payload.customs_declaration_no,
            payload.declaration_month,
            payload.declaration_batch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"出口明细生成失败: {exc}"
        ) from exc


@router.post("/api/customs-declarations/batch-convert-to-export-details")
async def batch_convert_customs_declarations(payload: CustomsBatchExportRequest):
    try:
        return await run_in_threadpool(
            convert_customs_declarations_to_export_details,
            payload.customs_declaration_numbers,
            payload.declaration_month,
            payload.declaration_batch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"批量生成出口和进货明细失败: {exc}"
        ) from exc
