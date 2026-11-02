from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.api.deps import require_internal_access
from backend.schemas.performance_requests import SchedulerRunRequest
from backend.schemas.responses import success_response
from backend.ebay_api.credentials import EbayApiError
from backend.ebay_api.workbook_accounts import credential_expiry_report
from backend.services.scheduler_service import (
    SchedulerTaskAlreadyRunning,
    get_async_run,
    list_scheduler_runs,
    list_scheduler_tasks,
    run_scheduler_task,
    set_scheduler_task_enabled,
    start_scheduler_task_async,
)


router = APIRouter(
    prefix="/api/v1/internal/scheduler",
    dependencies=[Depends(require_internal_access)],
)


@router.get('/ebay-credentials/expiry')
def get_ebay_credential_expiry(request: Request):
    try:
        return success_response(credential_expiry_report(), request_id=request.state.request_id)
    except EbayApiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/tasks")
def get_scheduler_tasks(request: Request):
    return success_response(list_scheduler_tasks(), request_id=request.state.request_id)


@router.get("/tasks/{task_code}/runs")
def get_scheduler_runs(task_code: str, request: Request, limit: int = 50):
    return success_response(
        list_scheduler_runs(task_code, limit),
        request_id=request.state.request_id,
    )


@router.post("/tasks/{task_code}/run", status_code=201)
def post_scheduler_run(
    task_code: str,
    payload: SchedulerRunRequest,
    request: Request,
    trigger_type: str = Header(default="manual", alias="X-Trigger-Type"),
):
    try:
        return success_response(
            run_scheduler_task(
                task_code,
                stat_month=payload.stat_month or payload.pull_month,
                start_date=payload.start_date,
                end_date=payload.end_date,
                request_id=request.state.request_id,
                trigger_type=(
                    "job"
                    if trigger_type.strip().lower() in {"job", "quartz"}
                    else "manual"
                ),
            ),
            request_id=request.state.request_id,
            message="scheduler task completed",
        )
    except SchedulerTaskAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"内部任务执行失败: {exc}") from exc


def _trigger(value: str) -> str:
    return "job" if value.strip().lower() in {"job", "quartz"} else "manual"


@router.post("/tasks/{task_code}/runs", status_code=202)
def post_scheduler_run_async(
    task_code: str,
    payload: SchedulerRunRequest,
    request: Request,
    trigger_type: str = Header(default="manual", alias="X-Trigger-Type"),
):
    """异步触发：立即返回 run_id，执行结果用 GET /runs/{run_id} 轮询。"""
    try:
        return success_response(
            start_scheduler_task_async(
                task_code,
                stat_month=payload.stat_month or payload.pull_month,
                start_date=payload.start_date,
                end_date=payload.end_date,
                request_id=request.state.request_id,
                trigger_type=_trigger(trigger_type),
            ),
            request_id=request.state.request_id,
            message="scheduler task accepted",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}")
def get_scheduler_run_result(run_id: str, request: Request):
    """running 时返回 202；完成时返回与同步接口相同的结果体；失败时按原因返回 409/400/502。"""
    entry = get_async_run(run_id)
    state = entry.get("state")
    if state == "missing":
        raise HTTPException(status_code=404, detail="运行记录不存在")
    if state == "failed":
        raise HTTPException(status_code=entry.get("http_status", 502), detail=entry.get("error"))
    if state == "completed":
        return success_response(
            entry["response"], request_id=request.state.request_id,
            message="scheduler task completed",
        )
    return JSONResponse(status_code=202, content=success_response(
        {"run_id": run_id, "task_code": entry.get("task_code"), "status": "running"},
        request_id=request.state.request_id,
    ))


@router.post("/tasks/{task_code}/enable")
def post_scheduler_enable(task_code: str, request: Request):
    try:
        return success_response(
            set_scheduler_task_enabled(task_code, True),
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_code}/disable")
def post_scheduler_disable(task_code: str, request: Request):
    try:
        return success_response(
            set_scheduler_task_enabled(task_code, False),
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
