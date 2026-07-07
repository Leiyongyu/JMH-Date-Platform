"""同步领星本地仓库存报表明细到 STG/ODS。

规则：
- ODS 为空时默认全量拉取最近 3 年。
- ODS 已有数据时默认滚动拉取最近 3 天。
- 可通过 force_full=True 强制全量。
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable

from sqlalchemy import text

from app.clients.lingxing_client import LingxingClient
from app.core.config import settings
from app.db.report import report_engine


JOB_CODE = "sync_lingxing_local_inventory"
PAGE_SIZE = 100


def _client() -> LingxingClient:
    return LingxingClient(
        endpoint=settings.lingxing_endpoint,
        app_id=settings.lingxing_app_id,
        app_secret=settings.lingxing_app_secret,
        connect_timeout=settings.lingxing_connect_timeout,
        read_timeout=settings.lingxing_read_timeout,
        token_refresh_skew_seconds=settings.lingxing_token_refresh_skew_seconds,
    )


def _safe_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _safe_int(value) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_str(value) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _month_windows(start: date, end: date) -> Iterable[tuple[date, date]]:
    current = start
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        window_end = min(date(current.year, current.month, last_day), end)
        yield current, window_end
        current = window_end + timedelta(days=1)


def _day_windows(start: date, end: date) -> Iterable[tuple[date, date]]:
    current = start
    while current <= end:
        yield current, current
        current += timedelta(days=1)


def _extract_rows(response: dict) -> tuple[list[dict], int | None]:
    payload = response.get("data")
    total = response.get("total")
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("list") or payload.get("rows") or []
        total = payload.get("total", total)
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    if total is not None:
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = None
    return rows if isinstance(rows, list) else [], total


def _row_hash(row: dict, report_start: date, report_end: date, is_total_row: int) -> str:
    key = {
        "report_start_date": report_start.isoformat(),
        "report_end_date": report_end.isoformat(),
        "sys_wid": _safe_int(row.get("sys_wid")),
        "sku": _safe_str(row.get("sku")),
        "fnsku": _safe_str(row.get("fnsku")),
        "attribute_text": _safe_str(row.get("attribute_text")),
        "is_total_row": is_total_row,
    }
    return hashlib.md5(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _to_ods_params(
    row: dict,
    *,
    batch_id: str,
    report_start: date,
    report_end: date,
    raw_id: int,
    is_total_row: int,
) -> dict:
    return {
        "batch_id": batch_id,
        "report_start_date": report_start,
        "report_end_date": report_end,
        "source_system": "LINGXING",
        "warehouse_type": "LOCAL",
        "sys_wid": _safe_int(row.get("sys_wid")),
        "ware_house_name": row.get("ware_house_name"),
        "seller_name": row.get("seller_name"),
        "sku": _safe_str(row.get("sku")),
        "fnsku": _safe_str(row.get("fnsku")),
        "spu": row.get("spu"),
        "spu_name": row.get("spu_name"),
        "product_name": row.get("product_name"),
        "product_type": row.get("product_type"),
        "brand": row.get("brand"),
        "category1": row.get("category1"),
        "category2": row.get("category2"),
        "category3": row.get("category3"),
        "attribute_text": _safe_str(row.get("attribute_text")),
        "is_total_row": is_total_row,
        "day_early_count": _safe_decimal(row.get("day_early_count")),
        "day_early_cost": _safe_decimal(row.get("day_early_cost")),
        "day_end_count": _safe_decimal(row.get("day_end_count")),
        "day_end_cost": _safe_decimal(row.get("day_end_cost")),
        "cost_adjustment": _safe_decimal(row.get("cost_adjustment")),
        "purchase_in_count": _safe_decimal(row.get("purchase_in_count")),
        "purchase_in_cost": _safe_decimal(row.get("purchase_in_cost")),
        "allocation_in_count": _safe_decimal(row.get("allocation_in_count")),
        "allocation_in_cost": _safe_decimal(row.get("allocation_in_cost")),
        "other_in_count": _safe_decimal(row.get("other_in_count")),
        "other_in_cost": _safe_decimal(row.get("other_in_cost")),
        "allocation_out_count": _safe_decimal(row.get("allocation_out_count")),
        "allocation_out_cost": _safe_decimal(row.get("allocation_out_cost")),
        "fba_out_count": _safe_decimal(row.get("fba_out_count")),
        "fba_out_cost": _safe_decimal(row.get("fba_out_cost")),
        "fbm_out_count": _safe_decimal(row.get("fbm_out_count")),
        "fbm_out_cost": _safe_decimal(row.get("fbm_out_cost")),
        "other_out_count": _safe_decimal(row.get("other_out_count")),
        "other_out_cost": _safe_decimal(row.get("other_out_cost")),
        "raw_id": raw_id,
        "row_hash": _row_hash(row, report_start, report_end, is_total_row),
    }


INSERT_STG_SQL = text(
    """
    INSERT INTO stg_lingxing_local_inventory_report_raw (
        batch_id, request_start_date, request_end_date, page_no, row_no,
        request_id, response_time, source_system, warehouse_type,
        sys_wid, ware_house_name, seller_name, sku, fnsku, spu,
        product_name, attribute_text, raw_json
    ) VALUES (
        :batch_id, :request_start_date, :request_end_date, :page_no, :row_no,
        :request_id, :response_time, :source_system, :warehouse_type,
        :sys_wid, :ware_house_name, :seller_name, :sku, :fnsku, :spu,
        :product_name, :attribute_text, :raw_json
    )
    """
)


UPSERT_ODS_SQL = text(
    """
    INSERT INTO ods_lingxing_local_inventory_report_detail (
        batch_id, report_start_date, report_end_date, source_system, warehouse_type,
        sys_wid, ware_house_name, seller_name, sku, fnsku, spu, spu_name,
        product_name, product_type, brand, category1, category2, category3,
        attribute_text, is_total_row,
        day_early_count, day_early_cost, day_end_count, day_end_cost, cost_adjustment,
        purchase_in_count, purchase_in_cost, allocation_in_count, allocation_in_cost,
        other_in_count, other_in_cost, allocation_out_count, allocation_out_cost,
        fba_out_count, fba_out_cost, fbm_out_count, fbm_out_cost,
        other_out_count, other_out_cost, raw_id, row_hash
    ) VALUES (
        :batch_id, :report_start_date, :report_end_date, :source_system, :warehouse_type,
        :sys_wid, :ware_house_name, :seller_name, :sku, :fnsku, :spu, :spu_name,
        :product_name, :product_type, :brand, :category1, :category2, :category3,
        :attribute_text, :is_total_row,
        :day_early_count, :day_early_cost, :day_end_count, :day_end_cost, :cost_adjustment,
        :purchase_in_count, :purchase_in_cost, :allocation_in_count, :allocation_in_cost,
        :other_in_count, :other_in_cost, :allocation_out_count, :allocation_out_cost,
        :fba_out_count, :fba_out_cost, :fbm_out_count, :fbm_out_cost,
        :other_out_count, :other_out_cost, :raw_id, :row_hash
    )
    ON DUPLICATE KEY UPDATE
        batch_id = VALUES(batch_id),
        ware_house_name = VALUES(ware_house_name),
        seller_name = VALUES(seller_name),
        spu = VALUES(spu),
        spu_name = VALUES(spu_name),
        product_name = VALUES(product_name),
        product_type = VALUES(product_type),
        brand = VALUES(brand),
        category1 = VALUES(category1),
        category2 = VALUES(category2),
        category3 = VALUES(category3),
        day_early_count = VALUES(day_early_count),
        day_early_cost = VALUES(day_early_cost),
        day_end_count = VALUES(day_end_count),
        day_end_cost = VALUES(day_end_cost),
        cost_adjustment = VALUES(cost_adjustment),
        purchase_in_count = VALUES(purchase_in_count),
        purchase_in_cost = VALUES(purchase_in_cost),
        allocation_in_count = VALUES(allocation_in_count),
        allocation_in_cost = VALUES(allocation_in_cost),
        other_in_count = VALUES(other_in_count),
        other_in_cost = VALUES(other_in_cost),
        allocation_out_count = VALUES(allocation_out_count),
        allocation_out_cost = VALUES(allocation_out_cost),
        fba_out_count = VALUES(fba_out_count),
        fba_out_cost = VALUES(fba_out_cost),
        fbm_out_count = VALUES(fbm_out_count),
        fbm_out_cost = VALUES(fbm_out_cost),
        other_out_count = VALUES(other_out_count),
        other_out_cost = VALUES(other_out_cost),
        raw_id = VALUES(raw_id),
        row_hash = VALUES(row_hash)
    """
)


def _insert_stg(conn, row: dict, *, batch_id: str, report_start: date, report_end: date,
                page_no: int, row_no: int, response: dict) -> int:
    result = conn.execute(
        INSERT_STG_SQL,
        {
            "batch_id": batch_id,
            "request_start_date": report_start,
            "request_end_date": report_end,
            "page_no": page_no,
            "row_no": row_no,
            "request_id": response.get("request_id"),
            "response_time": _parse_datetime(response.get("response_time")),
            "source_system": "LINGXING",
            "warehouse_type": "LOCAL",
            "sys_wid": _safe_int(row.get("sys_wid")),
            "ware_house_name": row.get("ware_house_name"),
            "seller_name": row.get("seller_name"),
            "sku": _safe_str(row.get("sku")),
            "fnsku": _safe_str(row.get("fnsku")),
            "spu": row.get("spu"),
            "product_name": row.get("product_name"),
            "attribute_text": _safe_str(row.get("attribute_text")),
            "raw_json": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
        },
    )
    return int(result.lastrowid)


def _write_rows(conn, rows: list[dict], *, batch_id: str, report_start: date,
                report_end: date, page_no: int, response: dict) -> tuple[int, int]:
    stg_rows = 0
    ods_rows = 0
    for idx, row in enumerate(rows, start=1):
        raw_id = _insert_stg(
            conn,
            row,
            batch_id=batch_id,
            report_start=report_start,
            report_end=report_end,
            page_no=page_no,
            row_no=idx,
            response=response,
        )
        stg_rows += 1

        conn.execute(
            UPSERT_ODS_SQL,
            _to_ods_params(
                row,
                batch_id=batch_id,
                report_start=report_start,
                report_end=report_end,
                raw_id=raw_id,
                is_total_row=1,
            ),
        )
        ods_rows += 1

        child_list = row.get("child_list")
        if isinstance(child_list, list):
            for child in child_list:
                if not isinstance(child, dict):
                    continue
                conn.execute(
                    UPSERT_ODS_SQL,
                    _to_ods_params(
                        child,
                        batch_id=batch_id,
                        report_start=report_start,
                        report_end=report_end,
                        raw_id=raw_id,
                        is_total_row=0,
                    ),
                )
                ods_rows += 1

    return stg_rows, ods_rows


def _decide_range(force_full: bool, start_date: date | None = None, end_date: date | None = None) -> tuple[str, date, date]:
    if start_date or end_date:
        if not start_date or not end_date:
            raise ValueError("start_date 和 end_date 必须同时提供")
        if start_date > end_date:
            raise ValueError("start_date 不能大于 end_date")
        return "CUSTOM", start_date, end_date

    today = date.today()
    if force_full:
        return "FULL", _subtract_years(today, 3), today

    with report_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM ods_lingxing_local_inventory_report_detail")).scalar() or 0
    if count == 0:
        return "FULL", _subtract_years(today, 3), today
    return "INCREMENTAL", today - timedelta(days=3), today


def sync_lingxing_local_inventory(
    force_full: bool = False,
    sleep_seconds: float = 0.35,
    start_date: date | None = None,
    end_date: date | None = None,
    sys_wid: str | None = None,
    use_config_wids: bool = True,
    empty_page_retries: int = 3,
) -> dict:
    mode, start, end = _decide_range(force_full, start_date, end_date)
    windows = list(_month_windows(start, end)) if mode == "FULL" else list(_day_windows(start, end))
    batch_id = f"lingxing_local_inventory_{mode.lower()}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now()

    total_stg_rows = 0
    total_ods_rows = 0
    total_pages = 0
    status = "success"
    error_message = None

    with report_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO etl_batch (batch_id, batch_type, status, start_time) VALUES (:batch_id, :batch_type, 'running', :start_time)"),
            {"batch_id": batch_id, "batch_type": JOB_CODE, "start_time": started_at},
        )
        conn.execute(
            text("INSERT INTO etl_job_log (job_code, batch_id, status, start_time) VALUES (:job_code, :batch_id, 'running', :start_time)"),
            {"job_code": JOB_CODE, "batch_id": batch_id, "start_time": started_at},
        )

    client = _client()

    try:
        for window_start, window_end in windows:
            page_no = 1
            while True:
                request_sys_wid = sys_wid
                if request_sys_wid is None and use_config_wids:
                    request_sys_wid = settings.lingxing_inventory_wids or None

                response = client.get_local_inventory_report_page(
                    start_date=window_start.isoformat(),
                    end_date=window_end.isoformat(),
                    offset=page_no,
                    length=PAGE_SIZE,
                    sys_wid=request_sys_wid,
                )
                rows, total = _extract_rows(response)
                retry_count = 0
                while (
                    not rows
                    and isinstance(total, int)
                    and page_no > 1
                    and (page_no - 1) * PAGE_SIZE < total
                    and retry_count < empty_page_retries
                ):
                    retry_count += 1
                    time.sleep(max(sleep_seconds, 1))
                    response = client.get_local_inventory_report_page(
                        start_date=window_start.isoformat(),
                        end_date=window_end.isoformat(),
                        offset=page_no,
                        length=PAGE_SIZE,
                        sys_wid=request_sys_wid,
                    )
                    rows, total = _extract_rows(response)
                if not rows:
                    break

                with report_engine.begin() as conn:
                    stg_count, ods_count = _write_rows(
                        conn,
                        rows,
                        batch_id=batch_id,
                        report_start=window_start,
                        report_end=window_end,
                        page_no=page_no,
                        response=response,
                    )
                total_stg_rows += stg_count
                total_ods_rows += ods_count
                total_pages += 1

                print(
                    f"[{mode}] {window_start}~{window_end} page={page_no} "
                    f"rows={len(rows)} total={total} stg={total_stg_rows} ods={total_ods_rows}",
                    flush=True,
                )

                if len(rows) < PAGE_SIZE:
                    break
                if isinstance(total, int) and page_no * PAGE_SIZE >= total:
                    break
                page_no += 1
                time.sleep(sleep_seconds)

        return {
            "batch_id": batch_id,
            "mode": mode,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "windows": len(windows),
            "pages": total_pages,
            "stg_rows": total_stg_rows,
            "ods_rows": total_ods_rows,
        }
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        ended_at = datetime.now()
        duration = int((ended_at - started_at).total_seconds())
        with report_engine.begin() as conn:
            conn.execute(
                text("UPDATE etl_batch SET status=:status, end_time=:end_time WHERE batch_id=:batch_id"),
                {"status": status, "end_time": ended_at, "batch_id": batch_id},
            )
            conn.execute(
                text(
                    "UPDATE etl_job_log SET status=:status, end_time=:end_time, duration_seconds=:duration_seconds, "
                    "read_count=:read_count, insert_count=:insert_count, update_count=:update_count, "
                    "error_count=:error_count, error_message=:error_message "
                    "WHERE job_code=:job_code AND batch_id=:batch_id"
                ),
                {
                    "status": status,
                    "end_time": ended_at,
                    "duration_seconds": duration,
                    "read_count": total_stg_rows,
                    "insert_count": total_ods_rows,
                    "update_count": 0,
                    "error_count": 1 if status == "failed" else 0,
                    "error_message": error_message,
                    "job_code": JOB_CODE,
                    "batch_id": batch_id,
                },
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="强制全量拉取最近 3 年")
    parser.add_argument("--start-date", help="指定拉取开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", help="指定拉取结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--sys-wid", help="指定领星仓库ID，多个用英文逗号分隔")
    parser.add_argument("--all-warehouses", action="store_true", help="不使用配置中的仓库ID限制，拉取接口默认范围")
    parser.add_argument("--sleep-seconds", type=float, default=0.35, help="分页请求间隔秒数")
    args = parser.parse_args()
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else None
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None
    result = sync_lingxing_local_inventory(
        force_full=args.full,
        sleep_seconds=args.sleep_seconds,
        start_date=start_date,
        end_date=end_date,
        sys_wid=args.sys_wid,
        use_config_wids=not args.all_warehouses,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
