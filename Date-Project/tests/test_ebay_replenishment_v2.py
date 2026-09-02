from datetime import date
from decimal import Decimal

from backend.services import ebay_replenishment_v2_service as service


def test_complete_months_crosses_year_boundary():
    months = service._complete_months(date(2026, 1, 15))

    assert [month["month"] for month in months] == [
        "2025-12",
        "2025-11",
        "2025-10",
    ]
    assert months[0]["start_date"] == date(2025, 12, 1)
    assert months[0]["end_date"] == date(2026, 1, 1)
    assert months[-1]["start_date"] == date(2025, 10, 1)
    assert months[-1]["end_date"] == date(2025, 11, 1)


def test_assemble_items_uses_latest_complete_month_and_fills_missing_month():
    months = service._complete_months(date(2026, 8, 31))
    rows = [
        {
            "site": "德国",
            "sku": "TYT-90050-0159",
            "product_name": "换挡电机",
            "sales_qty_m1": Decimal("26"),
            "gross_profit_amount_m1": Decimal("3230.5"),
            "paid_amount_m1": Decimal("10000"),
            "return_qty_m1": Decimal("2"),
            "return_amount_m1": Decimal("418"),
            "sales_qty_m2": None,
            "gross_profit_amount_m2": None,
            "paid_amount_m2": None,
            "return_qty_m2": None,
            "return_amount_m2": None,
            "sales_qty_m3": Decimal("15"),
            "gross_profit_amount_m3": Decimal("1890"),
            "paid_amount_m3": Decimal("5000"),
            "return_qty_m3": Decimal("0"),
            "return_amount_m3": Decimal("0"),
            "chengdu_in_transit_quantity": Decimal("12"),
            "chengdu_sellable_quantity": Decimal("34"),
            "overseas_in_transit_quantity": Decimal("56"),
            "overseas_sellable_quantity": Decimal("78"),
        }
    ]

    item = service._assemble_items(rows, months)[0]

    assert item["sales_qty"] == "26"
    assert item["gross_profit_amount"] == "3230.50"
    assert item["profit_rate"] == "0.341367"
    assert item["return_qty"] == "2"
    assert item["return_rate"] == "0.048780"
    assert item["return_amount"] == "418.00"
    assert [metric["month"] for metric in item["monthly_metrics"]] == [
        "2026-07",
        "2026-06",
        "2026-05",
    ]
    assert item["monthly_metrics"][1] == {
        "month": "2026-06",
        "sales_qty": "0",
        "gross_profit_amount": "0.00",
        "return_qty": "0",
        "return_amount": "0.00",
    }
    assert item["chengdu_in_transit_quantity"] == "12"
    assert item["chengdu_sellable_quantity"] == "34"
    assert item["overseas_in_transit_quantity"] == "56"
    assert item["overseas_sellable_quantity"] == "78"
    assert item["sell_through_ratio"] == "0.175214"
    assert item["product_level"] == "长尾产品-B"


def test_assemble_items_leaves_three_month_rates_empty_when_denominators_are_zero():
    months = service._complete_months(date(2026, 8, 31))
    row = {
        "site": "美国",
        "sku": "ZERO-DENOMINATOR",
        "product_name": "无分母样例",
        "overseas_sellable_quantity": 0,
    }

    item = service._assemble_items([row], months)[0]

    assert item["profit_rate"] is None
    assert item["return_rate"] is None
    assert item["sell_through_ratio"] is None
    assert item["product_level"] is None
