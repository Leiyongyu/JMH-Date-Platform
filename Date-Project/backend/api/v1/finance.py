from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from backend.schemas.performance_requests import PerformanceRefreshRequest
from backend.schemas.responses import success_response
from backend.repositories import clearance_repository as clearance_repo
from backend.services.performance_service import (
    import_ebay_profit,
    import_owner_rules,
    list_performance_rankings,
    owner_rule_summary,
    performance_months,
    refresh_performance,
)


router = APIRouter(prefix="/api/v1/finance")


@router.get("/slow-moving-clearance/groups")
def get_slow_moving_clearance_groups(
    request: Request,
    pull_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    return success_response(
        clearance_repo.list_groups(pull_month),
        request_id=request.state.request_id,
    )


@router.get("/slow-moving-clearance/summary")
def get_slow_moving_clearance_summary(
    request: Request,
    pull_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    return success_response(
        clearance_repo.summary(pull_month),
        request_id=request.state.request_id,
    )


@router.get("/slow-moving-clearance/months")
def get_slow_moving_clearance_months(request: Request, limit: int = 24):
    return success_response(
        clearance_repo.months(limit),
        request_id=request.state.request_id,
    )


@router.get("/performance-rankings")
def get_performance_rankings(
    request: Request,
    platform: str = Query("combined", pattern="^(combined|amazon|ebay)$"),
    stat_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    principal_name: str | None = None,
    order_by: str = Query("gross_profit", pattern="^(gross_profit|net_sales_amount)$"),
    order: str = Query("desc", pattern="^(desc|asc)$"),
    page: int = 1,
    page_size: int = 100,
):
    return success_response(
        list_performance_rankings(
            platform=platform,
            stat_month=stat_month,
            principal_name=principal_name,
            order_by=order_by,
            order=order,
            page=page,
            page_size=page_size,
        ),
        request_id=request.state.request_id,
    )


@router.get("/performance-months")
def get_performance_months(request: Request, limit: int = 12):
    return success_response(performance_months(limit), request_id=request.state.request_id)


@router.post("/performance-refreshes", status_code=201)
def post_performance_refresh(payload: PerformanceRefreshRequest, request: Request):
    try:
        result = refresh_performance(
            payload.stat_month,
            platform=payload.platform,
            require_all_platforms=payload.require_all_platforms,
            request_id=request.state.request_id,
        )
        return success_response(result, request_id=request.state.request_id, message="performance ranking refreshed")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"绩效刷新失败: {exc}") from exc


@router.post("/ebay-profit-imports", status_code=201)
async def post_ebay_profit_import(
    request: Request,
    file: UploadFile = File(...),
    rebuild: bool = True,
    operator: str | None = None,
):
    try:
        content = await file.read()
        result = import_ebay_profit(
            content,
            file.filename or "ebay-profit.xlsx",
            rebuild=rebuild,
            operator=operator,
            request_id=request.state.request_id,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return success_response(result, request_id=request.state.request_id, message="ebay profit imported")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"eBay利润导入失败: {exc}") from exc


@router.post("/performance-owner-rule-imports", status_code=201)
async def post_owner_rule_import(
    request: Request,
    platform: str = Query(..., pattern="^(amazon|ebay)$"),
    file: UploadFile = File(...),
    rebuild: bool = True,
    stat_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    operator: str | None = None,
):
    try:
        content = await file.read()
        result = import_owner_rules(
            platform,
            content,
            file.filename or "owner-rules.xlsx",
            rebuild=rebuild,
            stat_month=stat_month,
            operator=operator,
            request_id=request.state.request_id,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return success_response(result, request_id=request.state.request_id, message="owner rules imported")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"负责人规则导入失败: {exc}") from exc


@router.get("/performance-owner-rule-summaries")
def get_owner_rule_summary(
    request: Request,
    platform: str = Query(..., pattern="^(amazon|ebay)$"),
    stat_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    return success_response(
        owner_rule_summary(platform, stat_month),
        request_id=request.state.request_id,
    )
