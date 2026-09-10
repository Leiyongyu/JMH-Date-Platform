"""eBay-only CTU cost attribution; all database access is mocked."""
from copy import deepcopy
from decimal import Decimal as D
from io import BytesIO

from openpyxl import load_workbook

from test_inventory_report_owner_age_costs import env, by_key, populate
from backend.services import inventory_report_etl_service as service
from backend.services import inventory_report_export_service as exporter


def test_ebay_cost_matches_group_sum_and_keeps_other_metrics(env):
    populate(env)
    baseline = service.get_dimension_summary("OWNER", "2026-08")
    env["ctu"] = [dict(sku="JMH-20078-0297", over_30_cost=D("12.3456")),
                  dict(sku="BMW-20078-0297", over_30_cost=D("2")),
                  dict(sku="", over_30_cost=D("4")),
                  dict(sku="UNKNOWN-001", over_30_cost=D("-1")),
                  dict(sku="CL-123", over_30_cost=D("5"))]
    actual = service.get_dimension_summary("OWNER", "2026-08")
    rows = by_key(actual)
    assert D(rows[("EBAY", "EBAY-1", "eBay负责人")]["ctu_over_30_cost"]) == D("14.3456")
    assert D(rows[("EBAY", "EBAY-1", "未分配")]["ctu_over_30_cost"]) == 3
    assert D(rows[("EBAY", "EBAY-1", "陈丽")]["ctu_over_30_cost"]) == 5
    assert rows[("EBAY", "EBAY-1", "陈丽")]["is_age_cost_only"] == 1
    assert rows[("EBAY", "EBAY-1", "陈丽")].get("total_goods_value") is None
    expected = sum((row["over_30_cost"] for row in env["ctu"]), D(0))
    assert D(actual["total"]["ctu_over_30_cost"]) == expected
    assert sum((D(row["ctu_over_30_cost"]) for row in actual["items"]
                if row["platform_code"] == "EBAY"), D(0)) == expected
    assert all(row["ctu_over_30_cost"] is None for row in actual["items"] if row["platform_code"] == "AMZ")
    ignored = {"ctu_over_30_cost", "ctu_cost_month"}
    for key, old in by_key(baseline).items():
        assert {k:v for k,v in rows[key].items() if k not in ignored} == {k:v for k,v in old.items() if k not in ignored}
    assert {k:v for k,v in actual["total"].items() if k not in ignored} == {k:v for k,v in baseline["total"].items() if k not in ignored}


def test_snapshot_none_vs_zero_and_source_rule_month(env):
    env["base"] = [dict(platform_code="EBAY", department_code="EBAY-1", dimension_value="未分配")]
    env["stat_month"] = "2026-12"
    missing = service.get_dimension_summary("OWNER")
    assert missing["items"][0]["ctu_over_30_cost"] is None
    env["ctu"] = [dict(sku=None, over_30_cost=None)]
    zero = service.get_dimension_summary("OWNER")
    assert D(zero["items"][0]["ctu_over_30_cost"]) == 0
    assert D(zero["total"]["ctu_over_30_cost"]) == 0
    assert zero["items"][0]["ctu_cost_month"] == "2027-01"
    assert ("ctu", "2027-01") in env["calls"]
    assert ("rules", "2026-12", "ebay") in env["calls"]
    assert ("sku_map", "2027-01") in env["calls"]


def test_ctu_only_owner_is_visible_and_exported(env, monkeypatch):
    env["base"] = []
    env["ctu"] = [dict(sku="FLL-001", over_30_cost=D("8.12"))]
    data = service.get_dimension_summary("OWNER", "2026-08")
    assert data["items"][0]["dimension_value"] == "方黎力"
    monkeypatch.setattr(exporter, "get_dimension_summary", lambda *args: deepcopy(data))
    _, payload = exporter.export_monthly_inventory_report("2026-08", "OWNER")
    book = load_workbook(BytesIO(payload), read_only=True)
    rows = list(book.active.values)
    column = rows[0].index("成都仓30天以上货值（仅eBay）")
    assert rows[1][column] == rows[2][column] == 8.12
    assert rows[2][3] is None
    book.close()
    assert not any("成都仓" in h[0] for h in exporter._dimension_headers("STORE"))


def test_other_dimensions_skip_ctu_personal_query(env, monkeypatch):
    def forbid(*args, **kwargs): raise AssertionError("owner-only query")
    monkeypatch.setattr(service.clearance_repo, "ctu_ebay_owner_cost_rows", forbid)
    service.get_dimension_summary("STORE", "2026-08")
    service.get_department_summary("2026-08")


def test_query_filters_only_ebay_and_keeps_negative_and_null_sku(monkeypatch):
    calls=[]
    class Fake:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def cursor(self): return self
        def execute(self,sql,params): calls.append((sql,params))
        def fetchall(self): return [dict(sku=None,over_30_cost=D(-1))]
    monkeypatch.setattr(service.clearance_repo,"db_connection",Fake)
    assert service.clearance_repo.ctu_ebay_owner_cost_rows("2026-09")[0]["over_30_cost"] == -1
    sql,params=calls[0]
    assert params == ("2026-09",)
    assert "g.group_code='EBAY-1'" in sql and "d.group_code=g.group_code" in sql
    assert "LEFT JOIN" in sql and "d.over_30_cost<>0" in sql
    assert "DISTINCT" not in sql and "d.sku IS NOT NULL" not in sql
