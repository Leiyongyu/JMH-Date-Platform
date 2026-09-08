"""Offline editor checks: no business database, running service or external calls."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api.v1 import ebay_replenishment_v2 as api
from backend.repositories import ebay_replenishment_v2_repository as repo
from backend.services import ebay_forecast_rule_engine as engine
from backend.services import ebay_forecast_rule_service as service

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def prevent_database(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline tests must not access a database")
    monkeypatch.setattr(repo, "db_connection", forbidden)


@pytest.fixture
def rules():
    rows = json.loads((Path(__file__).with_name("fixtures") / "ebay_forecast_rules.json").read_text(encoding="utf-8"))
    assert len(rows) == 13
    return [{**row, "status": 1, "remark": f"规则{row['rule_no']}"} for row in rows]


def preview(rules, nature="老品", s7="14", s15="25", s30="50", age=None):
    return service.preview_forecast(rules, product_nature=nature,
        sales_7d=Decimal(s7), sales_15d=Decimal(s15), sales_30d=Decimal(s30),
        age_days=Decimal(age) if age is not None else None)


@pytest.mark.parametrize("field,expression,error", [
    ("condition_expr", "r5 > 0", "未知变量"),
    ("condition_expr", "s7", "条件必须"),
    ("formula_expr", "true", "公式必须"),
    ("formula_expr", "__import__('os')", "不允许"),
    ("formula_expr", "s7 ** 2", "不允许"),
    ("condition_expr", "", "不能为空"),
])
def test_invalid_draft_is_reported_and_never_written(rules, field, expression, error, monkeypatch):
    rules[1][field] = expression
    rules[1]["status"] = 0  # Disabled rules must also validate before persistence.
    writes = []
    monkeypatch.setattr(repo, "save_forecast_rules", lambda *args: writes.append(args))
    result = service.validate_forecast_rules(rules)
    assert not result["valid"]
    assert error in result["rows"][1]["errors"][field]
    with pytest.raises(ValueError, match="规则2校验失败"):
        service.save_forecast_rules(rules, "a" * 64)
    assert writes == []
    result = preview(rules)
    assert result["result"]["status"] == "invalid_draft"
    assert result["result"]["value"] is None


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "nature", "status", "remark"])
def test_immutable_metadata_and_complete_payload(rules, mutation):
    if mutation == "missing":
        rules.pop()
    elif mutation == "duplicate":
        rules[1]["rule_no"] = 1
    elif mutation == "nature":
        rules[1]["product_nature"] = "新品"
    elif mutation == "status":
        rules[1]["status"] = 2
    else:
        rules[1]["remark"] = "x" * 256
    with pytest.raises(ValueError):
        service.validate_forecast_rules(rules)


def test_draft_preview_uses_unsaved_expression_and_same_engine(rules):
    rules[1]["formula_expr"] = "(r7*0.9 + r15*0.05 + r30*0.05)*30"
    result = preview(rules)["result"]
    direct = engine.calculate_forecast(product_nature="老品",
        sales_7d=Decimal(14), sales_15d=Decimal(25), sales_30d=Decimal(50),
        age_days=None, rules=engine.prepare_rules(rules))
    assert result["matched_rule_no"] == 2
    assert result["value"] == "59.00" == format(direct, "f")
    assert result["formula_expr"] == rules[1]["formula_expr"]
    assert result["remark"] == "规则2"


@pytest.mark.parametrize("no,s7,s15,s30", [
    (2, "14", "25", "50"), (3, "7", "15", "30"), (4, "14", "20", "75"),
    (5, "7", "15", "60"), (6, "1", "2", "60"), (7, "0", "13", "20"),
    (8, "0", "11", "20"), (9, "0", "9", "20"), (10, "0", "6", "20"),
    (11, "0", "1", "20"), (12, "0", "0", "20"), (13, "0", "0", "0"),
])
def test_preview_reports_exact_first_match_at_boundaries(rules, no, s7, s15, s30):
    assert preview(rules, s7=s7, s15=s15, s30=s30)["result"]["matched_rule_no"] == no


@pytest.mark.parametrize("age", [None, "0"])
def test_missing_age_is_precheck_not_a_fabricated_match(rules, age):
    result = preview(rules, nature="新品", age=age)["result"]
    assert result["status"] == "missing_age"
    assert result["matched_rule_no"] is None
    assert result["value"] is None
    assert "未执行" in result["message"]


def test_preview_runtime_zero_division_stops_at_matched_rule(rules):
    rules[1]["formula_expr"] = "s30 / (s7 - s7)"
    result = preview(rules)["result"]
    assert result["status"] == "calculation_error"
    assert result["matched_rule_no"] == 2
    assert result["failed_rule_no"] == 2
    assert result["value"] is None
    assert "除以0" in result["message"]


def test_disabled_rules_and_no_match_are_explicit(rules):
    rules[1]["status"] = 0
    assert preview(rules)["result"]["matched_rule_no"] == 3
    for row in rules:
        row["status"] = 0
    assert preview(rules)["result"]["status"] == "unavailable"
    for row in rules:
        row.update(status=1, condition_expr="false")
    assert preview(rules)["result"]["status"] == "no_match"


def test_editor_loads_disabled_rules_and_returns_revision(rules, monkeypatch):
    rules[2]["status"] = 0
    monkeypatch.setattr(repo, "list_forecast_rule_rows", lambda: rules)
    result = service.list_forecast_rules()
    assert len(result["configs"]) == 13
    assert result["configs"][2]["status"] == 0
    assert len(result["revision"]) == 64
    old_revision = result["revision"]
    rules[2]["condition_expr"] = "true"
    assert repo.forecast_rules_revision(rules) != old_revision
    assert repo.forecast_rules_revision(list(reversed(rules))) == repo.forecast_rules_revision(rules)


class FakeConnection:
    def __init__(self, rows, fail=False):
        self.rows = deepcopy(rows)
        self.fail = fail
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def executemany(self, sql, params):
        self.calls.append((sql, params))
        if self.fail:
            raise RuntimeError("simulated write failure")

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize("mode", ["success", "stale", "missing", "failure"])
def test_save_transaction_is_update_only_with_revision_lock(rules, monkeypatch, mode):
    baseline = deepcopy(rules)
    revision = repo.forecast_rules_revision(baseline)
    if mode == "stale":
        baseline[1]["formula_expr"] = "777"
    if mode == "missing":
        baseline.pop()
    connection = FakeConnection(baseline, fail=mode == "failure")
    monkeypatch.setattr(repo, "db_connection", lambda: connection)
    rules[1]["formula_expr"] = "999"
    if mode == "success":
        repo.save_forecast_rules(rules, "tester", revision)
        assert connection.commits == 1 and connection.rollbacks == 0
        assert len(connection.calls[1][1]) == 13
        assert connection.calls[1][1][1]["formula_expr"] == "999"
        assert all(row["operator"] == "tester" for row in connection.calls[1][1])
    else:
        with pytest.raises((ValueError, RuntimeError)):
            repo.save_forecast_rules(rules, "tester", revision)
        assert connection.commits == 0 and connection.rollbacks == 1
    sql = " ".join(call[0].upper() for call in connection.calls)
    assert "FOR UPDATE" in sql
    assert "INSERT" not in sql and "DELETE" not in sql
    if mode in {"stale", "missing"}:
        assert len(connection.calls) == 1


def test_real_sku_inputs_use_exact_keys_and_global_anchor(monkeypatch):
    seen = []
    monkeypatch.setattr(repo, "forecast_sku_sales", lambda site, sku: (
        seen.append((site, sku)) or dict(site="英国", sku="ABC-001-YXR", sales_7d=0,
        sales_15d=9, sales_30d=58, anchor_date=date(2026, 8, 31))))
    monkeypatch.setattr(repo, "first_listing_date_by_sku",
                        lambda: {("ABC-001-YXR", "英国"): date.today() - timedelta(days=20)})
    monkeypatch.setattr(repo, "overseas_inventory_age_by_sku",
                        lambda: {("英国", "ABC-001-YXR"): Decimal(58), ("德国", "ABC-001-YXR"): Decimal(11)})
    data = service.forecast_sku_inputs(" 英国 ", " ABC-001-YXR ")
    assert seen == [("英国", "ABC-001-YXR")]
    assert data["sales_7d"] == "0"
    assert data["age_days"] == "58" and data["product_nature"] == "新品"
    assert data["anchor_date"] == date(2026, 8, 31)


def test_real_sku_query_does_not_use_fuzzy_search(monkeypatch):
    conn = FakeConnection([])
    monkeypatch.setattr(repo, "db_connection", lambda: conn)
    assert repo.forecast_sku_sales("英国", "ABC-001-YXR") is None
    sql, params = conn.calls[0]
    assert params == ("英国", "ABC-001-YXR")
    assert "LIKE" not in sql.upper()
    assert "recent.site_name=%s AND recent.inventory_sku=%s" in sql
    for days in (6, 14, 29):
        assert f"INTERVAL {days} DAY" in sql
    assert "INTERVAL 1 DAY" in sql
    assert "WHERE" not in sql.split(")")[0].upper()  # global anchor is not SKU-filtered


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_internal_access] = lambda: None

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "offline-test"
        return await call_next(request)

    with TestClient(app) as test_client:
        yield test_client


PREFIX = "/api/v1/finance/ebay-replenishment-v2/forecast-rule"


def test_api_rejects_invalid_save_without_writing(client, rules, monkeypatch):
    writes = []
    monkeypatch.setattr(repo, "save_forecast_rules", lambda *args: writes.append(args))
    rules[1]["condition_expr"] = "r5 > 0"
    response = client.post(PREFIX, json={"configs": rules, "revision": "a" * 64})
    assert response.status_code == 400
    assert "未知变量 r5" in response.json()["detail"]
    assert writes == []
    response = client.post(PREFIX + "/validate", json={"configs": rules})
    assert response.status_code == 200
    assert not response.json()["data"]["valid"]


def test_api_preview_decimal_text_without_persisting(client, rules):
    response = client.post(PREFIX + "/preview", json=dict(configs=rules,
        product_nature="老品", sales_7d="14", sales_15d="25", sales_30d="50"))
    assert response.status_code == 200
    assert response.json()["data"]["result"]["matched_rule_no"] == 2


def test_api_valid_save_preserves_operator_and_revision(client, rules, monkeypatch):
    writes = []
    monkeypatch.setattr(repo, "save_forecast_rules", lambda *args: writes.append(args))
    monkeypatch.setattr(repo, "list_forecast_rule_rows", lambda: rules)
    response = client.post(PREFIX, json={"configs": rules, "revision": "a" * 64, "operator": "tester"})
    assert response.status_code == 200
    assert writes[0][1:] == ("tester", "a" * 64)
    assert len(writes[0][0]) == 13


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "1e25"])
def test_api_rejects_unsafe_preview_inputs(client, rules, value):
    response = client.post(PREFIX + "/preview", json=dict(configs=rules,
        product_nature="老品", sales_7d=value, sales_15d="25", sales_30d="50"))
    assert response.status_code == 422


def test_all_new_python_endpoints_keep_internal_access_dependency():
    routes = [route for route in api.router.routes if "/forecast-rule" in route.path]
    assert len(routes) == 5
    assert all(any(dep.call is api.require_internal_access for dep in route.dependant.dependencies)
               for route in routes)


def test_all_five_java_routes_are_permission_guarded_and_operator_is_server_owned():
    path = ROOT / "RuoYi-Vue-springboot3/ruoyi-admin/src/main/java/com/ruoyi/web/controller/operation/EbayReplenishmentV2Controller.java"
    source = path.read_text(encoding="utf-8")
    for name in ("forecastRules", "saveForecastRules", "validateForecastRules", "previewForecastRules", "forecastRuleSku"):
        before = source.split("public AjaxResult " + name + "(")[0].rsplit("    }", 1)[-1]
        assert "@PreAuthorize(\"@ss.hasPermi('operations:ebayReplenishmentV2:formula')\")" in before
    method = source.split("public AjaxResult saveForecastRules(")[1].split("    }", 1)[0]
    assert 'payload.put("operator", getUsername())' in method
