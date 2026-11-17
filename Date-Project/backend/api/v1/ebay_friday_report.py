"""eBay「周五数据」内部接口（运营中心 / eBay / 数据报表）；终端用户权限由 Java 侧控制。

数据由周五定时任务生成快照；页面只读两张表、维护店铺主站点、导出，以及有权限时用现有快照重新生成。
"""
from __future__ import annotations

import logging
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ebay_friday_order_sales_service as order_sales
from backend.services import ebay_friday_report_service as service

router = APIRouter(
    prefix="/api/v1/finance/ebay-friday-report",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)
DATE_PATTERN = r"^20\d{2}-\d{2}-\d{2}$"


def _run(action, label: str):
    try:
        return success_response(action())
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except service.EbayFridayReportError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        if service.repo.missing_table(exc):
            raise HTTPException(400, detail=service.repo.MIGRATION_MESSAGE) from exc
        LOG.exception("周五数据%s失败", label)
        raise HTTPException(500, detail=f"周五数据{label}失败，请检查服务日志") from exc


def _params(**values):
    return {key: value for key, value in values.items() if value not in (None, "")}


@router.get("/overview")
def overview(report_date: str | None = Query(None, pattern=DATE_PATTERN)):
    return _run(lambda: service.overview(report_date), "查询")


@router.get("/listings")
def listings(report_date: str | None = Query(None, pattern=DATE_PATTERN), keyword: str | None = None,
             site: str | None = None, store_name: str | None = None, principal_name: str | None = None,
             flag: str | None = None, sort_field: str | None = None, sort_order: str | None = None,
             page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    params = _params(report_date=report_date, keyword=keyword, site=site, store_name=store_name,
                     principal_name=principal_name, flag=flag, sort_field=sort_field, sort_order=sort_order,
                     page=page, page_size=page_size)
    return _run(lambda: service.listing_page(params), "有货无货查询")


@router.get("/stocks")
def stocks(report_date: str | None = Query(None, pattern=DATE_PATTERN), keyword: str | None = None,
           site: str | None = None, brand: str | None = None, principal_name: str | None = None,
           flag: str | None = None, sort_field: str | None = None, sort_order: str | None = None,
           page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    params = _params(report_date=report_date, keyword=keyword, site=site, brand=brand,
                     principal_name=principal_name, flag=flag, sort_field=sort_field, sort_order=sort_order,
                     page=page, page_size=page_size)
    return _run(lambda: service.stock_page(params), "海外仓库存查询")


@router.post("/generate")
def generate(payload: dict = Body(default={})):
    return _run(lambda: service.generate(operator=payload.get("operator") or "manual"), "生成")


@router.put("/stores")
def save_store(payload: dict = Body(...)):
    return _run(lambda: service.save_store(payload, payload.get("operator")), "店铺主站点保存")


@router.delete("/stores/{store_key}")
def delete_store(store_key: str):
    return _run(lambda: service.delete_store(store_key), "店铺主站点删除")


@router.get("/order-sales")
def order_sales_summary():
    return _run(order_sales.summary, "订单售出统计查询")


@router.post("/order-sales/import")
async def import_order_sales(file: UploadFile = File(...), operator: str | None = Query(None, max_length=64)):
    try:
        content = await file.read(order_sales.MAX_FILE_BYTES + 1)
        result = await run_in_threadpool(order_sales.import_orders, content, file.filename or "订单导出.xlsx", operator)
        return success_response(result)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        if exc.args and exc.args[0] == 1146:
            raise HTTPException(400, detail=order_sales.MIGRATION_MESSAGE) from exc
        LOG.exception("周五数据订单售出上传失败")
        raise HTTPException(500, detail="订单售出统计上传失败，请检查服务日志") from exc
    finally:
        await file.close()


@router.get("/exports")
def export(report_date: str | None = Query(None, pattern=DATE_PATTERN)):
    try:
        name, content = service.export(report_date)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("周五数据导出失败")
        raise HTTPException(500, detail="周五数据导出失败，请检查服务日志") from exc
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)},
    )
