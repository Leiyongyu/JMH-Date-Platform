from datetime import date
from decimal import Decimal

from backend.integrations.lingxing.domains.currency import LingXingCurrencyDomain
from backend.services import currency_sync_service as service


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_signed_query_auth(self, path, body):
        self.calls.append((path, body))
        return self.response


class _Domain:
    def __init__(self):
        self.months = []

    def fetch_monthly_rates(self, month):
        self.months.append(month)
        return [{
            "date": month,
            "code": "USD",
            "my_rate": "7.1234",
            "rate_org": "7.1000",
        }]


def test_currency_domain_uses_non_paginated_month_endpoint():
    client = _Client({
        "code": 0,
        "data": [{"date": "2026-08", "code": "USD", "my_rate": "7.1"}],
    })
    domain = LingXingCurrencyDomain(client=client)

    rows = domain.fetch_monthly_rates("2026-08")

    assert rows[0]["code"] == "USD"
    assert client.calls == [(
        "erp/sc/routing/finance/currency/currencyMonth",
        {"date": "2026-08"},
    )]


def test_currency_sync_keeps_only_usd_my_rate_and_upserts(monkeypatch):
    stored = []
    monkeypatch.setattr(
        service.repo,
        "upsert_monthly_rates",
        lambda rows: stored.extend(rows) or len(rows),
    )

    result = service.sync_currency_month("2026-08", _Domain())

    assert result["my_rate"] == Decimal("7.1234")
    assert result["rate_org"] == Decimal("7.1000")
    assert stored[0]["currency_code"] == "USD"
    assert stored[0]["rate_month"] == "2026-08"


def test_inventory_currency_chain_syncs_previous_then_current(monkeypatch):
    domain = _Domain()
    intervals = []
    monkeypatch.setattr(
        service.repo,
        "upsert_monthly_rates",
        lambda rows: len(rows),
    )

    result = service.sync_inventory_currency_rates(
        source_stat_month="2026-08",
        today=date(2026, 9, 2),
        domain=domain,
        sleep=intervals.append,
    )

    assert result["rate_months"] == ["2026-08", "2026-09"]
    assert domain.months == ["2026-08", "2026-09"]
    assert intervals == [service.RATE_LIMIT_INTERVAL_SECONDS]


def test_historical_source_sync_adds_its_business_month(monkeypatch):
    domain = _Domain()
    monkeypatch.setattr(
        service.repo,
        "upsert_monthly_rates",
        lambda rows: len(rows),
    )

    result = service.sync_inventory_currency_rates(
        source_stat_month="2026-05",
        today=date(2026, 9, 2),
        domain=domain,
        sleep=lambda _seconds: None,
    )

    assert result["rate_months"] == ["2026-06", "2026-08", "2026-09"]
