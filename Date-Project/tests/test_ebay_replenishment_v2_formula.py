from decimal import Decimal

import pytest

from backend.services import ebay_replenishment_v2_service as service


FORMULAS = {
    "S": {
        "safety_coefficient": Decimal("0.6"),
        "suggest_coefficient": Decimal("1.6"),
    },
    "A": {
        "safety_coefficient": Decimal("0.4"),
        "suggest_coefficient": Decimal("1.4"),
    },
    "B": {
        "safety_coefficient": Decimal("0.2"),
        "suggest_coefficient": Decimal("1.2"),
    },
    "C": {
        "safety_coefficient": Decimal("0"),
        "suggest_coefficient": Decimal("0"),
    },
}


def calculate(level="S", inventory="20", lead_times=None, formulas=None):
    return service._replenishment_quantities(
        site="德国",
        sku="SKU-1",
        average_monthly_sales=Decimal("90"),
        product_level=level,
        inventory_total=Decimal(inventory),
        lead_time_days=(
            {("德国", "SKU-1"): Decimal("10")}
            if lead_times is None
            else lead_times
        ),
        formula_configs=FORMULAS if formulas is None else formulas,
    )


def test_replenishment_formula_uses_decimal_coefficients_and_inventory():
    assert calculate() == ("18", "28")


def test_long_tail_b_uses_b_coefficients():
    assert calculate(level="B") == ("6", "16")


def test_c_level_is_zero_when_lead_time_exists():
    assert calculate(level="C") == ("0", "0")


def test_missing_lead_time_returns_none_instead_of_zero():
    assert calculate(lead_times={}) == (None, None)


def test_missing_level_config_returns_none_without_code_default():
    formulas = {key: value for key, value in FORMULAS.items() if key != "S"}
    assert calculate(formulas=formulas) == (None, None)


def test_negative_suggested_quantity_is_clamped_to_zero():
    assert calculate(inventory="1000") == ("18", "0")


def test_half_up_rounding_is_used_for_both_quantities():
    result = service._replenishment_quantities(
        site="德国",
        sku="SKU-1",
        average_monthly_sales=Decimal("1"),
        product_level="S",
        inventory_total=Decimal("0"),
        lead_time_days={("德国", "SKU-1"): Decimal("25")},
        formula_configs=FORMULAS,
    )
    assert result == ("1", "1")


def test_save_requires_exactly_four_levels_and_persists_all(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        service.repository,
        "save_formula_rows",
        lambda rows, operator: saved.update(rows=rows, operator=operator),
    )
    monkeypatch.setattr(
        service.repository,
        "list_formula_rows",
        lambda: [
            {
                "product_level": row["product_level"],
                "safety_coefficient": row["safety_coefficient"],
                "suggest_coefficient": row["suggest_coefficient"],
                "remark": row["remark"],
                "status": 1,
            }
            for row in saved["rows"]
        ],
    )
    payload = [
        {
            "product_level": level,
            "safety_coefficient": config["safety_coefficient"],
            "suggest_coefficient": config["suggest_coefficient"],
        }
        for level, config in FORMULAS.items()
    ]

    response = service.save_formula_configs(payload, "tester")

    assert saved["operator"] == "tester"
    assert [row["product_level"] for row in response] == ["S", "A", "B", "C"]


def test_save_rejects_incomplete_or_negative_config():
    with pytest.raises(ValueError, match="必须且只能包含"):
        service.save_formula_configs([], "tester")
    invalid = [
        {
            "product_level": level,
            "safety_coefficient": -1 if level == "S" else 0,
            "suggest_coefficient": 0,
        }
        for level in ("S", "A", "B", "C")
    ]
    with pytest.raises(ValueError, match="必须大于或等于0"):
        service.save_formula_configs(invalid, "tester")
