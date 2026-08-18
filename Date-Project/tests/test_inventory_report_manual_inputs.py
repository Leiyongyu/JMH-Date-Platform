from decimal import Decimal

import pytest

from backend.services import inventory_report_etl_service as service


def _metric_row(department: str, qty: str, cost: str) -> dict:
    return {
        "department_code": department,
        "end_in_transit_qty": Decimal(qty),
        "end_in_transit_total_cost": Decimal(cost),
        "end_inventory_qty": Decimal("0"),
        "end_inventory_total_cost": Decimal("0"),
    }


def test_department_summary_uses_manual_local_transit_and_recalculates_total():
    rows = service._department_summaries(
        "2026-07",
        [],
        [],
        [_metric_row("EBAY-1", "999", "888")],
        {
            "EBAY-1": {
                "local_end_in_transit_qty": Decimal("12.5"),
                "local_end_in_transit_total_cost": Decimal("345.67"),
            },
            "AMZ-EU": {
                "local_end_in_transit_qty": Decimal("3"),
                "local_end_in_transit_total_cost": Decimal("20"),
            },
        },
    )

    ebay = next(row for row in rows if row["department_code"] == "EBAY-1")
    total = next(row for row in rows if row["is_total"] == 1)
    assert ebay["local_end_in_transit_qty"] == Decimal("12.5")
    assert ebay["local_end_in_transit_total_cost"] == Decimal("345.67")
    assert total["local_end_in_transit_qty"] == Decimal("15.5")
    assert total["local_end_in_transit_total_cost"] == Decimal("365.67")


def test_save_manual_inputs_rejects_unknown_department(monkeypatch):
    monkeypatch.setattr(service.repo, "upsert_manual_inputs", lambda *_args: None)
    with pytest.raises(ValueError, match="不支持的部门编码"):
        service.save_manual_inputs(
            "2026-07",
            [
                {
                    "department_code": "UNKNOWN",
                    "local_end_in_transit_qty": 1,
                    "local_end_in_transit_total_cost": 2,
                }
            ],
            "tester",
        )
