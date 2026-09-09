from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from decimal import Decimal
from itertools import product
from pathlib import Path
import json
import pytest

from backend.services import ebay_level_rule_service as levels
from backend.services import ebay_forecast_rule_engine as engine
from backend.services import ebay_replenishment_v2_service as service
from backend.services import ebay_inventory_shared as inventory
from backend.repositories import ebay_replenishment_v2_repository as repo


def legacy(r, p, t):
    if r is None: return None
    if r > Decimal(".06"): return "C"
    if p is None: return None
    if r >= Decimal(".03"): return "C" if p < Decimal(".18") else "B"
    if t is None: return None
    if p < Decimal(".12"): return "C" if t <= Decimal(".12") else "B"
    if p < Decimal(".22"): return "B" if t < Decimal(".12") else "A"
    return "B" if t < Decimal(".15") else "S"


def test_boundary_grid_is_equivalent_to_previous_chain(level_rules):
    # All thresholds and neighbouring Decimal values, plus missing inputs.
    values = [None, Decimal("-1"), Decimal("0")]
    for threshold in (".03", ".06", ".12", ".15", ".18", ".22"):
        v = Decimal(threshold)
        values.extend([v-Decimal(".000001"), v, v+Decimal(".000001")])
    for r, p, t in product(values, repeat=3):
        assert levels.calculate_level(r,p,t,level_rules) == legacy(r,p,t)


@pytest.mark.parametrize("expression", ["r7 > 0", "return_rate", "__import__('os')", "return_rate ** 2"])
def test_bad_rules_cannot_be_saved_even_when_disabled(level_rows, expression, monkeypatch):
    level_rows[1].update(condition_expr=expression, status=0)
    writes = []
    monkeypatch.setattr(repo, "save_level_rules", lambda *a: writes.append(a))
    assert levels.check_rules(level_rows)[1]["valid"] is False
    with pytest.raises(ValueError):
        levels.save_rules(level_rows, "a"*64)
    assert not writes


def test_grade_variables_never_leak_into_forecast_whitelist():
    with pytest.raises(ValueError, match="未知变量"):
        engine.parse_expression("return_rate > 0", "bool")
    engine.parse_expression("return_rate > 0", "bool", allowed_variables=levels.VARIABLES)


def test_invalid_rule_keeps_its_priority_and_is_not_skipped(level_rows):
    level_rows[1]["condition_expr"] = "unknown > 0"
    prepared = levels.prepare_levels(level_rows)
    assert levels.calculate_level(Decimal(".04"), Decimal(".3"), Decimal(".2"), prepared) is None
    assert levels.calculate_level(Decimal(".07"), None, None, prepared) == "C"
    assert levels.calculate_level(Decimal(".07"), None, None, levels.prepare_levels([])) is None


def test_prepared_rules_do_not_reparse_per_sku(level_rows, monkeypatch):
    prepared = levels.prepare_levels(level_rows)
    monkeypatch.setattr(engine, "parse_expression", lambda *a, **kw: pytest.fail("reparsed"))
    for _ in range(30):
        assert levels.calculate_level(Decimal("0"),Decimal(".3"),Decimal(".2"),prepared) == "S"


def test_rule_revision_includes_manual_edits_but_not_server_timestamp(level_rows):
    original = repo.level_rules_revision(level_rows)
    level_rows[0]["update_time"] = "server-time"
    assert repo.level_rules_revision(level_rows) == original
    level_rows[0]["condition_expr"] = "return_rate > .07"
    assert repo.level_rules_revision(level_rows) != original


def test_stale_save_rolls_back_without_updating(level_rows, monkeypatch):
    actions = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, *args): actions.append(sql)
        def fetchall(self): return level_rows
        def executemany(self, *a): pytest.fail("must not update")
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): actions.append("commit")
        def rollback(self): actions.append("rollback")
    @contextmanager
    def connection(): yield Connection()
    monkeypatch.setattr(repo, "db_connection", connection)
    with pytest.raises(ValueError):
        repo.save_level_rules(level_rows,"tester","a"*64)
    assert any("FOR UPDATE" in s for s in actions)
    assert actions[-1] == "rollback"
    assert "commit" not in actions


def test_inventory_enrichment_is_one_batch_full_sku_not_order_sum():
    calls = []
    class Cursor:
        def execute(self, sql, params): calls.append((sql,params))
        def fetchall(self):
            return [dict(row_no=0, **{key:Decimal("4") for key in inventory.FIELDS}),
                    dict(row_no=1, **{key:Decimal("0") for key in inventory.FIELDS})]
    rows=[dict(site_name="德国",inventory_sku="A-1-SUFFIX",sold_quantity="99"),
          dict(site_name="英国",inventory_sku="A-1",sold_quantity="10")]
    inventory.enrich_sku_items(Cursor(),rows)
    assert len(calls) == 1
    sql,params=calls[0]
    assert params == [0,"德国","A-1-SUFFIX",1,"英国","A-1"]
    assert sql.count("%s") == len(params)
    assert "payment_time" not in sql and "dwd_ebay_sku_analysis_order" not in sql
    assert "SUBSTRING_INDEX" not in sql
    assert rows[0]["sold_quantity"] == "99"
    assert rows[0]["chengdu_sellable_quantity"] == "4"
    assert rows[1]["chengdu_sellable_quantity"] == "0"
    inventory.enrich_sku_items(Cursor(),[])
    assert len(calls) == 1


def test_second_quantities_use_unrounded_forecast_and_share_coefficients(level_rules):
    rules = json.loads((Path(__file__).parent/"fixtures/ebay_forecast_rules.json").read_text(encoding="utf-8"))
    for row in rules: row["formula_expr"] = "2.49"
    key=("德国","SKU")
    row=dict(site="德国",sku="SKU",sales_qty_m1=30,paid_amount_m1=100,
             gross_profit_amount_m1=30,overseas_sellable_quantity=1)
    # 2.49 / 30 * 10 * .6 = .498 -> 0; displayed forecast would round to 2.49.
    args=dict(first_listing_dates={("SKU","德国"):date(2020,1,1)},
              lead_time_days={key:Decimal(10)},
              formula_configs={"S":dict(safety_coefficient=Decimal(".6"),suggest_coefficient=Decimal("1.6"))},
              level_rules=level_rules,forecast_rules=engine.prepare_rules(rules))
    item=service._assemble_items([row],service._complete_months(),**args)[0]
    assert item["safety_stock_quantity"] == "2"
    assert item["safety_stock_quantity_2"] == "0"
    assert item["suggested_replenishment_quantity_2"] == "0"
    for r in rules: r["formula_expr"] = "2.499"
    args["forecast_rules"] = engine.prepare_rules(rules)
    item=service._assemble_items([row],service._complete_months(),**args)[0]
    assert item["forecast_sales_quantity_2"] == "2.50"
    assert item["safety_stock_quantity_2"] == "0"  # rounded 2.50 would incorrectly give 1
    args["lead_time_days"] = {}
    item=service._assemble_items([row],service._complete_months(),**args)[0]
    assert item["safety_stock_quantity_2"] is None
    args["forecast_rules"] = engine.prepare_rules([])
    item=service._assemble_items([row],service._complete_months(),**args)[0]
    assert item["suggested_replenishment_quantity_2"] is None


def test_inventory_is_enriched_only_at_sku_summary_not_order_details():
    import ast
    from backend.services import ebay_sku_analysis_service as sku_service
    tree = ast.parse(Path(sku_service.__file__).read_text(encoding="utf-8"))
    callers = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == "enrich_sku_items" for call in ast.walk(node)
        ):
            callers.append(node.name)
    assert callers == ["list_summary"]
