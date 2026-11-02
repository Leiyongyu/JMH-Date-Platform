from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from backend.api.deps import require_internal_access
from backend.api.upload_helpers import read_excel_upload
from backend.schemas.performance_requests import (
    InventoryReportOrderProfitSyncRequest,
    InventoryReportRebuildRequest,
    PerformanceRefreshRequest,
)
from backend.schemas.responses import success_response
from backend.repositories import clearance_repository as clearance_repo
from backend.services.performance_service import (
    import_ebay_profit,
    import_owner_rules,
    import_unified_owner_rules,
    list_performance_rankings,
    owner_rule_summary,
    performance_months,
    refresh_performance,
)
from backend.services.performance_source_export_service import (
    export_amz_performance_source,
)
from backend.services.clearance_export_service import export_inventory_age_details, export_monthly_summary
from backend.services.clearance_drilldown_service import list_dimensions as clearance_dimensions
from backend.services.inventory_report_etl_service import (
    get_department_summary,
    get_dimension_summary,
    import_inventory_report_purchase_order,
    list_details as list_inventory_report_details,
    list_months as list_inventory_report_months,
    rebuild_monthly_inventory_report,
)
from backend.services.inventory_report_export_service import (
    export_monthly_inventory_report,
)
from backend.services.inventory_report_history_import_service import (
    history_preview,
    import_history,
)
from backend.services import inventory_purchase_order_job_service as purchase_order_jobs
from backend.services.inventory_report_source_sync_service import (
    InventoryReportSourceSyncError,
    sync_monthly_inventory_order_profit,
)
router = APIRouter(
    prefix="/api/v1/finance",
    dependencies=[Depends(require_internal_access)],
)


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


@router.get("/slow-moving-clearance/dimensions")
def get_slow_moving_clearance_dimensions(
    request: Request,
    pull_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    group_code: str = Query(..., pattern=r"^(EBAY-1|EU|US1|US2|US2-MJ|US1-ZXY)$"),
    site_code: str | None = Query(None, min_length=1, max_length=120),
):
    if site_code is not None and group_code != 'EBAY-1':
        raise HTTPException(status_code=400, detail='仅 eBay 支持站点下钻到个人')
    return success_response(
        clearance_dimensions(pull_month, group_code, site_code),
        request_id=request.state.request_id,
    )


@router.get("/slow-moving-clearance/months")
def get_slow_moving_clearance_months(request: Request, limit: int = 24):
    return success_response(
        clearance_repo.months(limit),
        request_id=request.state.request_id,
    )


@router.get("/slow-moving-clearance/owners")
def get_slow_moving_clearance_owners(
    request: Request,
    pull_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    site_code: str | None = Query(None, min_length=1, max_length=120),
    group_code: str = Query('EBAY-1', pattern=r"^(EBAY-1|EU|US1|US2|US2-MJ|US1-ZXY)$"),
):
    if site_code is not None and group_code != 'EBAY-1':
        raise HTTPException(status_code=400, detail='仅 eBay 支持站点筛选')
    return success_response(
        clearance_dimensions(pull_month, group_code, site_code, dimension='OWNER'),
        request_id=request.state.request_id,
    )


@router.get("/monthly-inventory-report/months")
def get_monthly_inventory_report_months(request: Request, limit: int = 24):
    return success_response(
        list_inventory_report_months(limit),
        request_id=request.state.request_id,
    )


@router.get("/monthly-inventory-report/summary")
def get_monthly_inventory_report_summary(
    request: Request,
    stat_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    return success_response(
        get_department_summary(stat_month),
        request_id=request.state.request_id,
    )


@router.get("/monthly-inventory-report/dimension-summary")
def get_monthly_inventory_report_dimension_summary(
    request: Request,
    dimension_type: str = Query(..., pattern="^(STORE|OWNER)$"),
    stat_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    try:
        data = get_dimension_summary(dimension_type, stat_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data, request_id=request.state.request_id)


@router.get("/monthly-inventory-report/exports")
async def get_monthly_inventory_report_export(
    stat_month: str | None = Query(
        None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"
    ),
    dimension_type: str = Query("GROUP"),
):
    try:
        download_name, content = await run_in_threadpool(
            export_monthly_inventory_report,
            stat_month,
            dimension_type,
        )
        return StreamingResponse(
            BytesIO(content),
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": (
                    "attachment; filename*=UTF-8''" + quote(download_name)
                )
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"月度库存报表导出失败: {exc}",
        ) from exc

@router.get("/monthly-inventory-report/details")
def get_monthly_inventory_report_details(
    request: Request,
    source_type: str = Query(..., pattern="^(fba|overseas|local)$"),
    stat_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    department_code: str | None = None,
    principal_name: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    try:
        data = list_inventory_report_details(
            source_type,
            stat_month,
            department_code,
            principal_name,
            keyword,
            page,
            page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data, request_id=request.state.request_id)


@router.post("/monthly-inventory-report/rebuilds", status_code=201)
def post_monthly_inventory_report_rebuild(
    payload: InventoryReportRebuildRequest,
    request: Request,
):
    try:
        # Manual recalculation owns the selected inventory report month only.
        # Its source month's order-profit detail belongs to the previous
        # displayed report month, so it must remain untouched.
        data = purchase_order_jobs.report_write(
            payload.stat_month, rebuild_monthly_inventory_report,
            payload.stat_month, preserve_sales_detail=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"月度库存报表重建失败: {exc}") from exc
    return success_response(
        data,
        request_id=request.state.request_id,
        message="monthly inventory report rebuilt",
    )


@router.post(
    "/monthly-inventory-report/order-profit-syncs",
    status_code=201,
)
def post_monthly_inventory_report_order_profit_sync(
    payload: InventoryReportOrderProfitSyncRequest,
    request: Request,
):
    try:
        data = sync_monthly_inventory_order_profit(payload.stat_month)
    except InventoryReportSourceSyncError as exc:
        status_code = 409 if exc.stage == "LOCK" else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"月度库存Amazon订单利润拉取失败: {exc}",
        ) from exc
    return success_response(
        data,
        request_id=request.state.request_id,
        message="monthly inventory order profit synced and report rebuilt",
    )


@router.post(
    "/monthly-inventory-report/purchase-order-imports",
    status_code=201,
)
async def post_monthly_inventory_report_purchase_order_import(
    request: Request,
    stat_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    file: UploadFile = File(...),
    operator: str | None = None,
):
    content, file_name = await read_excel_upload(file)
    try:
        data = await run_in_threadpool(
            purchase_order_jobs.report_write,
            stat_month,
            import_inventory_report_purchase_order,
            content,
            file_name,
            stat_month,
            operator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"月度库存采购单在途导入失败: {exc}",
        ) from exc
    return success_response(
        data,
        request_id=request.state.request_id,
        message="monthly inventory purchase order transit imported",
    )


@router.get("/monthly-inventory-report/purchase-order-sync-status")
def get_purchase_order_sync_status(
    request: Request,
    stat_month: str | None = Query(None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    sync_request_id: str | None = Query(None, max_length=128),
):
    try:
        return success_response(purchase_order_jobs.get_status(stat_month, sync_request_id),
                                request_id=request.state.request_id)
    except Exception:
        raise HTTPException(503, "采购在途同步状态不可用，请检查数据库迁移和连接") from None


@router.post("/monthly-inventory-report/purchase-order-syncs", status_code=202)
def post_purchase_order_sync(request: Request):
    try:
        return success_response(purchase_order_jobs.submit(), request_id=request.state.request_id,
                                message="已提交采购在途后台同步")
    except Exception:
        raise HTTPException(503, "无法启动采购在途同步，请检查数据库迁移和连接") from None


@router.post("/monthly-inventory-report/history-preview")
async def post_monthly_inventory_history_preview(
    request: Request, file: UploadFile = File(...),
):
    content, file_name = await read_excel_upload(file)
    try:
        data = await run_in_threadpool(history_preview, content, file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data, request_id=request.state.request_id)


@router.post("/monthly-inventory-report/history-imports", status_code=201)
async def post_monthly_inventory_history_import(
    request: Request,
    file: UploadFile = File(...),
    file_sha256: str = Query(..., pattern=r"^[a-f0-9]{64}$"),
):
    content, file_name = await read_excel_upload(file)
    try:
        data = await run_in_threadpool(import_history, content, file_name, file_sha256)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data, request_id=request.state.request_id)


@router.get("/slow-moving-clearance/monthly-summary-exports")
async def get_clearance_monthly_summary_export(
    pull_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    try:
        file_path, download_name = await run_in_threadpool(export_monthly_summary, pull_month)
        return FileResponse(
            file_path,
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(Path(file_path).unlink, missing_ok=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"滞销清货当月汇总导出失败: {exc}") from exc


@router.get("/slow-moving-clearance/inventory-age-detail-exports")
async def get_inventory_age_detail_export(
    pull_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    try:
        file_path, download_name = await run_in_threadpool(
            export_inventory_age_details,
            pull_month,
        )
        return FileResponse(
            file_path,
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(Path(file_path).unlink, missing_ok=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"库龄明细导出失败: {exc}") from exc


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


@router.get("/amz-performance-source-exports")
async def get_amz_performance_source_export(
    stat_month: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
):
    try:
        file_path, download_name = await run_in_threadpool(
            export_amz_performance_source,
            stat_month,
        )
        return FileResponse(
            file_path,
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(Path(file_path).unlink, missing_ok=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AMZ绩效源数据导出失败: {exc}") from exc


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
    stat_month: str | None = None,
    operator: str | None = None,
):
    try:
        content = await file.read()
        result = await run_in_threadpool(
            import_ebay_profit,
            content,
            file.filename or "ebay-profit.xlsx",
            rebuild=rebuild,
            stat_month=stat_month,
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
        result = await run_in_threadpool(
            import_owner_rules,
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


@router.post("/performance-owner-rule-unified-imports", status_code=201)
async def post_unified_owner_rule_import(
    request: Request,
    file: UploadFile = File(...),
    rebuild: bool = True,
    operator: str | None = None,
):
    try:
        content = await file.read()
        result = await run_in_threadpool(
            import_unified_owner_rules,
            content,
            file.filename or "unified-owner-rules.xlsx",
            rebuild=rebuild,
            operator=operator,
            request_id=request.state.request_id,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return success_response(
            result,
            request_id=request.state.request_id,
            message="unified owner rules imported",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"统一负责人规则导入失败: {exc}",
        ) from exc


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
