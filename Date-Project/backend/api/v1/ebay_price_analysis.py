"""eBay 价格分析 BI 的内部接口；终端用户的菜单与导出列权限由 Java 侧控制。

overview / detail / export 只读 dws_ebay_price_analysis，状态列是刷表时算好的，
这里不再推导。刷表只由定时任务 ebay_price_analysis_refresh 执行，不提供页面触发接口。
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


def _run(request: Request, action, label: str):
    try:
        return success_response(action(), request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("eBay价格分析%s失败", label)
        raise HTTPException(
            status_code=500,
            detail=f"eBay价格分析{label}失败，请确认 20261110_ebay_price_analysis.sql "
                   "已执行并检查服务日志",
        ) from exc


@router.get("/overview")
def get_overview(
    request: Request,
    stat_date: str | None = Query(None, max_length=10),
    sites: str | None = Query(None, max_length=200),
    accounts: str | None = Query(None, max_length=4000),
    status: str | None = Query(None, max_length=200),
    keyword: str | None = Query(None, max_length=128),
    dimension: str = Query("sku", max_length=8),
):
    return _run(request, lambda: service.overview(
        stat_date=stat_date, sites=sites, accounts=accounts, status=status,
        keyword=keyword, dimension=dimension), "看板查询")


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
):
    return _run(request, lambda: service.detail(
        stat_date=stat_date, sites=sites, accounts=accounts, status=status,
        keyword=keyword, sku=sku, mid_code_filter=mid_code, mode=mode, page=page,
        page_size=page_size, sort_by=sort_by, sort_order=sort_order), "明细查询")


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
):
    """返回 xlsx 流。columns 是 Java 按 exportColumn:* 过滤后的列，不传导全部。"""
    try:
        filename, content = service.export(
            columns=columns, mode=mode, stat_date=stat_date, sites=sites,
            accounts=accounts, status=status, keyword=keyword, sku=sku,
            mid_code_filter=mid_code, sort_by=sort_by, sort_order=sort_order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("eBay价格分析导出失败")
        raise HTTPException(status_code=500, detail="eBay价格分析导出失败，请检查服务日志") from exc
    return Response(content, media_type=service.EXCEL_CONTENT_TYPE, headers={
        "Content-Disposition": "attachment; filename=ebay-price-analysis.xlsx; "
                               f"filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
    })

