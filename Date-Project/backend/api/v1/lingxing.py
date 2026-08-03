from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.schemas.lingxing_requests import (
    LingXingDomainSyncRequest,
    LingXingProbeRequest,
    LingXingSyncRequest,
)
from backend.schemas.responses import success_response
from backend.services.lingxing_service import (
    create_lingxing_sync_job,
    domains,
    get_lingxing_sync_job,
    probe,
    refresh_token,
    token_status,
)


router = APIRouter(prefix="/api/v1/lingxing")


@router.get("/token-status")
def get_token_status(request: Request):
    return success_response(token_status(), request_id=request.state.request_id)


@router.post("/token-refresh")
def post_token_refresh(request: Request):
    try:
        return success_response(refresh_token(), request_id=request.state.request_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"领星 token 刷新失败: {exc}") from exc


@router.post("/probe")
def post_probe(payload: LingXingProbeRequest, request: Request):
    try:
        return success_response(
            probe(payload.path, payload.body),
            request_id=request.state.request_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"领星接口调用失败: {exc}") from exc


@router.get("/domains")
def get_domains(request: Request):
    return success_response(domains(), request_id=request.state.request_id)


@router.post("/sync", status_code=202)
def post_sync(payload: LingXingSyncRequest, request: Request):
    try:
        job = create_lingxing_sync_job(
            payload.data_type,
            payload.path,
            payload.params,
            payload.paginated,
        )
        return success_response(job, request_id=request.state.request_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"领星同步启动失败: {exc}") from exc


@router.post("/sync-domain", status_code=202)
def post_domain_sync(payload: LingXingDomainSyncRequest, request: Request):
    try:
        job = create_lingxing_sync_job(
            payload.data_type,
            payload.path,
            payload.params,
            payload.paginated,
            domain=payload.domain,
        )
        return success_response(job, request_id=request.state.request_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"领星业务域同步启动失败: {exc}") from exc


@router.get("/sync/{job_id}")
def get_sync_job(job_id: str, request: Request):
    job = get_lingxing_sync_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="领星同步任务不存在")
    return success_response(job, request_id=request.state.request_id)
