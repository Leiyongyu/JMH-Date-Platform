from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable
from uuid import uuid4

from backend.integrations.lingxing.domains.currency import LingXingCurrencyDomain
from backend.repositories import currency_repository as repo


RATE_LIMIT_INTERVAL_SECONDS = 1.1


def sync_currency_month(
    rate_month: str,
    domain: LingXingCurrencyDomain | None = None,
) -> dict:
    month = _validate_month(rate_month)
    currency_domain = domain or LingXingCurrencyDomain()
    rows = currency_domain.fetch_monthly_rates(month)
    usd = next(
        (
            row for row in rows
            if str(row.get("code") or "").strip().upper() == "USD"
        ),
        None,
    )
    if usd is None:
        raise RuntimeError(f"领星 {month} 汇率数据中没有USD")
    my_rate = _positive_decimal(usd.get("my_rate"), "my_rate")
    rate_org = _optional_decimal(usd.get("rate_org"), "rate_org")
    response_month = str(usd.get("date") or month).strip()
    if response_month != month:
        raise RuntimeError(
            f"领星汇率月份不一致：请求{month}，返回{response_month}"
        )
    sync_batch_id = str(uuid4())
    synced_at = datetime.now()
    stored_rows = repo.upsert_monthly_rates([
        {
            "rate_month": month,
            "currency_code": "USD",
            "my_rate": my_rate,
            "rate_org": rate_org,
            "sync_batch_id": sync_batch_id,
            "synced_at": synced_at,
        }
    ])
    return {
        "rate_month": month,
        "currency_code": "USD",
        "my_rate": my_rate,
        "rate_org": rate_org,
        "sync_batch_id": sync_batch_id,
        "extract_rows": len(rows),
        "stored_rows": stored_rows,
        "synced_at": synced_at,
    }


def sync_inventory_currency_rates(
    source_stat_month: str | None = None,
    today: date | None = None,
    domain: LingXingCurrencyDomain | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """同步当月、上月及历史补跑所需业务月的USD汇率。"""
    current_day = today or date.today()
    current_month = current_day.strftime("%Y-%m")
    previous_month = (current_day.replace(day=1) - timedelta(days=1)).strftime(
        "%Y-%m"
    )
    months = [previous_month, current_month]
    if source_stat_month:
        business_month = _next_month(_validate_month(source_stat_month))
        if business_month not in months:
            months.insert(0, business_month)

    currency_domain = domain or LingXingCurrencyDomain()
    results = []
    for index, month in enumerate(months):
        if index:
            sleep(RATE_LIMIT_INTERVAL_SECONDS)
        results.append(sync_currency_month(month, currency_domain))
    return {
        "rate_months": months,
        "currency_code": "USD",
        "stored_rows": sum(item["stored_rows"] for item in results),
        "rates": results,
    }


def _validate_month(value: str) -> str:
    month = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("汇率月份必须是YYYY-MM")
    return month


def _next_month(stat_month: str) -> str:
    year, month = map(int, stat_month.split("-"))
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _positive_decimal(value, field: str) -> Decimal:
    parsed = _optional_decimal(value, field)
    if parsed is None or parsed <= 0:
        raise RuntimeError(f"领星USD汇率{field}无效：{value}")
    return parsed


def _optional_decimal(value, field: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"领星USD汇率{field}不是有效数字：{value}") from exc
