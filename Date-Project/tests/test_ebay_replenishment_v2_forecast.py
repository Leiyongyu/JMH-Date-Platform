from datetime import date
from decimal import Decimal

from backend.services import ebay_replenishment_v2_service as service


def test_forecast_metrics_average_all_three_complete_months_including_zero_month():
    months = service._complete_months(date(2026, 8, 31))
    rows = [
        {
            "site": "德国",
            "sku": "TYT-90050-0159",
            "product_name": "换挡电机",
            "sales_qty_m1": Decimal("26"),
            "gross_profit_amount_m1": Decimal("3230.50"),
            "return_qty_m1": Decimal("2"),
            "return_amount_m1": Decimal("418.00"),
            "sales_qty_m2": None,
            "gross_profit_amount_m2": None,
            "return_qty_m2": None,
            "return_amount_m2": None,
            "sales_qty_m3": Decimal("15"),
            "gross_profit_amount_m3": Decimal("1890.00"),
            "return_qty_m3": Decimal("0"),
            "return_amount_m3": Decimal("0"),
        }
    ]

    item = service._assemble_items(rows, months)[0]

    assert item["forecast_sales_quantity"] == "13.67"
    assert item["forecast_gross_profit_amount"] == "1706.83"
    assert item["forecast_return_quantity"] == "0.67"
    assert item["forecast_return_amount"] == "139.33"
