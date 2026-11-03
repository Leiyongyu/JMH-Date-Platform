"""Monthly pull of LingXing profit sources for the AMZ profit report (USD).

利润统计 (seller + msku) is the settlement basis and only accepts windows of
at most 7 days, so a month is fetched in weekly windows and summed. 订单利润
(OrderProfit) is the order basis and is fetched for the whole month at once.
All three sources are validated first and then replaced together.
"""
from __future__ import annotations

import time
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterator
from uuid import uuid4

from backend.integrations.lingxing.client import LingXingClient
from backend.repositories import amz_profit_report_repository as repo
from backend.repositories import inventory_report_source_repository as source_repo
from backend.schemas.amz_profit_report_fields import ORDER_METRICS, SETTLEMENT_METRICS
from backend.services.weekly_inventory_api import (
    MAX_ATTEMPTS,
    RETRY_BUSINESS,
    _retry_delay,
    _transport_failure,
)


TASK_CODE = "amz_profit_report_sync"
TASK_NAME = "AMZ利润报表数据拉取"
SELLER_PATH = "bd/profit/statistics/open/seller/list"
MSKU_PATH = "bd/profit/statistics/open/msku/list"
ORDER_PATH = "basicOpen/finance/mreport/OrderProfit"
CURRENCY = "USD"
MAX_WINDOW_DAYS = 7
SID_GROUP_SIZE = 20
SETTLEMENT_PAGE_SIZE = 5000
ORDER_PAGE_SIZE = 5000
MAX_PAGES = 1000
# Token buckets: 利润统计 10, 订单利润 1.
SETTLEMENT_INTERVAL_SECONDS = 0.2
ORDER_INTERVAL_SECONDS = 1.1
# Store totals vs MSKU sums differ only by LingXing rounding.
RECONCILE_TOLERANCE = Decimal("1")
# Read-only pulls may retry LingXing's generic server error as well as rate limits.
RETRY_SERVER_CODES = {"500"}
ZERO = Decimal("0")


class AmzProfitReportSyncError(RuntimeError):
    def __init__(self, stage: str, message: str, metrics: dict[str, Any]):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics


def sync_amz_profit_report(
    stat_month: str | None = None,
    *,
    client: LingXingClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    month = _month(stat_month)
    batch_id = str(uuid4())
    synced_at = datetime.now()
    metrics: dict[str, Any] = {
        "stat_month": month,
        "sync_batch_id": batch_id,
        "currency_code": CURRENCY,
        "extract_rows": 0,
        "ods_rows": 0,
    }
    stage = "LOAD_SCOPE"
    try:
        sids = source_repo.amazon_seller_ids()
        if not sids:
            raise ValueError("shop_list 中没有 platform_code=10001 的有效 sid")
        api = _Api(client or LingXingClient(), sleep)
        windows = month_windows(month)

        common = {"stat_month": month, "currency_code": CURRENCY,
                  "sync_batch_id": batch_id, "synced_at": synced_at}

        # OrderProfit needs only a few calls; run it first so an upstream
        # failure surfaces before the long settlement pull.
        stage = "EXTRACT_ORDER"
        orders = OrderMonthAccumulator(common)
        for group in _groups(sids):
            for page in api.order_pages(_body(group, windows[0][0], windows[-1][1])):
                for record in page:
                    orders.add(record)
        metrics["order_records"] = orders.records
        order_rows = orders.rows()
        metrics["skipped_rows"] = orders.skipped

        stage = "EXTRACT_SELLER"
        seller_records = []
        for start, end in windows:
            for group in _groups(sids):
                for page in api.settlement_pages(SELLER_PATH, _body(group, start, end)):
                    seller_records.extend((start, record) for record in page)
        metrics["seller_records"] = len(seller_records)
        seller_rows = seller_daily_rows(month, seller_records, common)

        # A month of MSKU-day records is ~10^5 wide dicts; fold each page into
        # the monthly rows right away instead of keeping the raw records.
        stage = "EXTRACT_MSKU"
        msku = MskuMonthAccumulator(common)
        for start, end in windows:
            for group in _groups(sids):
                for page in api.settlement_pages(MSKU_PATH, _body(group, start, end)):
                    for record in page:
                        msku.add(start, record)
        metrics["msku_records"] = msku.records
        msku_rows = msku.rows()

        metrics["extract_rows"] = len(seller_records) + msku.records + orders.records

        stage = "TRANSFORM"
        empty = [name for name, rows in (
            ("利润统计-店铺", seller_rows), ("利润统计-MSKU", msku_rows),
            ("订单利润", order_rows),
        ) if not rows]
        if empty:
            raise ValueError(
                f"{month} 领星未返回{'、'.join(empty)}数据，为防止覆盖已有月份，本次未写入"
            )
        metrics["reconcile_diff_stores"] = reconcile_stores(seller_rows, msku_rows)

        stage = "LOAD"
        stored = repo.replace_month(month, seller_rows, msku_rows, order_rows)
    except AmzProfitReportSyncError:
        raise
    except Exception as exc:
        raise AmzProfitReportSyncError(
            stage, f"AMZ利润报表数据拉取失败（{stage}），原有月份数据保持不变: {exc}",
            metrics,
        ) from exc
    inserted = stored["seller_rows"] + stored["msku_rows"] + stored["order_rows"]
    return {
        **metrics,
        **stored,
        "ods_rows": inserted,
        "inserted_rows": inserted,
        "updated_rows": 0,
        "status": "completed",
    }


def month_windows(month: str) -> list[tuple[date, date]]:
    """Split a natural month into consecutive windows of at most 7 days."""
    year, number = (int(part) for part in month.split("-"))
    current = date(year, number, 1)
    last = date(year, number, monthrange(year, number)[1])
    windows = []
    while current <= last:
        end = min(current + timedelta(days=MAX_WINDOW_DAYS - 1), last)
        windows.append((current, end))
        current = end + timedelta(days=1)
    return windows


def seller_daily_rows(
    month: str, records: list[tuple[date, dict]], common: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: dict[tuple[date, str], dict[str, Any]] = {}
    for window_start, record in records:
        sid = _text(record.get("sid"))
        if not sid:
            continue
        posted = _date(record.get("postedDateLocale")) or window_start
        if posted.strftime("%Y-%m") != month:
            raise ValueError(f"利润统计-店铺返回了{month}以外的日期{posted}")
        key = (posted, sid)
        if key in rows:
            raise ValueError(f"利润统计-店铺重复返回 sid={sid} 日期={posted}")
        rows[key] = {
            **common,
            "posted_date": posted,
            "sid": sid,
            "store_name": _text(record.get("storeName")) or None,
            "country_code": _text(record.get("countryCode")) or None,
            **_metrics(record, SETTLEMENT_METRICS),
            "raw_json": record,
        }
    return list(rows.values())


class MskuMonthAccumulator:
    """Sum daily MSKU records into one row per (sid, msku)."""

    def __init__(self, common: dict[str, Any]):
        self.common = common
        self.records = 0
        self._seen: set[tuple[Any, ...]] = set()
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}
        self._fees: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

    def add(self, window_start: date, record: dict) -> None:
        self.records += 1
        sid = _text(record.get("sid"))
        if not sid:
            return
        msku = _text(record.get("msku")) or "-"
        day = _date(record.get("dataDate")) or _date(record.get("postedDateLocale")) or window_start
        daily_key = (day, sid, msku, _text(record.get("asin")))
        if daily_key in self._seen:
            raise ValueError(f"利润统计-MSKU重复返回 sid={sid} msku={msku} 日期={day}")
        self._seen.add(daily_key)
        key = (sid, msku)
        row = self._rows.get(key)
        if row is None:
            row = self._rows[key] = {
                **self.common, "sid": sid, "msku": msku, "source_rows": 0,
                **{column: 0 if kind == "qty" else ZERO
                   for column, _field, kind in SETTLEMENT_METRICS},
            }
        for field, column in (
            ("asin", "asin"), ("storeName", "store_name"),
            ("countryCode", "country_code"), ("localSku", "local_sku"),
            ("localName", "local_name"), ("principalRealname", "principal_realname"),
        ):
            row[column] = row.get(column) or _text(record.get(field)) or None
        for column, value in _metrics(record, SETTLEMENT_METRICS).items():
            row[column] += value
        row["source_rows"] += 1
        for fee in record.get("estimateFeeStr") or []:
            if isinstance(fee, dict) and _text(fee.get("name")):
                self._fees[key][_text(fee["name"])] += _decimal(fee.get("amount"))

    def rows(self) -> list[dict[str, Any]]:
        for key, row in self._rows.items():
            fees = self._fees.get(key)
            row["estimate_fees_json"] = (
                {name: str(amount) for name, amount in fees.items()} if fees else None
            )
        return list(self._rows.values())


class OrderMonthAccumulator:
    """One row per (sid, msku); the last duplicate wins like the AMZ ranking sync."""

    def __init__(self, common: dict[str, Any]):
        self.common = common
        self.records = 0
        self.invalid = 0
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    @property
    def skipped(self) -> int:
        """Invalid records plus duplicates replaced by a later record."""
        return self.records - len(self._rows)

    def add(self, record: dict) -> None:
        self.records += 1
        price = _first_dict(record.get("price_list"))
        local = _first_dict(record.get("local_infos"))
        country = _first_dict(record.get("seller_store_countries"))
        sid = _text(price.get("sid")) or _text(_first(record.get("sids")))
        msku = _text(price.get("seller_sku"))
        if not sid or not msku:
            self.invalid += 1
            return
        self._rows[(sid, msku)] = {
            **self.common,
            "sid": sid,
            "msku": msku,
            "asin": _text(price.get("asin")) or None,
            "local_sku": _text(price.get("local_sku")) or _text(local.get("local_sku")) or None,
            "local_name": _text(price.get("local_name")) or _text(local.get("local_name")) or None,
            # seller_store_countries: {"country": "美国", "name": "US2-韵盛余-US"}.
            "country": _text(country.get("country")) or None,
            "principal_names": _text(record.get("principal_names")) or None,
            **_metrics(record, ORDER_METRICS),
        }

    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows.values())


def msku_month_rows(
    month: str, records: list[tuple[date, dict]], common: dict[str, Any],
) -> list[dict[str, Any]]:
    accumulator = MskuMonthAccumulator(common)
    for window_start, record in records:
        accumulator.add(window_start, record)
    return accumulator.rows()


def order_month_rows(
    records: list[dict], common: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    accumulator = OrderMonthAccumulator(common)
    for record in records:
        accumulator.add(record)
    return accumulator.rows(), accumulator.skipped


def reconcile_stores(
    seller_rows: list[dict[str, Any]], msku_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stores whose MSKU sums do not match the store endpoint (warning only)."""
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for source, rows in (("seller", seller_rows), ("msku", msku_rows)):
        for row in rows:
            for field in ("total_sales_amount", "gross_profit"):
                totals[row["sid"]][f"{source}_{field}"] += Decimal(row[field])
    diffs = []
    for sid, values in sorted(totals.items()):
        for field in ("total_sales_amount", "gross_profit"):
            gap = values[f"seller_{field}"] - values[f"msku_{field}"]
            if abs(gap) > RECONCILE_TOLERANCE:
                diffs.append({"sid": sid, "field": field, "difference": str(gap)})
    return diffs


class _Api:
    def __init__(self, client: LingXingClient, sleep: Callable[[float], None]):
        self.client = client
        self.sleep = sleep

    def settlement_pages(self, path: str, body: dict[str, Any]) -> Iterator[list[dict]]:
        return self._pages(path, body, SETTLEMENT_PAGE_SIZE, SETTLEMENT_INTERVAL_SECONDS)

    def order_pages(self, body: dict[str, Any]) -> Iterator[list[dict]]:
        return self._pages(ORDER_PATH, body, ORDER_PAGE_SIZE, ORDER_INTERVAL_SECONDS)

    def _pages(
        self, path: str, body: dict[str, Any], page_size: int, interval: float,
    ) -> Iterator[list[dict]]:
        received = 0
        for page in range(MAX_PAGES):
            response = self._request(path, {**body, "offset": page * page_size,
                                             "length": page_size}, interval)
            batch, total = _records_and_total(response)
            received += len(batch)
            yield batch
            if received >= total:
                return
            if not batch:
                raise RuntimeError(f"{path} 分页不完整：应返回{total}条，实际{received}条")
        raise RuntimeError(f"{path} 超过最大页数{MAX_PAGES}")

    def _request(self, path: str, body: dict[str, Any], interval: float) -> dict:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.sleep(interval)
            retry_after = None
            try:
                response = self.client.post_signed_query_auth(path, dict(body))
            except Exception as exc:
                retryable, retry_after, _ = _transport_failure(exc, self.client)
                detail = f"传输错误 {type(exc).__name__}"
            else:
                code = str(response.get("code")) if isinstance(response, dict) else "invalid"
                if code in {"0", "200"}:
                    return response
                retryable = code in RETRY_BUSINESS or code in RETRY_SERVER_CODES
                detail = f"业务错误码 {code}" if code.isdecimal() else "接口响应格式错误"
            if retryable and attempt < MAX_ATTEMPTS:
                delay = _retry_delay(attempt, retry_after)
                if delay is not None:
                    self.sleep(delay)
                    continue
            raise RuntimeError(f"{path} 请求失败：{detail}，offset={body['offset']}")
        raise RuntimeError(f"{path} 请求失败")


def _records_and_total(response: dict) -> tuple[list[dict], int]:
    data = response.get("data")
    if isinstance(data, list):  # OrderProfit
        return data, int(response.get("total") or 0)
    if isinstance(data, dict):  # 利润统计
        records = data.get("records") or []
        if not isinstance(records, list):
            raise RuntimeError("利润统计响应 records 不是数组")
        return records, int(data.get("total") or 0)
    raise RuntimeError("领星响应缺少 data")


def _metrics(record: dict, metrics) -> dict[str, Any]:
    result = {}
    for column, field, kind in metrics:
        value = _decimal(record.get(field))
        result[column] = int(value) if kind == "qty" else value
    return result


def _body(sids: list[str], start: date, end: date) -> dict[str, Any]:
    return {"sids": sids, "startDate": start.isoformat(),
            "endDate": end.isoformat(), "currencyCode": CURRENCY}


def _groups(values: list[str]) -> list[list[str]]:
    return [values[start:start + SID_GROUP_SIZE] for start in range(0, len(values), SID_GROUP_SIZE)]


def _decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        return ZERO
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return ZERO
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"领星返回的数值无法解析：{value}") from exc


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _date(value: Any) -> date | None:
    text = _text(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date() if text else None
    except ValueError:
        return None


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None


def _first_dict(value: Any) -> dict:
    item = _first(value) if isinstance(value, list) else value
    return item if isinstance(item, dict) else {}


def _month(value: str | None) -> str:
    if not value:
        today = date.today()
        return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("stat_month 必须使用 YYYY-MM 格式") from exc
