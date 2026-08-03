from __future__ import annotations

from fastapi import HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool


async def read_excel_upload(file: UploadFile) -> tuple[bytes, str]:
    file_name = file.filename or "upload.xlsx"
    if not file_name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="只支持 .xlsx 或 .xlsm 文件")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="单个文件不能超过50MB")
    return content, file_name


async def run_import(importer, file: UploadFile, label: str):
    content, file_name = await read_excel_upload(file)
    try:
        return await run_in_threadpool(importer, content, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{label}上传失败: {exc}") from exc
