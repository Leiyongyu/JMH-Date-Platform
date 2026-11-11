"""CTU over-30 cost attribution for eBay and EU (US stays empty); all database access is mocked."""
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


def test_snapshot_none_vs_zero_and_report_rule_month(env):
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
    assert ("rules", "2027-01", "ebay") in env["calls"]
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
    column = rows[0].index("成都仓30天以上货值（eBay、EU）")
    assert rows[1][column] == rows[2][column] == 8.12
    assert rows[2][3] is None
    book.close()
    assert not any("成都仓" in h[0] for h in exporter._dimension_headers("STORE"))


def test_other_dimensions_skip_ctu_personal_query(env, monkeypatch):
    def forbid(*args, **kwargs): raise AssertionError("owner-only query")
    monkeypatch.setattr(service.clearance_repo, "ctu_owner_cost_rows", forbid)
    service.get_dimension_summary("STORE", "2026-08")
    service.get_department_summary("2026-08")


def test_query_filters_ebay_and_eu_and_keeps_negative_and_null_sku(monkeypatch):
    calls=[]
    class Fake:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def cursor(self): return self
        def execute(self,sql,params): calls.append((sql,params))
        def fetchall(self): return [dict(sku=None,over_30_cost=D(-1))]
    monkeypatch.setattr(service.clearance_repo,"db_connection",Fake)
    assert service.clearance_repo.ctu_owner_cost_rows("2026-09")[0]["over_30_cost"] == -1
    sql,params=calls[0]
    assert params == ("2026-09",)
    assert "g.group_code IN ('EBAY-1','EU')" in sql and "d.group_code=g.group_code" in sql
    assert "SELECT g.group_code,d.sku,d.over_30_cost" in sql
    assert "LEFT JOIN" in sql and "d.over_30_cost<>0" in sql
    assert "DISTINCT" not in sql and "d.sku IS NOT NULL" not in sql


def test_eu_ctu_cost_is_split_by_brand_rules_and_us_stays_empty(env):
    """EU 成都仓 30 天以上货值按品牌 / OTH 规则归属负责人（与本地仓同口径）；US 不参与，显示 --。"""
    populate(env)
    env["base"].extend([
        dict(platform_code="AMZ", dimension_type="OWNER", department_code="AMZ-US1", dimension_value="US1负责人"),
    ])
    env["ctu"] = [
        dict(group_code="EBAY-1", sku="JMH-20078-0297", over_30_cost=D("12")),
        dict(group_code="EU", sku="ABC-001", over_30_cost=D("7.5")),
        dict(group_code="EU", sku="OTH-2301-009", over_30_cost=D("2")),
        dict(group_code="EU", sku="ZZZ-1", over_30_cost=D("1")),
    ]
    actual = service.get_dimension_summary("OWNER", "2026-08")
    rows = by_key(actual)
    assert D(rows[("AMZ", "AMZ-EU", "品牌负责人")]["ctu_over_30_cost"]) == D("7.5")
    assert D(rows[("AMZ", "AMZ-EU", "OTH负责人")]["ctu_over_30_cost"]) == 2
    assert D(rows[("AMZ", "AMZ-EU", "未分配")]["ctu_over_30_cost"]) == 1
    assert D(rows[("EBAY", "EBAY-1", "eBay负责人")]["ctu_over_30_cost"]) == 12
    assert rows[("AMZ", "AMZ-US1", "US1负责人")]["ctu_over_30_cost"] is None, "US 负责人按店铺，成都仓无店铺，不参与"
    assert D(actual["total"]["ctu_over_30_cost"]) == D("22.5"), "合计 = eBay + EU"


def test_eu_without_ctu_snapshot_shows_dash_while_ebay_has_value(env):
    populate(env)
    env["ctu"] = [dict(group_code="EBAY-1", sku="JMH-20078-0297", over_30_cost=D("3"))]
    rows = by_key(service.get_dimension_summary("OWNER", "2026-08"))
    assert rows[("AMZ", "AMZ-EU", "未分配")]["ctu_over_30_cost"] is None, "EU 没有快照显示 --，不当 0"
    assert D(rows[("EBAY", "EBAY-1", "eBay负责人")]["ctu_over_30_cost"]) == 3
    env["ctu"].append(dict(group_code="EU", sku=None, over_30_cost=None))  # EU 有快照但无成本
    rows = by_key(service.get_dimension_summary("OWNER", "2026-08"))
    assert D(rows[("AMZ", "AMZ-EU", "未分配")]["ctu_over_30_cost"]) == 0
