"""Offline rule checks; optional deployment SQL is read, never executed."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
import json
import os
import re

import pytest

from backend.services import ebay_forecast_rule_engine as engine
from backend.services import ebay_replenishment_v2_service as service

RULE_FIXTURE = Path(__file__).with_name("fixtures") / "ebay_forecast_rules.json"


@pytest.fixture
def rule_rows():
    rows = json.loads(RULE_FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) == 13
    return rows


def forecast(rows, nature="老品", s7="0", s15="0", s30="0", age=None):
    return engine.calculate_forecast(
        product_nature=nature, sales_7d=Decimal(s7), sales_15d=Decimal(s15),
        sales_30d=Decimal(s30), age_days=Decimal(age) if age is not None else None,
        rules=engine.prepare_rules(rows),
    )


@pytest.mark.parametrize("rule_no,s7,s15,s30", [
    (2, "14", "25", "50"),   # r7 == 1.2*r30
    (3, "7", "15", "30"),   # r7 == r30
    (4, "14", "20", "75"),  # r7 == .8*r30
    (5, "7", "15", "60"),   # r7 == .5*r30
    (6, "1", "2", "60"),
    (7, "0", "13", "20"),   # r15 == 1.3*r30
    (8, "0", "11", "20"),
    (9, "0", "9", "20"),
    (10, "0", "6", "20"),
    (11, "0", "1", "20"),
    (12, "0", "0", "20"),
    (13, "0", "0", "0"),
])
def test_first_match_at_all_old_tier_boundaries(rule_rows, rule_no, s7, s15, s30):
    # Mark each rule with its number to test selection independently of formulas.
    marked = [{**row, "formula_expr": str(row["rule_no"])} for row in rule_rows]
    assert forecast(marked, s7=s7, s15=s15, s30=s30) == Decimal(rule_no)


@pytest.mark.parametrize("age,expected", [
    (None, None), ("0", None), ("-1", None),
    ("15", Decimal("92.00")), ("30", Decimal("46.00")), ("96", Decimal("14.38")),
])
def test_new_product_no_age_is_missing_and_age_has_no_cap(rule_rows, age, expected):
    assert forecast(rule_rows, nature="新品", s30="46", age=age) == expected


def test_unknown_empty_and_negative_inputs(rule_rows):
    assert forecast(rule_rows, nature=None, s30="10") is None
    assert forecast([], s30="10") is None
    assert forecast(rule_rows, s7="-1") is None
    assert forecast(rule_rows, s30="NaN") is None


@pytest.mark.parametrize("condition", ["true", "True", "not false", "not False"])
def test_boolean_aliases_and_decimal_rounding(condition):
    rows = [dict(rule_no=1, product_nature="老品", condition_expr=condition, formula_expr="2.675")]
    assert forecast(rows) == Decimal("2.68")


def test_decimal_literal_uses_original_token():
    literal = "1.000000000000000000000000000000000001"
    parsed = engine.parse_expression(literal, "number")
    assert engine.interpret(parsed, {}) == Decimal(literal)


@pytest.mark.parametrize("expr", [
    '__import__("os").system("x")', "s7.real", "s7[0]", "[s7]", "(x for x in [])",
    "lambda: 1", "2**1000000", "1e309", "'hello'", "True", "unknown",
    "1 if true else 0", "1+" * 150 + "1", "1+" * 22 + "1",
])
def test_invalid_formula_stops_matching_and_is_logged(expr, caplog):
    rows = [
        dict(rule_no=2, product_nature="老品", condition_expr="true", formula_expr=expr),
        dict(rule_no=13, product_nature="老品", condition_expr="true", formula_expr="0"),
    ]
    assert forecast(rows) is None
    assert "rule_no=2" in caplog.text


@pytest.mark.parametrize("condition", ["1", "s7", "s7 and true", "true + 1 > 0", ""])
def test_condition_must_be_boolean(condition):
    assert forecast([dict(rule_no=1, product_nature="老品",
                          condition_expr=condition, formula_expr="1")]) is None


@pytest.mark.parametrize("formula", ["1/0", "-1", "1e24 * 2", "1/1e-24 * 30"])
def test_runtime_error_does_not_fall_through(formula, caplog):
    rows = [
        dict(rule_no=2, product_nature="老品", condition_expr="true", formula_expr=formula),
        dict(rule_no=13, product_nature="老品", condition_expr="true", formula_expr="0"),
    ]
    prepared = engine.prepare_rules(rows)
    for _ in range(3):
        assert engine.calculate_forecast(product_nature="老品", sales_7d=Decimal(0),
            sales_15d=Decimal(0), sales_30d=Decimal(0), age_days=None, rules=prepared) is None
    assert sum("rule_no=2" in record.message for record in caplog.records) == 1


def test_boolean_short_circuit_avoids_division_by_zero():
    rows = [
        dict(rule_no=2, product_nature="老品", condition_expr="age > 0 and s30 / age > 1", formula_expr="99"),
        dict(rule_no=13, product_nature="老品", condition_expr="true", formula_expr="0"),
    ]
    assert forecast(rows) == Decimal("0.00")


def test_rule_change_affects_only_matched_branch(rule_rows):
    changed = deepcopy(rule_rows)
    changed[1]["formula_expr"] = "(r7*0.9 + r15*0.2 + r30*0.1) * 30"
    before = forecast(rule_rows, s7="14", s15="25", s30="50")
    after = forecast(changed, s7="14", s15="25", s30="50")
    assert after - before == Decimal("12.00")
    assert forecast(changed, s30="15") == forecast(rule_rows, s30="15")


def test_preparation_is_once_per_batch_and_assembly_keeps_other_fields(rule_rows, monkeypatch):
    calls = 0
    original_parse = engine.ast.parse

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(engine.ast, "parse", counted)
    prepared = engine.prepare_rules(rule_rows)
    assert calls == 26
    row = {"site": "英国", "sku": "SKU", "sales_qty_m1": Decimal(46), "sales_qty_30d": Decimal(46)}
    months = service._complete_months(date(2026, 9, 1))
    baseline = service._assemble_items([row], months, first_listing_dates={("SKU", "英国"): date.today()})
    actual = service._assemble_items([row] * 20, months,
        first_listing_dates={("SKU", "英国"): date.today()}, inventory_ages={("英国", "SKU"): Decimal(96)},
        forecast_rules=prepared)
    assert calls == 26
    assert actual[0]["forecast_sales_quantity_2"] == "14.38"
    for key, value in baseline[0].items():
        if key not in {"forecast_sales_quantity_2", "overseas_inventory_age_days"}:
            assert actual[0][key] == value
    assert baseline[0]["forecast_sales_quantity_2"] is None


def test_forecast_sort_keeps_missing_values_last():
    rows = [{"site": "英国", "sku": str(i), "forecast_sales_quantity_2": value}
            for i, value in enumerate([None, "2.00", "10.00"])]
    assert [r["forecast_sales_quantity_2"] for r in service._sort_forecast_sales_2(rows, "DESC")] == ["10.00", "2.00", None]


def test_migration_preserves_user_edits_and_rule_13_is_explicit(rule_rows):
    path = os.environ.get("FORECAST_RULE_DEPLOYMENT_SQL")
    if not path:
        pytest.skip("Set FORECAST_RULE_DEPLOYMENT_SQL to audit the external deployment artifact")
    sql = Path(path).read_text(encoding="utf-8-sig")
    matches = re.findall(r"\(\s*(\d+)\s*,'(新品|老品)','([^']*)',\s*'([^']*)'", sql)
    actual = [dict(rule_no=int(no), product_nature=nature, condition_expr=condition, formula_expr=formula)
              for no, nature, condition, formula in matches]
    assert actual == rule_rows
    tail = sql.split("ON DUPLICATE KEY UPDATE `rule_no`")[-1].split(";")[0]
    assert tail.strip() == "= `rule_no`"
    assert rule_rows[-1]["condition_expr"] == "s7 == 0 and s15 == 0 and s30 == 0"


def test_removed_edit_routes_and_safety_stock_routes_remain():
    from backend.api.v1.ebay_replenishment_v2 import router
    paths = {route.path for route in router.routes}
    prefix = "/api/v1/finance/ebay-replenishment-v2"
    assert prefix + "/forecast-formula" not in paths
    assert prefix + "/formula" in paths
    assert prefix + "/list" in paths

def test_matches_independent_exact_reference(rule_rows):
    """Independent Fraction oracle is test-only; production uses Decimal exclusively."""
    from fractions import Fraction
    from random import Random

    rng = Random(20260908)
    prepared = engine.prepare_rules(rule_rows)

    def expected(s7, s15, s30):
        r7, r15, r30 = Fraction(s7, 7), Fraction(s15, 15), Fraction(s30, 30)
        if s7:
            tiers = [
                ("1.2", ("0.7", "0.2", "0.1")), ("1", ("0.6", "0.25", "0.15")),
                ("0.8", ("0.5", "0.3", "0.2")), ("0.5", ("0.35", "0.35", "0.3")),
                (None, ("0.2", "0.3", "0.5")),
            ]
            weights = next(weights for threshold, weights in tiers
                           if threshold is None or r7 >= Fraction(threshold) * r30)
            result = sum(rate * Fraction(weight) for rate, weight in zip((r7, r15, r30), weights)) * 30
        elif s15:
            tiers = [
                ("1.3", ("0.6", "0.4")), ("1.1", ("0.5", "0.5")),
                ("0.9", ("0.4", "0.6")), ("0.6", ("0.3", "0.7")), (None, ("0.2", "0.8")),
            ]
            weights = next(weights for threshold, weights in tiers
                           if threshold is None or r15 >= Fraction(threshold) * r30)
            result = sum(rate * Fraction(weight) for rate, weight in zip((r15, r30), weights)) * 30
        else:
            result = Fraction(s30)
        cents = (result.numerator * 200 + result.denominator) // (2 * result.denominator)
        return Decimal(cents) / Decimal(100)

    cases = [(0, fifteen, thirty) for thirty in range(1, 61) for fifteen in range(thirty + 1)]
    cases += [tuple(sorted(rng.randrange(500) for _ in range(3))) for _ in range(200)]
    for s7, s15, s30 in cases:
        actual = engine.calculate_forecast(product_nature="老品",
            sales_7d=Decimal(s7), sales_15d=Decimal(s15), sales_30d=Decimal(s30),
            age_days=None, rules=prepared)
        assert actual == expected(s7, s15, s30), (s7, s15, s30)


@pytest.mark.parametrize("error_code", [1146, 1142])
def test_only_missing_rule_table_degrades_to_missing_values(monkeypatch, caplog, error_code):
    from contextlib import contextmanager
    from pymysql.err import ProgrammingError
    from backend.repositories import ebay_replenishment_v2_repository as repository

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query):
            assert "ebay_replenishment_v2_forecast_rule" in query
            raise ProgrammingError(error_code, "fixture database error")

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(repository, "db_connection", connection)
    if error_code == 1146:
        assert repository.forecast_rules() == []
        assert "规则表未部署" in caplog.text
    else:
        with pytest.raises(ProgrammingError):
            repository.forecast_rules()
