from __future__ import annotations

import json
import logging
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.integrations.lingxing.domains.inventory import LingXingInventoryDomain
from backend.repositories import inventory_report_source_repository as repo
from backend.services.inventory_report_etl_service import (
    rebuild_monthly_inventory_report,
)
from backend.schemas.inventory_report_source_fields import (
    FBA_SOURCE_FIELDS,
    JSON_SOURCE_FIELDS,
    LOCAL_SOURCE_FIELDS,
    OVERSEAS_SOURCE_FIELDS,
)


TASK_CODE = "monthly_inventory_report_source_sync"
TASK_NAME = "领星月度库存报表三接口源数据同步"

FBA_PATH = "cost/center/openApi/fba/detail/query"
OVERSEAS_PATH = "inventory/center/openapi/storageReport/overseas/detail/page"
LOCAL_PATH = "inventory/center/openapi/storageReport/local/detail/page"

FBA_PAGE_SIZE = 2100
# 海外仓文档没有声明上限，采用同类本地仓接口的最大值 100。
OVERSEAS_PAGE_SIZE = 100
LOCAL_PAGE_SIZE = 100
MAX_PAGES = 10000
PAGE_INTERVAL_SECONDS = 1.1

LOG = logging.getLogger(__name__)


class InventoryReportSourceSyncError(RuntimeError):
    def __init__(self, stage: str, message: str, metrics: dict[str, Any]):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics


def sync_monthly_inventory_report_sources(stat_month: str | None = None) -> dict:
    month, query_start, query_end = _month_scope(stat_month)
    batch_id = str(uuid4())
    pulled_at = datetime.now()
    metrics: dict[str, Any] = {
        "stat_month": month,
        "sync_batch_id": batch_id,
        "extract_rows": 0,
        "ods_rows": 0,
        "fba_rows": 0,
        "overseas_rows": 0,
        "local_rows": 0,
    }

    try:
        seller_ids = repo.amazon_seller_ids()
        if not seller_ids:
            raise ValueError(
                "jmh_data_platform.shop_list 中没有 platform_code=10001 的有效 sid"
            )
        warehouse_wids = repo.warehouse_wids()
        if not warehouse_wids:
            raise ValueError("jmh_data_platform.warehouse 中没有有效 wid")
    except Exception as exc:
        raise InventoryReportSourceSyncError(
            "LOAD_SCOPE", f"读取店铺或仓库范围失败: {exc}", metrics
        ) from exc

    domain = LingXingInventoryDomain()
    try:
        fba_rows = _fetch_fba(
            domain,
            month,
            query_start,
            query_end,
            seller_ids,
            batch_id,
            pulled_at,
        )
        metrics["fba_rows"] = len(fba_rows)
        metrics["extract_rows"] += len(fba_rows)

        overseas_rows = _fetch_warehouse_report(
            domain=domain,
            source="overseas",
            path=OVERSEAS_PATH,
            fields=OVERSEAS_SOURCE_FIELDS,
            page_size=OVERSEAS_PAGE_SIZE,
            month=month,
            query_start=query_start,
            query_end=query_end,
            warehouse_wids=warehouse_wids,
            batch_id=batch_id,
            pulled_at=pulled_at,
        )
        metrics["overseas_rows"] = len(overseas_rows)
        metrics["extract_rows"] += len(overseas_rows)

        local_rows = _fetch_warehouse_report(
            domain=domain,
            source="local",
            path=LOCAL_PATH,
            fields=LOCAL_SOURCE_FIELDS,
            page_size=LOCAL_PAGE_SIZE,
            month=month,
            query_start=query_start,
            query_end=query_end,
            warehouse_wids=warehouse_wids,
            batch_id=batch_id,
            pulled_at=pulled_at,
        )
        metrics["local_rows"] = len(local_rows)
        metrics["extract_rows"] += len(local_rows)
    except InventoryReportSourceSyncError:
        raise
    except Exception as exc:
        raise InventoryReportSourceSyncError(
            "EXTRACT", f"领星库存报表源数据拉取失败: {exc}", metrics
        ) from exc

    try:
        replace_stats = repo.replace_source_month(
            month,
            {
                "fba": fba_rows,
                "overseas": overseas_rows,
                "local": local_rows,
            },
        )
    except Exception as exc:
        raise InventoryReportSourceSyncError(
            "LOAD_ODS", f"库存报表源数据整月替换失败: {exc}", metrics
        ) from exc

    metrics["ods_deleted_rows"] = replace_stats["deleted_rows"]
    metrics["ods_rows"] = replace_stats["inserted_rows"]

    try:
        etl_result = rebuild_monthly_inventory_report(month)
    except Exception as exc:
        raise InventoryReportSourceSyncError(
            "TRANSFORM", f"库存报表清洗与汇总失败: {exc}", metrics
        ) from exc

    metrics["etl"] = etl_result
    metrics["dwd_rows"] = (
        etl_result["fba_detail_rows"]
        + etl_result["overseas_detail_rows"]
        + etl_result["local_detail_rows"]
    )
    metrics["summary_rows"] = (
        etl_result["dimension_summary_rows"]
        + etl_result["department_summary_rows"]
    )
    metrics["inserted_rows"] = etl_result["inserted_rows"]
    metrics["deleted_rows"] = (
        replace_stats["deleted_rows"] + etl_result["deleted_rows"]
    )
    return {**metrics, "status": "completed"}


def _fetch_fba(
    domain: LingXingInventoryDomain,
    month: str,
    query_start: str,
    query_end: str,
    seller_ids: list[str],
    batch_id: str,
    pulled_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    for page in range(1, MAX_PAGES + 1):
        response = domain.request(
            FBA_PATH,
            {
                "offset": offset,
                "length": FBA_PAGE_SIZE,
                "start_date": query_start,
                "end_date": query_end,
                "seller_id": seller_ids,
            },
        )
        _ensure_success(response, "FBA")
        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("领星FBA库存报表响应 data 不是对象")
        batch = data.get("row_data") or []
        if not isinstance(batch, list):
            raise RuntimeError("领星FBA库存报表响应 row_data 不是数组")
        total = _int_or_none(data.get("total"))
        meta = _response_meta(response, data, total)
        for item in batch:
            if not isinstance(item, dict):
                continue
            rows.append(
                _source_payload(
                    item=item,
                    fields=FBA_SOURCE_FIELDS,
                    month=month,
                    query_start=query_start,
                    query_end=query_end,
                    request_scope={"seller_id": seller_ids},
                    batch_id=batch_id,
                    page=page,
                    offset=offset,
                    row_no=len(rows) + 1,
                    meta=meta,
                    pulled_at=pulled_at,
                )
            )
        if not batch or len(batch) < FBA_PAGE_SIZE or (
            total is not None and len(rows) >= total
        ):
            return rows
        offset += FBA_PAGE_SIZE
        time.sleep(PAGE_INTERVAL_SECONDS)
    raise RuntimeError(f"领星FBA库存报表超过最大分页限制: {MAX_PAGES}页")


def _fetch_warehouse_report(
    *,
    domain: LingXingInventoryDomain,
    source: str,
    path: str,
    fields: tuple[str, ...],
    page_size: int,
    month: str,
    query_start: str,
    query_end: str,
    warehouse_wids: list[str],
    batch_id: str,
    pulled_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    scope = ",".join(warehouse_wids)
    for page in range(1, MAX_PAGES + 1):
        response = domain.request(
            path,
            {
                "offset": page,
                "length": page_size,
                "start_date": query_start,
                "end_date": query_end,
                "sys_wid": scope,
            },
        )
        _ensure_success(response, "海外仓" if source == "overseas" else "本地仓")
        batch = response.get("data") or []
        if not isinstance(batch, list):
            raise RuntimeError(f"领星{source}库存报表响应 data 不是数组")
        total = _int_or_none(response.get("total"))
        meta = _response_meta(response, {}, total)
        for item in batch:
            if not isinstance(item, dict):
                continue
            rows.append(
                _source_payload(
                    item=item,
                    fields=fields,
                    month=month,
                    query_start=query_start,
                    query_end=query_end,
                    request_scope={"sys_wid": warehouse_wids},
                    batch_id=batch_id,
                    page=page,
                    offset=page,
                    row_no=len(rows) + 1,
                    meta=meta,
                    pulled_at=pulled_at,
                )
            )
        if not batch or len(batch) < page_size or (
            total is not None and len(rows) >= total
        ):
            return rows
        time.sleep(PAGE_INTERVAL_SECONDS)
    raise RuntimeError(f"领星{source}库存报表超过最大分页限制: {MAX_PAGES}页")


def _source_payload(
    *,
    item: dict[str, Any],
    fields: tuple[str, ...],
    month: str,
    query_start: str,
    query_end: str,
    request_scope: dict[str, Any],
    batch_id: str,
    page: int,
    offset: int,
    row_no: int,
    meta: dict[str, Any],
    pulled_at: datetime,
) -> dict[str, Any]:
    payload = {
        "stat_month": month,
        "sync_batch_id": batch_id,
        "query_start_date": query_start,
        "query_end_date": query_end,
        "request_scope_json": _json(request_scope),
        "source_page": page,
        "source_offset": offset,
        "source_row_no": row_no,
        **meta,
        "raw_row_json": _json(item),
        "pulled_at": pulled_at,
    }
    for field in fields:
        value = item.get(field)
        payload[field] = _json(value) if field in JSON_SOURCE_FIELDS else _scalar(value)
    return payload


def _response_meta(
    response: dict[str, Any],
    data: dict[str, Any],
    total: int | None,
) -> dict[str, Any]:
    return {
        "api_code": _scalar(response.get("code")),
        "api_message": _scalar(response.get("message") or response.get("msg")),
        "api_trace_id": _scalar(response.get("traceId")),
        "api_request_id": _scalar(response.get("request_id")),
        "api_response_time": _scalar(response.get("response_time")),
        "api_error_details": _json(response.get("error_details")),
        "api_total": total,
        "api_start_date": _scalar(data.get("start_date")),
        "api_end_date": _scalar(data.get("end_date")),
        "api_day_interval": _int_or_none(data.get("day_interval")),
        "api_amount_type": _scalar(data.get("amount_type")),
        "api_size": _int_or_none(data.get("size")),
        "api_current": _int_or_none(data.get("current")),
    }


def _ensure_success(response: Any, name: str) -> None:
    if not isinstance(response, dict):
        raise RuntimeError(f"领星{name}库存报表响应为空")
    if str(response.get("code")).lower() not in {"0", "200", "ok", "success"}:
        raise RuntimeError(
            f"领星{name}库存报表失败: code={response.get('code')}, "
            f"message={response.get('message') or response.get('msg')}, "
            f"error_details={response.get('error_details')}"
        )


def _month_scope(
    value: str | None,
    today: date | None = None,
) -> tuple[str, str, str]:
    if value:
        month = value
    else:
        current_day = today or date.today()
        previous_month_day = current_day.replace(day=1) - timedelta(days=1)
        month = previous_month_day.strftime("%Y-%m")
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("stat_month 必须使用 YYYY-MM 格式") from exc
    normalized = parsed.strftime("%Y-%m")
    last_day = monthrange(parsed.year, parsed.month)[1]
    return normalized, f"{normalized}-01", f"{normalized}-{last_day:02d}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return _json(value)
    return str(value)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value) != "" else None
    except (TypeError, ValueError):
        LOG.warning("领星库存报表整数字段无法转换，按空值保存: %r", value)
        return None
