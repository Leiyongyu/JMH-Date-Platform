from decimal import Decimal

import pytest

from backend.services import ebay_replenishment_v2_service as service


@pytest.mark.parametrize(
    ("return_rate", "profit_rate", "turnover_rate", "expected"),
    [
        ("0.061", "0.30", "0.30", "C"),
        ("0.03", "0.179", "0.30", "C"),
        ("0.029", "0.119", "0.12", "C"),
        ("0.03", "0.18", "0.30", "B"),
        ("0.029", "0.119", "0.121", "B"),
        ("0.029", "0.12", "0.119", "B"),
        ("0.029", "0.22", "0.149", "B"),
        ("0.029", "0.12", "0.12", "A"),
        ("0.029", "0.22", "0.15", "S"),
    ],
)
def test_product_level_rules_follow_declared_priority(
    return_rate, profit_rate, turnover_rate, expected, level_rules
):
    assert service._product_level(
        Decimal(return_rate), Decimal(profit_rate), Decimal(turnover_rate), level_rules
    ) == expected


def test_profit_rate_uses_unrounded_source_amounts():
    assert service._ratio_text(
        Decimal("248.172"), Decimal("198.574547")
    ) == "1.249767"


@pytest.mark.parametrize("stock,expected", [
    (0, "10"), ("0.0000", "10"), (Decimal("0"), "10"),
    (2, "5"), (Decimal("0.5"), "20"), (-2, "-5"),
    (None, None), ("", None), ("invalid", None), ("NaN", None),
])
def test_sell_through_zero_fallback_is_local_to_this_ratio(stock, expected):
    actual = service._sell_through_ratio(Decimal("10"), stock)
    assert actual == (Decimal(expected) if expected is not None else None)
    assert service._ratio_decimal(Decimal("10"), 0) is None


def test_zero_stock_allows_grading_without_changing_stock_or_replenishment(level_rules):
    row = dict(site="德国", sku="ZERO-STOCK", sales_qty_m1=30,
               paid_amount_m1=100, gross_profit_amount_m1=30,
               return_qty_m1=0, overseas_sellable_quantity=0)
    item = service._assemble_items(
        [row], service._complete_months(), level_rules=level_rules,
        lead_time_days={("德国", "ZERO-STOCK"): Decimal("30")},
        formula_configs={"S": dict(safety_coefficient=Decimal("0.6"),
                                  suggest_coefficient=Decimal("1.6"))},
    )[0]
    assert item["forecast_sales_quantity"] == "10.00"
    assert item["sell_through_ratio"] == "10.000000"
    assert item["product_level"] == "S"
    assert row["overseas_sellable_quantity"] == 0
    assert item["overseas_sellable_quantity"] == "0"
    assert item["safety_stock_quantity"] == "6"
    assert item["suggested_replenishment_quantity"] == "16"


def test_turnover_uses_unrounded_three_month_average():
    metrics = [
        {"sales_qty": "1"},
        {"sales_qty": "0"},
        {"sales_qty": "0"},
    ]
    raw_forecast = service._average_metric_decimal(metrics, "sales_qty")

    assert service._average_metric(metrics, "sales_qty") == "0.33"
    assert service._ratio_decimal_text(
        service._ratio_decimal(raw_forecast, Decimal("2"))
    ) == "0.166667"
