from decimal import Decimal

from backend.services import inventory_report_etl_service as service


def _metric_row(department: str, qty: str, cost: str) -> dict:
    return {
        "department_code": department,
        "end_in_transit_qty": Decimal(qty),
        "end_in_transit_total_cost": Decimal(cost),
        "end_inventory_qty": Decimal("0"),
        "end_inventory_total_cost": Decimal("0"),
    }


def test_department_summary_uses_purchase_order_transit_and_ignores_local_api_transit():
    rows = service._department_summaries(
        "2026-07",
        [],
        [],
        [_metric_row("EBAY-1", "999", "888")],
        [
            {
                "department_code": "EBAY-1",
                "pending_arrival_qty": Decimal("12.5"),
                "sku_pending_total_cost": Decimal("345.67"),
            },
            {
                "department_code": "AMZ-EU",
                "pending_arrival_qty": Decimal("3"),
                "sku_pending_total_cost": Decimal("20"),
            },
        ],
    )

    ebay = next(row for row in rows if row["department_code"] == "EBAY-1")
    total = next(row for row in rows if row["is_total"] == 1)
    assert ebay["local_end_in_transit_qty"] == Decimal("12.5")
    assert ebay["local_end_in_transit_total_cost"] == Decimal("345.67")
    assert total["local_end_in_transit_qty"] == Decimal("15.5")
    assert total["local_end_in_transit_total_cost"] == Decimal("365.67")


def test_department_summary_preserves_filled_next_month_opening_inventory():
    rows = service._department_summaries(
        "2026-07",
        [],
        [],
        [],
        opening_inventory={
            "EBAY-1": Decimal("100"),
            "AMZ-EU": Decimal("200"),
            "AMZ-US1": Decimal("300"),
            "AMZ-US2": Decimal("400"),
            "AMZ-US2-MJ": Decimal("500"),
            "AMZ-US1-ZXY": Decimal("600"),
        },
    )

    ebay = next(row for row in rows if row["department_code"] == "EBAY-1")
    total = next(row for row in rows if row["is_total"] == 1)
    assert ebay["next_month_opening_inventory_qty"] == Decimal("100")
    assert total["next_month_opening_inventory_qty"] == Decimal("2100")


def test_fill_next_month_opening_inventory_returns_business_month(monkeypatch):
    monkeypatch.setattr(
        service.repo,
        "fill_next_month_opening_inventory",
        lambda month: {"source_rows": 6, "updated_rows": 7},
    )

    result = service.fill_next_month_opening_inventory("2026-07")

    assert result["stat_month"] == "2026-07"
    assert result["opening_month"] == "2026-08"
    assert result["extract_rows"] == 6
    assert result["updated_rows"] == 7
