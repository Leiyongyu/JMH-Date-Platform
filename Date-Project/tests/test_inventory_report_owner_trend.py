from decimal import Decimal

import pytest

from backend.services import inventory_report_owner_trend_service as service


def _snapshot(stat_month, report_month, items):
    return {"stat_month": stat_month, "payload": {"report_month": report_month, "items": items}}


def test_owner_trend_aligns_by_report_month_and_merges_departments(monkeypatch):
    calls = {}

    def performance(start, end):
        calls["performance"] = (start, end)
        return [
            {"stat_month": "2026-08", "principal_name": "张三",
             "net_sales_amount": Decimal("1000.005"), "gross_profit": Decimal("200")},
            {"stat_month": "2026-07", "principal_name": "未分配",
             "net_sales_amount": Decimal("50"), "gross_profit": Decimal("-5")},
            {"stat_month": "2026-07", "principal_name": "李四",
             "net_sales_amount": Decimal("300"), "gross_profit": Decimal("30")},
        ]

    def snapshots(start, end):
        calls["snapshots"] = (start, end)
        return [_snapshot("2026-07", "2026-08", [
            {"is_dimension_total": 1, "dimension_value": "合计",
             "turnover_days_by_value": "99", "actual_achievement_amount": "1"},
            {"dimension_value": "张三", "department_code": "AMZ-EU",
             "turnover_days_by_value": "10", "actual_achievement_amount": "100",
             "inventory_age_180_plus_cost": "40"},
            {"dimension_value": "张三", "department_code": "AMZ-US1",
             "turnover_days_by_value": "20", "actual_achievement_amount": "300",
             "inventory_age_180_plus_cost": "60"},
            {"dimension_value": "李四", "department_code": "EBAY-1",
             "turnover_days_by_value": None, "actual_achievement_amount": "0",
             "inventory_age_180_plus_cost": None},
        ])]

    monkeypatch.setattr(service.repo, "owner_performance_rows", performance)
    monkeypatch.setattr(service.repo, "owner_view_snapshots", snapshots)

    data = service.owner_trend("2026-07", "2026-08")

    assert calls == {"performance": ("2026-07", "2026-08"), "snapshots": ("2026-06", "2026-07")}
    assert data["months"] == ["2026-07", "2026-08"]
    assert data["inventory_months"] == ["2026-08"]
    assert data["owners"] == ["张三", "李四", "未分配"]
    assert "合计" not in data["series"]
    zhang = data["series"]["张三"]
    assert zhang["sales_amount"] == [None, 1000.0]
    assert zhang["gross_profit"] == [None, 200.0]
    # (10*100 + 20*300) / 400
    assert zhang["turnover_days"] == [None, 17.5]
    assert zhang["aged_181_plus_cost"] == [None, 100.0]
    li = data["series"]["李四"]
    assert li["turnover_days"] == [None, None]
    assert li["aged_181_plus_cost"] == [None, None]


@pytest.mark.parametrize("start,end,message", [
    ("2026-09", "2026-08", "开始月份不能晚于结束月份"),
    ("2024-01", "2026-01", "最多"),
    ("2026/01", "2026-02", "YYYY-MM"),
])
def test_owner_trend_rejects_bad_ranges(monkeypatch, start, end, message):
    monkeypatch.setattr(service.repo, "owner_performance_rows", lambda *_: [])
    monkeypatch.setattr(service.repo, "owner_view_snapshots", lambda *_: [])
    with pytest.raises(ValueError, match=message):
        service.owner_trend(start, end)
