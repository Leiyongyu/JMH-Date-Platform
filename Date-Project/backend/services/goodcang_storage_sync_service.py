"""Full replacement of the rolling 30-day GoodCang rent-summary source."""
from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from backend.integrations.goodcang.client import GoodcangClient, PAGE_SIZE, source_json
from backend.repositories import goodcang_storage_repository as repo

TASK_CODE = "goodcang_wh_inventory_storage_sync"
TASK_NAME = "谷仓仓租概要近30天同步"
CHINA_TIME = timezone(timedelta(hours=8))
MAX_PAGES = 10000
TEXT_LENGTHS = {
    "currency_code": 16, "is_date": 32, "note": 16000, "settlement_currency_code": 16,
    "warehouse_code": 64, "wis_code": 64, "wp_settlement_cycle": 64,
}
NUMERIC_FIELDS = ("isdb_volume", "is_amount", "is_settlement_amount")


class GoodcangStorageSyncError(ValueError):
    def __init__(self, stage, message, metrics):
        super().__init__(message)
        self.stage = stage
        self.metrics = dict(metrics)


def recent_window(now=None):
    now = now or datetime.now(CHINA_TIME)
    if now.tzinfo is not None:
        now = now.astimezone(CHINA_TIME).replace(tzinfo=None)
    end = now.replace(microsecond=0)
    start = datetime.combine(end.date() - timedelta(days=29), time.min)
    return start, end


def _count(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("count必须为非负整数")
    text = str(value)
    if not text.isascii() or not text.isdigit():
        raise ValueError("count必须为非负整数")
    result = int(text)
    if result > MAX_PAGES * PAGE_SIZE:
        raise ValueError("count超过分页安全上限")
    return result


def _decimal(value, field):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{field}不是有效高精度数值")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{field}不是有效高精度数值") from None
    if not result.is_finite() or result.copy_abs() >= Decimal("1e18"):
        raise ValueError(f"{field}超出DECIMAL(30,12)范围")
    # Inspect significant decimals without quantize/context rounding.
    digits = result.as_tuple()
    significant = list(digits.digits)
    exponent = digits.exponent
    while significant and significant[-1] == 0:
        significant.pop()
        exponent += 1
    if significant and exponent < -12:
        raise ValueError(f"{field}精度超过12位小数，拒绝静默舍入")
    return result


def _row(source, page, row_no, count, start, end, batch, pulled_at):
    row = {}
    for field, limit in TEXT_LENGTHS.items():
        value = source.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            raise ValueError(f"{field}类型或长度异常")
        row[field] = value
    row.update({field: _decimal(source.get(field), field) for field in NUMERIC_FIELDS})
    row.update(
        request_date_from=start, request_date_to=end, source_page=page, source_row_no=row_no,
        api_count=count, sync_batch_id=batch, pulled_at=pulled_at, raw_json=source_json(source),
    )
    return row


def sync_goodcang_storage():
    start, end = recent_window()
    batch = str(uuid4())
    metrics = {
        "sync_batch_id": batch, "stat_month": end.strftime("%Y-%m"),
        "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
        "extract_rows": 0, "ods_rows": 0, "inserted_rows": 0, "deleted_rows": 0,
        "page_size": PAGE_SIZE, "page_count": 0,
    }
    rows, seen, expected = [], {}, None
    stage = "EXTRACT"
    try:
        with GoodcangClient() as client:
            for page in range(1, MAX_PAGES + 1):
                response = client.fetch_storage_page(metrics["start_date"], metrics["end_date"], page)
                metrics["page_count"] = page
                # This endpoint is V1. Do not accept a V2 code=0 as success.
                if response.get("ask") != "Success":
                    raise ValueError(f"谷仓仓租V1接口未返回ask=Success；page={page}")
                count = _count(response.get("count"))
                data = response.get("data")
                if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                    raise ValueError(f"谷仓仓租data必须为对象数组；page={page}")
                if expected is not None and expected != count:
                    raise ValueError(f"谷仓仓租拉取期间count发生变化；page={page}")
                expected = count
                if len(data) > PAGE_SIZE or len(rows) + len(data) > count:
                    raise ValueError(f"谷仓仓租分页数量越界；page={page}")
                if len(rows) + len(data) < count and len(data) < PAGE_SIZE:
                    raise ValueError(f"谷仓仓租分页提前结束；page={page}")
                for row_no, source in enumerate(data, 1):
                    fingerprint = hashlib.sha256(source_json(dict(sorted(source.items()))).encode("utf-8")).hexdigest()
                    if fingerprint in seen and seen[fingerprint] != page:
                        raise ValueError(f"谷仓仓租存在跨页重复原始行；page={page}")
                    seen[fingerprint] = page
                    rows.append(_row(source, page, row_no, count, start, end, batch, end))
                    metrics["extract_rows"] = len(rows)
                if len(rows) == count:
                    break
            else:
                raise ValueError("谷仓仓租超过分页安全上限")
        stage = "LOAD"
        metrics.update(repo.replace_storage_rows(rows))
        return metrics
    except Exception as exc:
        # Never leak HTTP bodies, SQL parameter values or credentials to scheduler logs.
        message = str(exc) if stage == "EXTRACT" and isinstance(exc, ValueError) else (
            f"谷仓仓租同步失败；stage={stage} exception_type={type(exc).__name__}"
        )
        raise GoodcangStorageSyncError(stage, message, metrics) from None
