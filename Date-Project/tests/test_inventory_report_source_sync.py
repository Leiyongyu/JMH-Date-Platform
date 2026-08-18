from datetime import date
from datetime import datetime
from decimal import Decimal

import pytest

from backend.services import inventory_report_source_sync_service as service
from backend.services.inventory_report_source_sync_service import (
    InventoryReportSourceSyncError,
    _fetch_fba,
    _fetch_order_profit,
    _fetch_warehouse_report,
    _month_scope,
    _require_non_empty_extract,
    sync_monthly_inventory_sales_volume,
)
from backend.schemas.inventory_report_source_fields import OVERSEAS_SOURCE_FIELDS


def test_month_scope_defaults_to_previous_complete_natural_month():
    assert _month_scope(None, date(2026, 9, 1)) == (
        "2026-08",
        "2026-08-01",
        "2026-08-31",
    )


def test_month_scope_handles_year_boundary():
    assert _month_scope(None, date(2026, 1, 15)) == (
        "2025-12",
        "2025-12-01",
        "2025-12-31",
    )


def test_month_scope_uses_full_explicit_leap_month():
    assert _month_scope("2024-02") == (
        "2024-02",
        "2024-02-01",
        "2024-02-29",
    )


def test_month_scope_rejects_invalid_month():
    with pytest.raises(ValueError, match="YYYY-MM"):
        _month_scope("2026-13")


def test_empty_source_extract_fails_before_replacing_ods():
    metrics = {"stat_month": "2026-07"}
    with pytest.raises(
        InventoryReportSourceSyncError,
        match="未返回海外仓数据.*未写入ODS",
    ) as error:
        _require_non_empty_extract(
            "2026-07",
            {
                "fba": [{"id": 1}],
                "overseas": [],
                "local": [{"id": 2}],
                "order_profit": [{"id": 3}],
            },
            metrics,
        )
    assert error.value.stage == "VALIDATE_EXTRACT"
    assert error.value.metrics is metrics


class _FakeDomain:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, path, params):
        self.calls.append((path, params))
        return self.response


def test_fba_request_uses_year_month_date_format():
    domain = _FakeDomain(
        {"code": 0, "data": {"row_data": [{"sid": 1}], "total": 1}}
    )

    rows = _fetch_fba(
        domain,
        "2026-07",
        "2026-07-01",
        "2026-07-31",
        ["seller-1"],
        "batch-1",
        datetime(2026, 8, 17, 14, 0, 0),
    )

    assert len(rows) == 1
    assert domain.calls[0][1]["start_date"] == "2026-07"
    assert domain.calls[0][1]["end_date"] == "2026-07"
    assert domain.calls[0][1]["seller_id"] == ["seller-1"]
    assert rows[0]["query_start_date"] == "2026-07"
    assert rows[0]["query_end_date"] == "2026-07"


def test_overseas_request_keeps_full_natural_month_dates():
    domain = _FakeDomain({"code": 0, "data": [{"sys_wid": 18677}], "total": 1})

    rows = _fetch_warehouse_report(
        domain=domain,
        source="overseas",
        path="overseas-path",
        fields=OVERSEAS_SOURCE_FIELDS,
        page_size=100,
        month="2026-07",
        query_start="2026-07-01",
        query_end="2026-07-31",
        warehouse_wids=["18677"],
        batch_id="batch-1",
        pulled_at=datetime(2026, 8, 17, 14, 0, 0),
    )

    assert len(rows) == 1
    assert domain.calls[0][1]["start_date"] == "2026-07-01"
    assert domain.calls[0][1]["end_date"] == "2026-07-31"
    assert domain.calls[0][1]["sys_wid"] == "18677"
    assert rows[0]["query_start_date"] == "2026-07-01"
    assert rows[0]["query_end_date"] == "2026-07-31"


def test_order_profit_uses_full_month_cny_and_keeps_minimum_fields():
    domain = _FakeDomain(
        {
            "code": 0,
            "total": 1,
            "request_id": "request-1",
            "response_time": "2026-08-18 12:00:00",
            "data": [
                {
                    "currency_code": "CNY",
                    "amount": "1234.56",
                    "volume": "27",
                    "gross_profit": "999.99",
                    "price_list": [
                        {
                            "sid": "1001",
                            "seller_sku": "MSKU-1",
                            "local_sku": "SKU-1",
                            "asin": "B000000001",
                            "item_name": "测试商品",
                        }
                    ],
                }
            ],
        }
    )

    rows, skipped = _fetch_order_profit(
        domain,
        "2026-07",
        "2026-07-01",
        "2026-07-31",
        ["1001"],
        datetime(2026, 8, 18, 12, 0, 0),
    )

    assert skipped == 0
    assert domain.calls[0][0] == "basicOpen/finance/mreport/OrderProfit"
    assert domain.calls[0][1]["startDate"] == "2026-07-01"
    assert domain.calls[0][1]["endDate"] == "2026-07-31"
    assert domain.calls[0][1]["currencyCode"] == "CNY"
    assert domain.calls[0][1]["length"] == 5000
    assert rows[0]["sid"] == "1001"
    assert rows[0]["msku"] == "MSKU-1"
    assert rows[0]["local_sku"] == "SKU-1"
    assert rows[0]["amount"] == Decimal("1234.56")
    assert rows[0]["volume"] == Decimal("27")
    assert "gross_profit" not in rows[0]
    assert set(rows[0]) == {
        "stat_month", "sid", "msku", "local_sku", "asin", "item_name",
        "currency_code", "amount", "volume", "pulled_at",
    }


def test_month_end_sales_volume_rebuilds_only_amz_sales_dwd(monkeypatch):
    source_rows = [
        {
            "stat_month": "2026-08",
            "sid": "1001",
            "msku": "MSKU-1",
            "local_sku": "SKU-1",
            "asin": "B000000001",
            "item_name": "测试商品",
            "currency_code": "CNY",
            "amount": Decimal("100"),
            "volume": Decimal("8"),
            "pulled_at": datetime(2026, 8, 31, 23, 0, 0),
        }
    ]
    monkeypatch.setattr(service.repo, "amazon_seller_ids", lambda: ["1001"])
    monkeypatch.setattr(
        service,
        "_fetch_order_profit",
        lambda *_args, **_kwargs: (source_rows, 0),
    )
    monkeypatch.setattr(
        service.repo,
        "replace_order_profit_month",
        lambda month, rows: {"deleted_rows": 2, "inserted_rows": len(rows)},
    )
    monkeypatch.setattr(
        service,
        "rebuild_monthly_inventory_amz_sales",
        lambda month: {"dwd_rows": 1, "deleted_rows": 2},
    )
    monkeypatch.setattr(
        service,
        "rebuild_monthly_inventory_report",
        lambda _month: pytest.fail("月末销量任务不应重建完整库存报表"),
    )

    result = sync_monthly_inventory_sales_volume("2026-08")

    assert result["stat_month"] == "2026-08"
    assert result["order_profit_rows"] == 1
    assert result["ods_rows"] == 1
    assert result["dwd_rows"] == 1
    assert result["inserted_rows"] == 2
    assert result["deleted_rows"] == 4
