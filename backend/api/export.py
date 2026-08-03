from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from backend.config import settings
from backend.schemas.requests import FinalPackageRequest
from backend.services.export_service import generate_final_package


router = APIRouter()


@router.post("/api/export/final-package")
async def export_final_package(payload: FinalPackageRequest | None = None):
    try:
        return await run_in_threadpool(
            generate_final_package, payload.errors if payload else []
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"最终文件生成失败: {exc}"
        ) from exc


@router.get("/api/export/download-package")
async def download_generated_package():
    target = (Path(settings.export_output_dir) / "外汇退税生成文件.zip").resolve()
    if not target.is_file():
        raise HTTPException(status_code=404, detail="生成文件包不存在，请先生成所选批次")
    return FileResponse(
        target,
        filename=target.name,
        media_type="application/zip",
    )
