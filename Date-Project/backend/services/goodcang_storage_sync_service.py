"""Rolling GoodCang rent summaries and per-bill details; one atomic snapshot."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from tempfile import TemporaryFile
from time import monotonic
from uuid import uuid4

from backend.integrations.goodcang.client import (
    DETAIL_PAGE_SIZE, DETAIL_PATH, PATH, GoodcangClient, PAGE_SIZE, source_json,
)
from backend.repositories import goodcang_storage_repository as repo

TASK_CODE = "goodcang_wh_inventory_storage_sync"
TASK_NAME = "谷仓仓租概要及明细近30天同步"
CHINA_TIME = timezone(timedelta(hours=8))
LOG = logging.getLogger(__name__)
MAX_PAGES = 10000
MAX_DETAIL_ROWS = 2_000_000
MAX_SPOOL_BYTES = 2 * 1024 * 1024 * 1024
# Bound API extraction to 2.5h, leaving headroom under the existing Java 3h timeout.
MAX_EXTRACT_SECONDS = 9000
TEXT_LENGTHS = {
    "currency_code": 16, "is_date": 32, "note": 16000, "settlement_currency_code": 16,
    "warehouse_code": 64, "wis_code": 64, "wp_settlement_cycle": 64,
}
NUMERIC_FIELDS = ("isdb_volume", "is_amount", "is_settlement_amount")
DETAIL_TEXT_LENGTHS = {
    "wis_code": 64, "reference_no": 255, "warehouse_code": 64,
    "product_sku": 255, "product_barcode": 255, "product_name": 1000,
    "cargo_type": 64, "bill_currency_code": 16, "settlement_currency_code": 16,
    "charge_date": 32, "putaway_date": 32,
}
DETAIL_NUMERIC_FIELDS = (
    "length", "width", "height", "volume", "bill_amount",
    "settlement_amount", "warehouse_rent_amount",
)


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
    digits = result.as_tuple()
    significant = list(digits.digits)
    exponent = digits.exponent
    while significant and significant[-1] == 0:
        significant.pop()
        exponent += 1
    if significant and exponent < -12:
        raise ValueError(f"{field}精度超过12位小数，拒绝静默舍入")
    return result


def _integer(value, field):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{field}必须为整数")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{field}必须为整数") from None
    if (not number.is_finite() or number != number.to_integral_value()
            or not Decimal("-9223372036854775808") <= number <= Decimal("9223372036854775807")):
        raise ValueError(f"{field}不是有效BIGINT整数")
    return int(number)


def _source_fields(source, text_lengths, numeric_fields):
    row = {}
    for field, limit in text_lengths.items():
        value = source.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            raise ValueError(f"{field}类型或长度异常")
        row[field] = value
    row.update({field: _decimal(source.get(field), field) for field in numeric_fields})
    return row


def _metadata(source, page, row_no, count, start, end, batch):
    return dict(
        request_date_from=start, request_date_to=end, source_page=page, source_row_no=row_no,
        api_count=count, sync_batch_id=batch, pulled_at=end, raw_json=source_json(source),
    )


def _detail_row(source, code, page, row_no, count, start, end, batch):
    row = _source_fields(source, DETAIL_TEXT_LENGTHS, DETAIL_NUMERIC_FIELDS)
    returned_code = row.get("wis_code")
    if returned_code and returned_code.strip() and returned_code.strip() != code:
        raise ValueError("仓租明细返回单号与请求不一致")
    row.update({field: _integer(source.get(field), field) for field in ("quantity", "day")})
    row.update(_metadata(source, page, row_no, count, start, end, batch))
    # Missing source wis_code remains NULL; do not invent content in raw_json.
    row["request_wis_code"] = code
    return row


def _pages(fetch, path, metrics, page_counter, *, detail=False):
    """Independent count and paging state for every bill; never deduplicate detail rows."""
    seen, full_pages, expected, received = {}, set(), None, 0
    page_size = DETAIL_PAGE_SIZE if detail else PAGE_SIZE
    for page in range(1, MAX_PAGES + 1):
        metrics["current_page"] = page
        response = fetch(page)
        metrics[page_counter] += 1
        context = f"接口={path} page={page}"
        if not isinstance(response, dict) or response.get("ask") != "Success":
            raise ValueError(f"谷仓仓租V1接口未返回ask=Success；{context}")
        count = _count(response.get("count"))
        data = response.get("data")
        # Unlike summaries, detail data is optional in the V1 specification.
        if detail and count == 0 and data is None:
            data = []
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError(f"谷仓仓租data必须为对象数组；{context}")
        if expected is not None and expected != count:
            raise ValueError(f"谷仓仓租拉取期间count发生变化；{context}")
        expected = count
        if len(data) > page_size or received + len(data) > count:
            raise ValueError(f"谷仓仓租分页数量越界；{context}")
        if received + len(data) < count and len(data) < page_size:
            raise ValueError(f"谷仓仓租分页提前结束；{context}")
        if detail and len(data) == page_size:
            # Detect a server replaying a full page, not individual duplicate batch rows.
            fingerprint = hashlib.sha256(source_json(data).encode("utf-8")).hexdigest()
            if fingerprint in full_pages:
                raise ValueError(f"谷仓仓租明细完整页面重复，拒绝不完整快照；{context}")
            full_pages.add(fingerprint)
        for row_no, source in enumerate(data, 1):
            if not detail:
                fingerprint = hashlib.sha256(source_json(dict(sorted(source.items()))).encode("utf-8")).hexdigest()
                if fingerprint in seen and seen[fingerprint] != page:
                    raise ValueError(f"谷仓仓租存在跨页重复原始行；{context}")
                seen[fingerprint] = page
            yield source, page, row_no, count
        received += len(data)
        if received == count:
            return
    raise ValueError(f"谷仓仓租超过分页安全上限；接口={path}")


def _write_detail(spool, row):
    serialized = dict(row)
    for field in ("request_date_from", "request_date_to", "pulled_at"):
        serialized[field] = serialized[field].isoformat(sep=" ")
    line = source_json(serialized) + "\n"
    return spool.write(line.encode("utf-8"))


def _spooled_rows(spool, expected_count):
    spool.seek(0)
    count = 0
    for line in spool:
        row = json.loads(line, parse_float=Decimal)
        for field in ("request_date_from", "request_date_to", "pulled_at"):
            row[field] = datetime.fromisoformat(row[field])
        count += 1
        yield row
    if count != expected_count:
        raise ValueError("仓租明细临时文件行数不完整，拒绝提交")


def _fetch_with_budget(fetch, deadline):
    if monotonic() >= deadline:
        raise ValueError("仓租概要及明细拉取超过2.5小时预算，保留旧快照")
    response = fetch()
    if monotonic() >= deadline:
        raise ValueError("仓租概要及明细拉取超过2.5小时预算，保留旧快照")
    return response


def sync_goodcang_storage():
    start, end = recent_window()
    deadline = monotonic() + MAX_EXTRACT_SECONDS
    batch = str(uuid4())
    metrics = {
        "sync_batch_id": batch, "stat_month": end.strftime("%Y-%m"),
        "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
        "extract_rows": 0, "ods_rows": 0, "inserted_rows": 0, "deleted_rows": 0,
        "summary_rows": 0, "detail_rows": 0, "bill_count": 0, "completed_bills": 0,
        "empty_detail_bills": 0, "page_size": PAGE_SIZE, "detail_page_size": DETAIL_PAGE_SIZE,
        "page_count": 0, "detail_page_count": 0, "current_bill_index": 0, "current_page": 0,
    }
    summaries, codes = [], {}
    stage = "EXTRACT"
    try:
        # TemporaryFile is removed on close, including API/validation/DB failure.
        with TemporaryFile(mode="w+b") as spool, GoodcangClient() as client:
            for source, page, row_no, count in _pages(
                lambda p: _fetch_with_budget(
                    lambda: client.fetch_storage_page(metrics["start_date"], metrics["end_date"], p), deadline),
                PATH, metrics, "page_count",
            ):
                row = _source_fields(source, TEXT_LENGTHS, NUMERIC_FIELDS)
                row.update(_metadata(source, page, row_no, count, start, end, batch))
                code = (row.get("wis_code") or "").strip()
                if not code or len(code) > 32:
                    raise ValueError("概要缺少有效仓租单号，无法完整拉取明细")
                summaries.append(row)
                codes.setdefault(code, None)
                metrics["summary_rows"] += 1
                metrics["extract_rows"] += 1
            metrics["bill_count"] = len(codes)
            stage = "DETAIL_EXTRACT"
            spool_bytes = 0
            LOG.info("谷仓仓租概要完成 batch=%s summary_rows=%s bill_count=%s",
                     batch, len(summaries), len(codes))
            for bill_index, code in enumerate(codes, 1):
                metrics["current_bill_index"] = bill_index
                rows_before = metrics["detail_rows"]
                for source, page, row_no, count in _pages(
                    lambda p: _fetch_with_budget(lambda: client.fetch_storage_detail_page(code, p), deadline),
                    DETAIL_PATH, metrics, "detail_page_count", detail=True,
                ):
                    if metrics["detail_rows"] >= MAX_DETAIL_ROWS:
                        raise ValueError("仓租明细总行数超过安全上限，拒绝提交")
                    row = _detail_row(source, code, page, row_no, count, start, end, batch)
                    spool_bytes += _write_detail(spool, row)
                    if spool_bytes > MAX_SPOOL_BYTES:
                        raise ValueError("仓租明细临时文件超过2GiB安全上限，拒绝提交")
                    metrics["detail_rows"] += 1
                    metrics["extract_rows"] += 1
                metrics["completed_bills"] += 1
                if rows_before == metrics["detail_rows"]:
                    metrics["empty_detail_bills"] += 1
                if bill_index == 1 or bill_index % 10 == 0 or bill_index == len(codes):
                    LOG.info("谷仓仓租明细进度 batch=%s bills=%s/%s detail_rows=%s pages=%s",
                             batch, bill_index, len(codes), metrics["detail_rows"], metrics["detail_page_count"])
            spool.flush()
            if monotonic() >= deadline:
                raise ValueError("仓租概要及明细拉取超过2.5小时预算，保留旧快照")
            stage = "LOAD"
            metrics.update(repo.replace_storage_snapshot(
                summaries, _spooled_rows(spool, metrics["detail_rows"]),
            ))
        LOG.info("谷仓仓租两表提交完成 batch=%s summary_rows=%s detail_rows=%s empty_bills=%s",
                 batch, metrics["summary_rows"], metrics["detail_rows"], metrics["empty_detail_bills"])
        return metrics
    except Exception as exc:
        message = str(exc) if stage in {"EXTRACT", "DETAIL_EXTRACT"} and isinstance(exc, ValueError) else (
            f"谷仓仓租同步失败；exception_type={type(exc).__name__}"
        )
        message = (f"{message}；stage={stage} batch={batch} "
                   f"bill_index={metrics['current_bill_index']}/{metrics['bill_count']} "
                   f"page={metrics['current_page']}")
        LOG.error("%s", message)
        raise GoodcangStorageSyncError(stage, message, metrics) from None
