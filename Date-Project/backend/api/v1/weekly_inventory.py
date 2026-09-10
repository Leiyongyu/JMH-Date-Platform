from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from backend.api.deps import require_internal_access
from backend.repositories import weekly_inventory_repository as repo
from backend.services.weekly_inventory_export_service import download_path
from backend.services.weekly_inventory_sync_service import TASK_CODE
from backend.services.weekly_inventory_regenerate_service import NO_SNAPSHOT

router = APIRouter(prefix="/api/v1/weekly-inventory", dependencies=[Depends(require_internal_access)])
LOG = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="weekly-inventory")
_guard = Lock()
_future = None


@router.get("/page")
def page():
    return FileResponse(Path(__file__).resolve().parents[3] / "frontend/public/weekly-inventory/index.html",
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/files")
def files(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    result = repo.list_files(page, limit)
    result['latest_snapshot'] = repo.latest_completed_snapshot()
    future = _future
    if future is not None and future.done() and not future.cancelled():
        error = future.exception()
        if error:
            result['generation_error'] = (str(error) if isinstance(error, ValueError)
                                          else '生成任务失败，请查看任务日志后重试')
    return result


@router.get("/files/{file_id}/download")
def download(file_id: int):
    try:
        record = repo.file_record(file_id)
        path = download_path(record)
        return FileResponse(path, filename=record["file_name"], headers={"Cache-Control": "no-store"})
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _run(request_id):
    from backend.services.scheduler_service import run_scheduler_task
    try:
        return run_scheduler_task(TASK_CODE, request_id=request_id, trigger_type="manual_snapshot",
                                  weekly_snapshot_only=True)
    except Exception:
        LOG.exception("Manual weekly inventory failed, request_id=%s", request_id)
        raise


@router.post("/run", status_code=202)
def run():
    global _future
    with _guard:
        if _future is not None and not _future.done():
            raise HTTPException(409, "周报正在生成，请稍后查看文件列表")
        source = repo.latest_completed_snapshot()
        if not source:
            raise HTTPException(400, NO_SNAPSHOT)
        request_id = "weekly-manual-" + str(uuid4())
        _future = _executor.submit(_run, request_id)
    return {"request_id": request_id, "message": "已提交已有快照生成任务，不拉取领星数据；结果见文件列表和任务日志"}
