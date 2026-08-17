from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from datetime import date, datetime
from io import BytesIO

from backend.api.deps import require_internal_access
from backend.api.upload_helpers import read_excel_upload
from backend.schemas.performance_requests import (
    InventoryReportRebuildRequest,
    PerformanceRefreshRequest,
)
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
from backend.services.performance_source_export_service import (
    export_amz_performance_source,
)
from backend.services.clearance_service import import_inventory_age_cost
from backend.services.clearance_export_service import export_inventory_age_details
from backend.services.inventory_report_etl_service import (
    get_department_summary,
    list_details as list_inventory_report_details,
    list_months as list_inventory_report_months,
    rebuild_monthly_inventory_report,
)
from backend.repositories import amz_sop_repository as amz_sop_repo
from backend.services.amz_sop_after_sales_service import (
    BIG_CATEGORIES,
    export_filtered_summary,
    export_summary,
    list_product_summary,
)
from backend.services import ebay_sop_after_sales_service as ebay_sop_service


router = APIRouter(
    prefix="/api/v1/finance",
    dependencies=[Depends(require_internal_access)],
)


@router.get("/amz-sop-after-sales/summary")
def get_amz_sop_after_sales_summary(
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
    big_category: str | None = None,
    small_category: str | None = None,
    sku: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    if (start_date is None) != (end_date is None):
        raise HTTPException(status_code=400, detail="start_date和end_date必须同时提供")
    try:
        data = list_product_summary(
            start_date, end_date, big_category, small_category, sku,
            max(page, 1), max(1, min(page_size, 200)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data,
        request_id=request.state.request_id,
    )


@router.get("/amz-sop-after-sales/categories")
def get_amz_sop_after_sales_categories(request: Request):
    return success_response(
        {"big_categories": list(BIG_CATEGORIES), "rules": amz_sop_repo.category_rules()},
        request_id=request.state.request_id,
    )


@router.get("/amz-sop-after-sales/periods")
def get_amz_sop_after_sales_periods(request: Request, limit: int = 24):
    return success_response(
        amz_sop_repo.periods(limit),
        request_id=request.state.request_id,
    )


@router.get("/amz-sop-after-sales/exports")
def get_amz_sop_after_sales_export(
    request: Request,
    start_date: date,
    end_date: date,
):
    content = export_summary(start_date, end_date)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"AMZ-SOP售后表-{start_date}-{end_date}-{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/amz-sop-after-sales/data-exports")
def get_amz_sop_after_sales_data_export(
    request: Request,
    start_date: date,
    end_date: date,
    big_category: str | None = None,
    small_category: str | None = None,
    sku: str | None = None,
    ids: str | None = None,
    skus: str | None = None,
):
    selected_ids = [
        int(value.strip())
        for value in (ids or "").split(",")
        if value.strip().isdigit()
    ]
    selected_skus = [
        value.strip()
        for value in (skus or "").split(",")
        if value.strip()
    ]
    content = export_filtered_summary(
        start_date, end_date, big_category, small_category, sku,
        selected_ids or None, selected_skus or None,
    )
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"AMZ-SOP售后数据-{start_date}-{end_date}-{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/ebay-sop-after-sales/summary")
def get_ebay_sop_after_sales_summary(
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
    big_category: str | None = None,
    small_category: str | None = None,
    sku: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    if (start_date is None) != (end_date is None):
        raise HTTPException(status_code=400, detail="start_date和end_date必须同时提供")
    try:
        data = ebay_sop_service.list_product_summary(
            start_date, end_date, big_category, small_category, sku,
            max(page, 1), max(1, min(page_size, 200)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data, request_id=request.state.request_id)


@router.get("/ebay-sop-after-sales/categories")
def get_ebay_sop_after_sales_categories(request: Request):
    return success_response(
        {"big_categories": list(BIG_CATEGORIES), "rules": amz_sop_repo.category_rules()},
        request_id=request.state.request_id,
    )


@router.get("/ebay-sop-after-sales/periods")
def get_ebay_sop_after_sales_periods(request: Request, limit: int = 24):
    return success_response(
        ebay_sop_service.list_periods(limit),
        request_id=request.state.request_id,
    )


@router.post("/ebay-sop-after-sales/sales-imports", status_code=201)
async def post_ebay_sop_sales_import(
    request: Request,
    file: UploadFile = File(...),
    operator: str | None = None,
):
    return await _run_ebay_sop_import(
        request, file, operator, ebay_sop_service.import_ebay_sales, "eBay销量"
    )


@router.post("/ebay-sop-after-sales/history-imports", status_code=201)
async def post_ebay_sop_history_import(
    request: Request,
    file: UploadFile = File(...),
    operator: str | None = None,
):
    return await _run_ebay_sop_import(
        request, file, operator, ebay_sop_service.import_ebay_history, "eBay历史售后"
    )


@router.post("/ebay-sop-after-sales/after-sales-imports", status_code=201)
async def post_ebay_sop_after_sales_import(
    request: Request,
    file: UploadFile = File(...),
    operator: str | None = None,
):
    return await _run_ebay_sop_import(
        request, file, operator, ebay_sop_service.import_ebay_after_sales, "eBay售后"
    )


async def _run_ebay_sop_import(request, file, operator, importer, label):
    content, file_name = await read_excel_upload(file)
    try:
        result = await run_in_threadpool(importer, content, file_name, operator)
        return success_response(
            result,
            request_id=request.state.request_id,
            message=f"{label} imported",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{label}导入失败: {exc}") from exc


@router.get("/ebay-sop-after-sales/exports")
def get_ebay_sop_after_sales_export(
    request: Request,
    start_date: date,
    end_date: date,
):
    content = ebay_sop_service.export_summary(start_date, end_date)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"eBay-SOP售后表-{start_date}-{end_date}-{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/ebay-sop-after-sales/data-exports")
def get_ebay_sop_after_sales_data_export(
    request: Request,
    start_date: date,
    end_date: date,
    big_category: str | None = None,
    small_category: str | None = None,
    sku: str | None = None,
    skus: str | None = None,
):
    selected_skus = [value.strip() for value in (skus or "").split(",") if value.strip()]
    content = ebay_sop_service.export_filtered_summary(
        start_date, end_date, big_category, small_category, sku, selected_skus or None
    )
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"eBay-SOP售后数据-{start_date}-{end_date}-{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
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


@router.get("/slow-moving-clearance/months")
def get_slow_moving_clearance_months(request: Request, limit: int = 24):
    return success_response(
        clearance_repo.months(limit),
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
        data = rebuild_monthly_inventory_report(payload.stat_month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"月度库存报表重建失败: {exc}") from exc
    return success_response(
        data,
        request_id=request.state.request_id,
        message="monthly inventory report rebuilt",
    )


@router.post("/slow-moving-clearance/inventory-age-cost-imports", status_code=201)
async def post_inventory_age_cost_import(
    request: Request,
    file: UploadFile = File(...),
    operator: str | None = None,
):
    content, file_name = await read_excel_upload(file)
    try:
        result = await run_in_threadpool(
            import_inventory_age_cost,
            content,
            file_name,
            operator,
        )
        return success_response(
            result,
            request_id=request.state.request_id,
            message="inventory age cost imported",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"库存成本导入失败: {exc}") from exc


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
    operator: str | None = None,
):
    try:
        content = await file.read()
        result = await run_in_threadpool(
            import_ebay_profit,
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
