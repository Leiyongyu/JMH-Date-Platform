"""eBay 价格分析 BI 的内部接口；终端用户的菜单与导出列权限由 Java 侧控制。

stores / detail / sku-listings / export 只读 dws_ebay_price_analysis，状态列是刷表时算好的，
跨店对比列（同站点同 SKU 的店铺数、可售合计、最低最高价、多店超卖）在查询时派生。
刷表只由定时任务 ebay_price_analysis_refresh 执行，不提供页面触发接口。
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ebay_price_analysis_service as service

router = APIRouter(
    prefix="/api/v1/ebay-price-analysis",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)


def _failure(exc: Exception, label: str) -> HTTPException:
    """统一的失败响应：参数错误 400 原样给；其余 500，带上数据库缺的表/列或错误码，不带 SQL 原文。"""
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    LOG.exception("eBay价格分析%s失败", label)
    return HTTPException(status_code=500,
                         detail=f"eBay价格分析{label}失败：{service.failure_reason(exc)}")


def _run(request: Request, action, label: str):
    try:
        return success_response(action(), request_id=request.state.request_id)
    except Exception as exc:
        raise _failure(exc, label) from exc


@router.get("/stores")
def get_stores(
    request: Request,
    sites: str | None = Query(None, max_length=200),
    accounts: str | None = Query(None, max_length=4000),
):
    return _run(request, lambda: service.stores(sites=sites, accounts=accounts), "店铺汇总查询")


@router.get("/sku-listings")
def get_sku_listings(request: Request, sku: str = Query(..., min_length=1, max_length=255)):
    return _run(request, lambda: service.sku_listings(sku=sku), "SKU跨店查询")


@router.get("/detail")
def get_detail(
    request: Request,
    stat_date: str | None = Query(None, max_length=10),
    sites: str | None = Query(None, max_length=200),
    accounts: str | None = Query(None, max_length=4000),
    status: str | None = Query(None, max_length=200),
    keyword: str | None = Query(None, max_length=128),
    sku: str | None = Query(None, max_length=255),
    mid_code: str | None = Query(None, max_length=128),
    mode: str = Query("detail", max_length=16),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=service.MAX_PAGE_SIZE),
    sort_by: str | None = Query(None, max_length=64),
    sort_order: str = Query("desc", max_length=8),
    site_oversell: bool | None = Query(None),
    out_of_stock_listed: bool | None = Query(None),
    unmatched: bool | None = Query(None),
):
    return _run(request, lambda: service.detail(
        stat_date=stat_date, sites=sites, accounts=accounts, status=status,
        keyword=keyword, sku=sku, mid_code_filter=mid_code, mode=mode, page=page,
        page_size=page_size, sort_by=sort_by, sort_order=sort_order,
        site_oversell=site_oversell, out_of_stock_listed=out_of_stock_listed,
        unmatched=unmatched), "明细查询")


@router.get("/export")
def get_export(
    stat_date: str | None = Query(None, max_length=10),
    sites: str | None = Query(None, max_length=200),
    accounts: str | None = Query(None, max_length=4000),
    status: str | None = Query(None, max_length=200),
    keyword: str | None = Query(None, max_length=128),
    sku: str | None = Query(None, max_length=255),
    mid_code: str | None = Query(None, max_length=128),
    mode: str = Query("detail", max_length=16),
    sort_by: str | None = Query(None, max_length=64),
    sort_order: str = Query("desc", max_length=8),
    columns: str | None = Query(None, max_length=2000),
    site_oversell: bool | None = Query(None),
    out_of_stock_listed: bool | None = Query(None),
    unmatched: bool | None = Query(None),
):
    """返回 xlsx 流。columns 是 Java 按 exportColumn:* 过滤后的列，不传导全部。

    筛选与 /detail 同一套（含多店超卖、断货在售两个标记）；导出列与列权限不变。
    """
    try:
        filename, content = service.export(
            columns=columns, mode=mode, stat_date=stat_date, sites=sites,
            accounts=accounts, status=status, keyword=keyword, sku=sku,
            mid_code_filter=mid_code, sort_by=sort_by, sort_order=sort_order,
            site_oversell=site_oversell, out_of_stock_listed=out_of_stock_listed,
            unmatched=unmatched)
    except Exception as exc:
        raise _failure(exc, "导出") from exc
    return Response(content, media_type=service.EXCEL_CONTENT_TYPE, headers={
        "Content-Disposition": "attachment; filename=ebay-price-analysis.xlsx; "
                               f"filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
    })

