from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.import_job_state import (
    customs_import_executor,
    process_customs_import_job,
)
from backend.job_state import get_job, record_job


router = APIRouter()


async def read_customs_folder_uploads(
    files: list[UploadFile],
) -> tuple[list[tuple[bytes, str]], list[str]]:
    if len(files) > 500:
        raise HTTPException(status_code=400, detail="单次文件夹最多包含500个文件")

    excel_files: list[tuple[bytes, str]] = []
    skipped_files: list[str] = []
    total_size = 0
    for file in files:
        file_name = file.filename or "未命名文件"
        base_name = Path(file_name.replace("\\", "/")).name
        if base_name.startswith("~$") or not file_name.lower().endswith(
            (".xlsx", ".xlsm")
        ):
            skipped_files.append(file_name)
            continue
        content = await file.read()
        if not content:
            skipped_files.append(file_name)
            continue
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"文件“{file_name}”超过50MB",
            )
        total_size += len(content)
        if total_size > 500 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件夹Excel总大小不能超过500MB")
        excel_files.append((content, file_name))

    if not excel_files:
        raise HTTPException(
            status_code=400,
            detail="所选文件夹中没有可导入的 .xlsx 或 .xlsm 报关资料",
        )
    return excel_files, skipped_files


@router.post("/api/import-jobs/customs-folder", status_code=202)
async def create_customs_folder_import_job(
    files: list[UploadFile] = File(...),
):
    excel_files, skipped_files = await read_customs_folder_uploads(files)
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "kind": "customs_folder_import",
        "status": "queued",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": None,
        "completed_at": None,
        "total_files": len(excel_files),
        "processed_files": 0,
        "succeeded_files": 0,
        "failed_files": 0,
        "skipped_files": skipped_files,
        "skipped_file_count": len(skipped_files),
        "current_file": None,
        "processed_rows": 0,
        "inserted_rows": 0,
        "updated_rows": 0,
        "replaced_rows": 0,
        "results": [],
        "errors": [],
        "fatal_error": None,
    }
    record_job(job)
    customs_import_executor.submit(process_customs_import_job, job_id, excel_files)
    return copy.deepcopy(job)


@router.get("/api/import-jobs/{job_id}")
def get_import_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return copy.deepcopy(job)
