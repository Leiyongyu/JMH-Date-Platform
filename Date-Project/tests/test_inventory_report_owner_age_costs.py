"""OWNER age-cost regression tests. All DB access is mocked; no data sync."""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from backend.services import inventory_report_etl_service as service
from backend.services import inventory_report_export_service as exporter

D = Decimal
COST_FIELDS = {"inventory_age_90_180_cost", "inventory_age_180_plus_cost", "inventory_age_cost_month"}


@pytest.fixture
def env(monkeypatch):
    state = dict(costs=[], health=[], rules={"amazon": [], "ebay": []}, sku_map={}, calls=[],
                 base=[{"platform_code": "AMZ", "dimension_type": "OWNER",
                        "department_code": "AMZ-EU", "dimension_value": "未分配",
                        "fba_end_inventory_qty": D(10), "fba_end_inventory_total_cost": D(100)}],
                 stat_month="2026-08", group_costs={})

    def forbid(*args, **kwargs):
        raise AssertionError("Tests must not access a real database")

    monkeypatch.setattr(service.repo, "db_connection", forbid)
    monkeypatch.setattr(service.repo, "dimension_summary", lambda dim, month: {
        "stat_month": state["stat_month"], "items": deepcopy(state["base"])})
    monkeypatch.setattr(service.repo, "inventory_age_cost_rows", lambda month: (
        state["calls"].append(("costs", month)) or deepcopy(state["costs"])))
    monkeypatch.setattr(service.repo, "inventory_age_health_rows", lambda month: (
        state["calls"].append(("health", month)) or deepcopy(state["health"])))
    monkeypatch.setattr(service.repo, "owner_rules", lambda month, platform: (
        state["calls"].append(("rules", month, platform)) or state["rules"][platform]))
    monkeypatch.setattr(service.repo, "ebay_product_sku_map", lambda month: (
        state["calls"].append(("sku_map", month)) or state["sku_map"]))
    for name in ("usd_rate", "amz_sales_amount_by_department", "ebay_sales_amount",
                 "amz_sales_volume_by_owner", "amz_sales_volume_by_store",
                 "ebay_sales_volume_rows", "amz_sales_volume_by_department", "ebay_sales_volume"):
        monkeypatch.setattr(service.repo, name, lambda *args: None)
    monkeypatch.setattr(service.repo, "sales_amount_by_owner", lambda *args: {})
    monkeypatch.setattr(service.repo, "amz_sales_amount_by_store", lambda *args: [])
    monkeypatch.setattr(service.clearance_repo, "ctu_over_30_costs", lambda month: {})
    state["ctu"] = []
    monkeypatch.setattr(service.clearance_repo, "ctu_ebay_owner_cost_rows", lambda month: (
        state["calls"].append(("ctu", month)) or deepcopy(state["ctu"])))
    monkeypatch.setattr(service.repo, "inventory_age_group_costs", lambda month: state["group_costs"])
    monkeypatch.setattr(service.repo, "department_summary", lambda month: {
        "stat_month": state["stat_month"],
        "items": [{"department_code": code, "is_total": 0} for code, _, _ in service.DEPARTMENTS]
                 + [{"department_code": "AUTO-PARTS-TOTAL", "is_total": 1}],
    })
    return state


def amz(group, sku, store, cost1, cost2):
    return dict(platform_code="AMZ", group_code=group, sku=sku, store_name=store,
                cost_91_180=D(str(cost1)), cost_181_plus=D(str(cost2)), is_aged_sku=1)


def ebay(sku, cost1, cost2):
    return dict(platform_code="EBAY", group_code="EBAY-1", sku=sku, store_name=None,
                cost_91_180=D(str(cost1)), cost_181_plus=D(str(cost2)), is_aged_sku=1)


def populate(env):
    env["rules"]["amazon"] = [
        dict(group_code="EU", rule_type="BRAND", match_key="ABC", principal_name="品牌负责人"),
        dict(group_code="EU", rule_type="OTH_CODE", match_key="2301", principal_name="OTH负责人"),
        dict(group_code="US1", rule_type="STORE", match_key="店铺一", principal_name="US1负责人"),
        dict(group_code="US3", rule_type="STORE", match_key="富琳顿", principal_name="毛静"),
        dict(group_code="US3", rule_type="STORE", match_key="店铺三", principal_name="张"),
    ]
    env["rules"]["ebay"] = [dict(rule_type="EBAY_BRAND", match_key="BMW", principal_name="eBay负责人")]
    env["sku_map"] = {"20078-0297": "BMW-20078-0297"}
    env["costs"] = [
        amz("EU", "ABC-001", "EU-店铺-DE", "10.2501", 20),
        amz("EU", "OTH-2301-001", "EU-店铺-DE", 2, 3),
        amz("EU", "ABC-001", "EU-店铺-UK", 1, 2),
        amz("EU", "", "", 4, -2),  # No SKU still contributes to unassigned.
        amz("US1", "ABC-001", "US1-店铺一-US", 8, 9),
        amz("US1", "ABC-001", "US1-店铺一-CA", 3, 5),  # No monetary SKU dedup.
        amz("US2", "NO-MATCH", "US2-未知-US", -1, 5),
        amz("US2-MJ", "ABC-001", "US3-富琳顿-US", 4, 5),
        amz("US1-ZXY", "ABC-001", "US3-店铺三-US", 6, 7),
        ebay("JMH-20078-0297", 11, 12),
        ebay("", 3, 4),
    ]
    env["health"] = deepcopy(env["costs"])
    totals = defaultdict(lambda: {"inventory_91_180_cost": D(0), "inventory_181_plus_cost": D(0)})
    for row in env["costs"]:
        totals[row["group_code"]]["inventory_91_180_cost"] += row["cost_91_180"]
        totals[row["group_code"]]["inventory_181_plus_cost"] += row["cost_181_plus"]
    env["group_costs"] = totals


def by_key(result):
    return {(row["platform_code"], row["department_code"], row["dimension_value"]): row
            for row in result["items"]}


def test_owner_sums_equal_every_group_and_total_including_unassigned(env):
    populate(env)
    owner = service.get_dimension_summary("OWNER", "2026-08")
    group = service.get_department_summary("2026-08")
    rows = by_key(owner)
    assert ("AMZ", "AMZ-EU", service.EU_UK_FIXED_OWNER) in rows
    assert ("AMZ", "AMZ-EU", "OTH负责人") in rows
    assert ("AMZ", "AMZ-US2-MJ", "毛静") in rows
    assert ("AMZ", "AMZ-US1-ZXY", "张") in rows
    assert rows[("EBAY", "EBAY-1", "eBay负责人")]["inventory_age_90_180_cost"] == "11"
    assert rows[("AMZ", "AMZ-US1", "US1负责人")]["inventory_age_90_180_cost"] == "11"
    assert rows[("AMZ", "AMZ-EU", "未分配")]["inventory_age_180_plus_cost"] == "-2"
    for expected in group["items"]:
        total = int(expected["is_total"]) == 1
        for field in ("inventory_age_90_180_cost", "inventory_age_180_plus_cost"):
            actual = sum((D(row[field]) for row in owner["items"]
                          if total or row["department_code"] == expected["department_code"]), D(0))
            assert actual == D(expected[field])
            if total:
                assert D(owner["total"][field]) == actual
        assert expected["inventory_age_cost_month"] == "2026-09"
    assert all(row["inventory_age_cost_month"] == "2026-09" for row in owner["items"])


def test_rules_and_sku_mapping_loaded_once_for_health_and_costs(env):
    populate(env)
    service.get_dimension_summary("OWNER", "2026-08")
    assert env["calls"].count(("rules", "2026-08", "amazon")) == 1
    assert env["calls"].count(("rules", "2026-08", "ebay")) == 1
    assert env["calls"].count(("sku_map", "2026-09")) == 1
    assert env["calls"].count(("costs", "2026-09")) == 1
    assert env["calls"].count(("health", "2026-09")) == 1


def test_year_boundary_uses_source_rules_and_report_snapshot(env):
    env["stat_month"] = "2026-12"
    service.get_dimension_summary("OWNER", "2026-12")
    assert ("health", "2027-01") in env["calls"]
    assert ("costs", "2027-01") in env["calls"]
    assert ("rules", "2026-12", "amazon") in env["calls"]
    assert ("sku_map", "2027-01") in env["calls"]


def test_existing_owner_metrics_and_total_are_unchanged_by_cost_only_rows(env):
    populate(env)
    costs = env["costs"]
    env["costs"] = []
    baseline = service.get_dimension_summary("OWNER", "2026-08")
    env["costs"] = costs
    actual = service.get_dimension_summary("OWNER", "2026-08")
    assert {key: value for key, value in actual["total"].items() if key not in COST_FIELDS} == {
        key: value for key, value in baseline["total"].items() if key not in COST_FIELDS}
    for key, old in by_key(baseline).items():
        new = by_key(actual)[key]
        assert {k: v for k, v in new.items() if k not in COST_FIELDS} == {
            k: v for k, v in old.items() if k not in COST_FIELDS}
    added = [row for row in actual["items"] if row.get("is_age_cost_only")]
    assert added
    assert all(row.get("total_goods_value") is None for row in added)
    assert all(row.get("actual_achievement_amount") is None for row in added)


def test_missing_snapshot_is_none_but_zero_cost_snapshot_is_zero(env):
    missing = service.get_dimension_summary("OWNER", "2026-08")
    assert missing["items"][0]["inventory_age_90_180_cost"] is None
    assert missing["total"]["inventory_age_90_180_cost"] is None
    env["health"] = [amz("EU", "YOUNG", "EU-店-DE", 0, 0)]
    env["health"][0]["is_aged_sku"] = 0
    zero = service.get_dimension_summary("OWNER", "2026-08")
    assert D(zero["items"][0]["inventory_age_90_180_cost"]) == 0
    assert D(zero["items"][0]["inventory_age_180_plus_cost"]) == 0
    assert zero["total"]["inventory_age_90_180_cost"] is None  # Other groups missing.


def test_partial_snapshot_does_not_turn_missing_platform_to_zero(env):
    env["base"].append(dict(platform_code="EBAY", department_code="EBAY-1", dimension_value="未分配"))
    env["health"] = [amz("EU", "YOUNG", "EU-店-DE", 0, 0)]
    rows = by_key(service.get_dimension_summary("OWNER", "2026-08"))
    assert D(rows[("AMZ", "AMZ-EU", "未分配")]["inventory_age_90_180_cost"]) == 0
    assert rows[("EBAY", "EBAY-1", "未分配")]["inventory_age_90_180_cost"] is None


def test_only_cost_data_keeps_owner_visible_without_inventing_old_metrics(env):
    env["base"] = []
    env["costs"] = [ebay("", 1, 2)]
    data = service.get_dimension_summary("OWNER", "2026-08")
    assert data["items"][0]["dimension_value"] == "未分配"
    assert data["items"][0]["is_age_cost_only"] == 1
    assert data["total"]["is_age_cost_only"] == 1
    assert data["total"].get("total_goods_value") is None


def test_no_month_does_not_query_rules_or_costs(env):
    env["stat_month"] = None
    env["base"] = []
    data = service.get_dimension_summary("OWNER")
    assert data["items"] == [] and data["total"] is None
    assert env["calls"] == []


@pytest.mark.parametrize("dimension", ["GROUP", "STORE"])
def test_other_dimensions_do_not_read_costs_or_add_columns(env, monkeypatch, dimension):
    populate(env)
    def unexpected(*args, **kwargs):
        raise AssertionError("Other dimensions must not call owner cost query")
    monkeypatch.setattr(service.repo, "inventory_age_cost_rows", unexpected)
    if dimension == "GROUP":
        service.get_department_summary("2026-08")
    else:
        result = service.get_dimension_summary("STORE", "2026-08")
        assert not any(field in row for row in result["items"] + [result["total"]] for field in COST_FIELDS)
        assert not any("costs" == call[0] for call in env["calls"])


def test_cost_sql_is_narrow_parameterized_and_keeps_negative_values(monkeypatch):
    calls = []
    class Fake:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return self
        def execute(self, sql, params): calls.append((sql, params))
        def fetchall(self): return [{"cost_91_180": D("-1")}]
    monkeypatch.setattr(service.repo, "db_connection", Fake)
    result = service.repo.inventory_age_cost_rows("2026-09")
    sql, params = calls[0]
    assert result[0]["cost_91_180"] == D("-1")
    assert params == ("2026-09", "2026-09")
    assert sql.count("pull_month=%s") == 2
    assert "inventory_91_180_cost<>0 OR inventory_181_plus_cost<>0" in sql
    assert "inventory_age_cost<>0" in sql
    assert "match_status" not in sql
    assert "inventory_quantity" not in sql
    assert "UNION ALL" in sql


def test_owner_export_has_same_two_values_and_store_is_unchanged(env, monkeypatch):
    populate(env)
    data = service.get_dimension_summary("OWNER", "2026-08")
    monkeypatch.setattr(exporter, "get_dimension_summary", lambda *args: data)
    _, content = exporter.export_monthly_inventory_report("2026-08", "OWNER")
    book = load_workbook(BytesIO(content), read_only=True)
    values = list(book.active.values)
    assert values[0][-2:] == ("90-180库龄成本", "180+库龄成本")
    for excel, row in zip(values[1:], [data["total"], *data["items"]]):
        assert excel[-2] == float(row["inventory_age_90_180_cost"])
        assert excel[-1] == float(row["inventory_age_180_plus_cost"])
        if row.get("is_age_cost_only"):
            assert excel[3] is None  # total value unknown, not zero
            assert excel[4:8] == (None, None, None, None)
    assert len(exporter._dimension_headers("STORE")) == 13
    assert len(exporter._group_headers("2026-09")) == 23
    book.close()
