from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from backend.integrations.lingxing.domains.order_profit import LingXingOrderProfitDomain
from backend.repositories import performance_repository as repo
from backend.services.performance_service import (
    begin_performance_refresh,
    calculate_performance,
    complete_performance_refresh,
    fail_performance_refresh,
)


class AmazonProfitEtlError(RuntimeError):
    def __init__(
        self, stage: str, message: str, metrics: dict | None = None
    ):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics or {}


def previous_natural_month(today: date | None = None) -> str:
    current = today or date.today()
    first_day = current.replace(day=1)
    last_prev = first_day - timedelta(days=1)
    return f"{last_prev.year:04d}-{last_prev.month:02d}"


def month_range(stat_month: str) -> tuple[date, date]:
    year, month = [int(part) for part in stat_month.split("-")]
    start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def sync_amazon_monthly_profit(
    stat_month: str | None = None,
    request_id: str = "",
    trigger_source: str = "internal_scheduler",
) -> dict:
    stage = "VALIDATE"
    refresh_context = None
    metrics = {
        "sync_batch_id": None,
        "extract_rows": 0,
        "ods_rows": 0,
        "inserted_rows": 0,
        "updated_rows": 0,
        "deleted_rows": 0,
        "skipped_rows": 0,
        "amz_ranking_rows": 0,
        "combined_ranking_rows": 0,
    }
    try:
        month = stat_month or previous_natural_month()
        start_date, end_date = month_range(month)
        sync_batch_id = str(uuid4())
        metrics["sync_batch_id"] = sync_batch_id
        sids = repo.amazon_shop_sids()
        if not sids:
            raise ValueError("shop_list 中没有可用 Amazon 店铺 SID")

        stage = "EXTRACT"
        domain = LingXingOrderProfitDomain()
        remote_rows: list[dict] = []
        for group in _chunks(sids, 20):
            remote_rows.extend(
                domain.fetch_monthly_profit(group, start_date, end_date)
            )
        if not remote_rows:
            raise ValueError("领星月利润接口返回0条，已拒绝清空当月数据")
        metrics["extract_rows"] = len(remote_rows)

        stage = "TRANSFORM"
        rows_by_key: dict[tuple[str, str], dict] = {}
        raw_rows = []
        invalid_rows = 0
        sync_time = datetime.now()
        for item in remote_rows:
            row, raw_row = _transform_row(
                item, month, sync_batch_id, sync_time
            )
            raw_rows.append(raw_row)
            if row is None:
                invalid_rows += 1
                continue
            rows_by_key[(row["sid"], row["seller_sku"])] = row
        rows = list(rows_by_key.values())
        duplicate_rows = len(remote_rows) - invalid_rows - len(rows)
        metrics["skipped_rows"] = invalid_rows + duplicate_rows

        stage = "ODS"
        with repo.performance_connection() as connection:
            repo.append_amz_profit_raw(connection, raw_rows)
            connection.commit()
        metrics["ods_rows"] = len(raw_rows)

        stage = "DWD_DWS"
        refresh_context = begin_performance_refresh(
            month, "amazon", trigger_source, request_id
        )
        with repo.performance_connection() as connection:
            try:
                changes = repo.replace_amz_profit_month(
                    connection, month, rows
                )
                metrics.update(changes)
                refresh = calculate_performance(
                    connection, month, platform="amazon"
                )
                metrics["amz_ranking_rows"] = refresh[
                    "amz_ranking_rows"
                ]
                metrics["combined_ranking_rows"] = refresh[
                    "combined_ranking_rows"
                ]
                complete_performance_refresh(
                    connection, refresh_context, refresh
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        refresh["status"] = "completed"
        return {
            "sync_batch_id": sync_batch_id,
            "stat_month": month,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "sid_count": len(sids),
            "extract_rows": len(remote_rows),
            "remote_rows": len(remote_rows),
            "ods_rows": len(raw_rows),
            "dwd_rows": changes["dwd_rows"],
            "inserted_rows": changes["inserted_rows"],
            "updated_rows": changes["updated_rows"],
            "deleted_rows": changes["deleted_rows"],
            "skipped_rows": invalid_rows + duplicate_rows,
            "invalid_rows": invalid_rows,
            "duplicate_rows": duplicate_rows,
            "etl_stage": "COMPLETED",
            "refresh": refresh,
        }
    except Exception as exc:
        if stage == "DWD_DWS":
            for key in (
                "inserted_rows",
                "updated_rows",
                "deleted_rows",
                "amz_ranking_rows",
                "combined_ranking_rows",
            ):
                metrics[key] = 0
        if refresh_context is not None:
            try:
                fail_performance_refresh(refresh_context, exc)
            except Exception:
                pass
        if isinstance(exc, AmazonProfitEtlError):
            raise
        raise AmazonProfitEtlError(stage, str(exc), metrics) from exc


def _transform_row(
    item: dict,
    month: str,
    sync_batch_id: str,
    sync_time: datetime,
) -> tuple[dict | None, dict]:
    price = _first_dict(
        item.get("price_list")
        or item.get("priceList")
        or item.get("prices")
        or item.get("price")
    )
    local_info = _first_dict(
        item.get("local_infos") or item.get("localInfos") or item.get("local_info")
    )
    asin_info = _first_dict(
        item.get("asins") or item.get("asin_list") or item.get("asinList")
    )
    country_info = _first_dict(
        item.get("seller_store_countries")
        or item.get("sellerStoreCountries")
        or item.get("countries")
    )
    sid = (
        _string_value(price, "sid")
        or _first_value(item.get("sids"))
        or _string_value(item, "sid", "sellerId", "seller_id")
    )
    seller_sku = _string_value(
        price, "seller_sku", "sellerSku", "sellerSKU", "msku", "sku"
    ) or _string_value(item, "seller_sku", "sellerSku", "sellerSKU", "msku", "sku")
    amount = _decimal_value(item, "amount")
    refund_amount = _decimal_value(item, "refund_amount", "refundAmount")
    structured = {
        "local_sku": _string_value(price, "local_sku", "localSku")
        or _string_value(local_info, "local_sku", "localSku"),
        "asin": _string_value(price, "asin") or _string_value(asin_info, "asin"),
        "country": _string_value(country_info, "country")
        or _string_value(item, "country"),
        "currency_code": _string_value(item, "currency_code", "currencyCode") or "CNY",
        "gross_profit": _decimal_value(item, "gross_profit", "grossProfit"),
        "amount": amount,
        "refund_amount": refund_amount,
        "net_sales_amount": amount - refund_amount,
        "principal_names": _string_value(item, "principal_names", "principalNames"),
    }
    raw_row = {
        "stat_month": month,
        "sid": sid,
        "seller_sku": seller_sku,
        **structured,
        "sync_batch_id": sync_batch_id,
        "sync_time": sync_time,
    }
    if not sid or not seller_sku:
        return None, raw_row
    return (
        {
            "stat_month": month,
            "sid": sid,
            "seller_sku": seller_sku,
            **structured,
            "sync_batch_id": sync_batch_id,
            "sync_time": sync_time,
        },
        raw_row,
    )


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _string_value(item: dict, *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _first_dict(value: Any) -> dict:
    value = _json_value(value)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def _first_value(value: Any) -> str | None:
    value = _json_value(value)
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return _string_value(first, "sid", "id", "value")
        if first is not None:
            return str(first).strip()
    return None


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("[", "{")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def _decimal_value(item: dict, *keys: str) -> Decimal:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() != "":
            return Decimal(str(value))
    return Decimal("0")
