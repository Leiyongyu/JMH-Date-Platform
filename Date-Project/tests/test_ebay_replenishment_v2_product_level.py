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
    return_rate, profit_rate, turnover_rate, expected
):
    assert service._product_level(
        Decimal(return_rate), Decimal(profit_rate), Decimal(turnover_rate)
    ) == expected


def test_profit_rate_uses_unrounded_source_amounts():
    assert service._ratio_text(
        Decimal("248.172"), Decimal("198.574547")
    ) == "1.249767"


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
