from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.config import settings
from backend.schemas.performance_requests import SchedulerRunRequest
from backend.schemas.responses import success_response
from backend.services.scheduler_service import (
    SchedulerTaskAlreadyRunning,
    list_scheduler_runs,
    list_scheduler_tasks,
    run_scheduler_task,
    set_scheduler_task_enabled,
)


def require_internal_access(
    request: Request,
    internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    configured_token = settings.python_performance_internal_token
    if configured_token:
        if not internal_token or not secrets.compare_digest(
            internal_token, configured_token
        ):
            raise HTTPException(status_code=401, detail="内部任务令牌无效")
        return
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail="未配置内部任务令牌时，仅允许本机访问",
        )


router = APIRouter(
    prefix="/api/v1/internal/scheduler",
    dependencies=[Depends(require_internal_access)],
)


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
