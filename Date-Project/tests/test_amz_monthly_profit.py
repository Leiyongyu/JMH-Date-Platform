"""AMZ 月度利润表：拉取解析（途损、自定义费用、币种、合并、核对）、报表口径、补充费用、导出、接口与调度注册。"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import require_internal_access
from backend.api.v1 import amz_monthly_profit as api
from backend.config import PROJECT_ROOT
from backend.services import amz_monthly_profit_service as service
from backend.services import amz_monthly_profit_sync_service as sync
from backend.services import inventory_report_etl_service as inventory
from backend.services import scheduler_service
from backend.sql_statements import split_sql_statements

MIGRATION = PROJECT_ROOT / "migrations" / "20261111_amz_monthly_profit.sql"
RULES = inventory._amazon_rule_maps([])


def record(**overrides):
    base = {
        "sid": "100", "msku": "M-1", "storeName": "EU-伶斯勋-DE", "localSku": "DAS-1-1", "localName": "n",
        "currencyCode": "CNY", "totalSalesQuantity": 10, "refundsQuantity": 1, "fbaReturnsQuantity": 2,
        "totalSalesAmount": 1000, "shippingCredits": 50, "promotionalRebates": -20, "fbaInventoryCredit": 10,
        "otherInAmount": 5, "totalSalesRefunds": -100, "totalFeeRefunds": 15, "platformFee": -150,
        "totalFbaDeliveryFee": -200, "totalAdsCost": -80, "totalStorageFee": -30, "cgPriceTotal": -300,
        "cgTransportCostsTotal": -40, "grossProfit": 160,
        "otherFeeStr": [{"otherFeeName": "仓库费用", "feeAllocation": -5},
                        {"otherFeeName": "仓库费用", "feeAllocation": -1},
                        {"otherFeeName": "店租费（法人补贴等）", "feeAllocation": -2}],
        "cgPriceDetails": '[{"202":{"quantity":-1,"amount":-300.0}},{"226":{"quantity":-1,"amount":-20.5}}]',
        "cgTransportCostsDetails": '[{"226":{"quantity":-1,"amount":-3.5},"11":{"quantity":1,"amount":1}}]',
        "cgOtherCostsDetails": "",
    }
    base.update(overrides)
    return base


COMMON = {"stat_month": "2026-09", "sync_batch_id": "b", "pulled_at": None}


# ----------------------------------------------------------- 拉取解析
def test_transit_loss_sums_codes_226_and_11_in_both_detail_formats():
    assert sync.transit_loss(record()) == Decimal("-23.0")
    mcp_style = '{"202":{"amount":-5}},,{"226":{"amount":-2.25}},,{"11":{"amount":0.25}},,null'
    assert sync.transit_loss({"cgPriceDetails": mcp_style}) == Decimal("-2.00")
    assert sync.transit_loss({"cgPriceDetails": "not json", "cgOtherCostsDetails": None}) == 0


def test_msku_row_maps_fields_and_sums_custom_fees_by_name():
    row = sync.msku_row(record(), COMMON)
    assert (row["sid"], row["msku"], row["store_name"]) == ("100", "M-1", "EU-伶斯勋-DE")
    assert row["sales_qty"] == 10 and row["fba_delivery_fee"] == Decimal("-200")
    assert row["other_fees"] == {"仓库费用": "-6", "店租费（法人补贴等）": "-2"}
    assert row["transit_loss"] == Decimal("-23.0")
    with pytest.raises(ValueError, match="币种 USD"):
        sync.msku_row(record(currencyCode="USD"), COMMON)
    with pytest.raises(ValueError, match="缺少 sid"):
        sync.msku_row(record(sid=""), COMMON)


def test_merge_and_reconcile():
    rows = sync.merge_msku([sync.msku_row(record(), COMMON), sync.msku_row(record(), COMMON)])
    assert len(rows) == 1 and rows[0]["sales_qty"] == 20 and rows[0]["other_fees"]["仓库费用"] == "-12"
    seller = [{"sid": "100", "store_name": "EU-伶斯勋-DE", "sales_qty": 20, "sales_amount": Decimal("2000")}]
    assert sync.reconcile(rows, seller) == []
    seller[0]["sales_qty"] = 19
    assert sync.reconcile(rows, seller)[0]["seller_qty"] == 19


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def post_signed_query_auth(self, path, body):
        self.calls.append((path, body))
        data = self.pages[path]
        return {"code": 0, "data": {"records": data if body["offset"] == 0 else [], "total": len(data)}}


def test_sync_pulls_cny_monthly_summaries_and_replaces_month():
    client = FakeClient({sync.SELLER_PATH: [{"sid": "100", "storeName": "EU-伶斯勋-DE", "totalSalesQuantity": 10,
                                              "totalSalesAmount": 1000, "grossProfit": 160, "currencyCode": "CNY"}],
                         sync.MSKU_PATH: [record()]})
    stored = {}

    def replace(month, msku, seller):
        stored.update(month=month, msku=msku, seller=seller)
        return {"msku_rows": len(msku), "seller_rows": len(seller), "deleted_rows": 0}

    result = sync.sync_amz_monthly_profit("2026-09", client=client, sleep=lambda _: None, replace=replace)
    assert stored["month"] == "2026-09" and len(stored["msku"]) == 1
    assert result["status"] == "completed" and result["reconcile_diff_stores"] == []
    assert result["extract_rows"] == 2 and result["ods_rows"] == 2
    bodies = {path: body for path, body in client.calls}
    for path in (sync.SELLER_PATH, sync.MSKU_PATH):
        assert bodies[path]["currencyCode"] == "CNY" and bodies[path]["monthlyQuery"] is True
        assert bodies[path]["summaryEnabled"] is True and bodies[path]["startDate"] == "2026-09"


def test_sync_refuses_empty_pull_without_replacing():
    client = FakeClient({sync.SELLER_PATH: [], sync.MSKU_PATH: []})
    replaced = []
    with pytest.raises(sync.AmzMonthlyProfitSyncError, match="未返回") as error:
        sync.sync_amz_monthly_profit("2026-09", client=client, sleep=lambda _: None,
                                     replace=lambda *args: replaced.append(args))
    assert error.value.stage == "TRANSFORM" and replaced == []


# ----------------------------------------------------------- 报表口径
def stored(store, msku="M-1", sid="100", **values):
    row = sync.msku_row(record(storeName=store, msku=msku, sid=sid), COMMON)
    row.update(values)
    return row


def build(rows, adjustments=()):
    return service.build_report("2026-09", rows, shops={}, rules=RULES, adjustments=list(adjustments))


def test_store_rows_follow_the_exclusion_and_group_rules():
    report = build([
        stored("EU-伶斯勋-DE"), stored("EU-伶斯勋-FR", sid="101"),
        stored("US2-斯鑫雅-US", sid="12518"),                  # 关停店铺
        stored("US3-优贝诺-US", sid="102", msku="ABC-1"),       # 优贝诺只留含 zmy/dsq 的 MSKU
        stored("US3-优贝诺-US", sid="102", msku="DSQ-1"),
        stored("US3-新志楠-US", sid="103"),                     # MJ
        stored("信博嘉立-DE", sid="104"),                        # 非部门
    ])
    keys = [(row["group_code"], row["subteam_code"], row["store_name"]) for row in report["store_rows"]]
    assert keys == [("EU", None, "伶斯勋"), ("US3", "MJ", "新志楠"), ("US3", "ZXY", "优贝诺")]
    eu = report["store_rows"][0]
    assert eu["sales_qty"] == 20 and eu["warehouse_fee"] == Decimal("-12.00")
    assert report["excluded"]["excluded_shop"] == 1 and report["excluded"]["excluded_special_msku"] == 1
    assert report["excluded"]["unmatched_department"] == 1


def test_final_profit_and_ratios_use_the_finance_sheet_formulas():
    row = build([stored("EU-伶斯勋-DE")])["store_rows"][0]
    # 最终毛利 = 毛利润 − 途损抵扣（-23）= 183
    assert row["final_profit"] == Decimal("183.00")
    margin_base = Decimal(1000 + 50 - 20 + 10 + 5 - 100 + 15)
    assert row["gross_margin"] == (Decimal(183) / margin_base).quantize(service.RATE)
    share_base = Decimal(1000 + 50 - 20 + 10 + 5)
    assert row["platform_fee_ratio"] == (Decimal(-150) / share_base).quantize(service.RATE)
    assert row["refund_rate"] == Decimal("0.100000") and row["return_rate"] == Decimal("0.200000")
    empty = build([stored("EU-伶斯勋-DE", sales_qty=0, refunds_qty=0, sales_amount=Decimal(0),
                          shipping_credits=Decimal(0), promotional_rebates=Decimal(0),
                          fba_inventory_credit=Decimal(0), other_in_amount=Decimal(0),
                          sales_refunds=Decimal(0), fee_refunds=Decimal(0))])["store_rows"][0]
    assert empty["gross_margin"] is None and empty["refund_rate"] is None, "分母为 0 返回 None，不当 0"


def test_group_rows_split_us3_and_apply_adjustments_to_leaf_rows():
    report = build([stored("EU-伶斯勋-DE"), stored("US3-富琳顿-US", sid="103"), stored("US3-睿启君-US", sid="105")],
                   adjustments=[
                       {"row_code": "MJ", "fee_item": "warehouse_fee", "amount": Decimal("-100")},
                       {"row_code": "ZXY", "fee_item": "supplement_fee", "amount": Decimal("50")},
                       {"row_code": "US3", "fee_item": "warehouse_fee", "amount": Decimal("-999")},  # 非末级行忽略
                   ])
    rows = {row["row_code"]: row for row in report["group_rows"]}
    assert [row["row_code"] for row in report["group_rows"]] == ["EU", "US3", "MJ", "ZXY"]
    assert rows["MJ"]["warehouse_fee"] == Decimal("-106.00") and rows["MJ"]["final_profit"] == Decimal("83.00")
    assert rows["ZXY"]["supplement_fee"] == Decimal("50.00") and rows["ZXY"]["final_profit"] == Decimal("233.00")
    assert rows["US3"]["final_profit"] == Decimal("316.00"), "US3 = MJ + ZXY，含两边的补充费用"
    assert report["group_total"]["final_profit"] == Decimal("499.00")
    assert report["adjustment_count"] == 2


def test_unknown_custom_fee_names_are_reported():
    row = stored("EU-伶斯勋-DE")
    row["other_fees"] = {**row["other_fees"], "新费用": "-9"}
    assert "新费用 -9.00" in build([row])["notices"][0]


def test_adjustment_payload_validation():
    with pytest.raises(ValueError, match="末级行"):
        service._adjustment_payload("2026-09", {"row_code": "US3", "fee_item": "warehouse_fee", "amount": 1}, "u")
    with pytest.raises(ValueError, match="费用列"):
        service._adjustment_payload("2026-09", {"row_code": "MJ", "fee_item": "ads_cost", "amount": 1}, "u")
    with pytest.raises(ValueError, match="金额"):
        service._adjustment_payload("2026-09", {"row_code": "MJ", "fee_item": "warehouse_fee", "amount": "x"}, "u")
    with pytest.raises(ValueError, match="不能为 0"):
        service._adjustment_payload("2026-09", {"row_code": "MJ", "fee_item": "warehouse_fee", "amount": 0}, "u")
    row = service._adjustment_payload("2026-09", {"row_code": "MJ", "fee_item": "supplement_fee",
                                                  "amount": "-5766.425", "remark": " 仓租分摊 "}, "admin")
    assert row == {"stat_month": "2026-09", "row_code": "MJ", "fee_item": "supplement_fee",
                   "amount": Decimal("-5766.43"), "remark": "仓租分摊", "operator": "admin"}


def test_report_requires_a_pulled_month(monkeypatch):
    monkeypatch.setattr(service.repo, "msku_rows", lambda month: [])
    with pytest.raises(ValueError, match="还没有拉取"):
        service.get_report("2026-09")
    with pytest.raises(ValueError, match="YYYY-MM"):
        service.get_report("2026/09")


def test_export_has_both_sheets_with_finance_headers(monkeypatch):
    from openpyxl import load_workbook

    report = build([stored("EU-伶斯勋-DE"), stored("US3-富琳顿-US", sid="103")])
    report.update(pulled_at="2026-10-07 06:00:00", notices=[])
    monkeypatch.setattr(service, "get_report", lambda month: report)
    name, content = service.export_report("2026-09")
    assert name == "AMZ月度利润表-2026-09.xlsx"
    workbook = load_workbook(BytesIO(content))
    assert workbook.sheetnames == ["店铺利润-CNY", "小组利润-CNY", "说明"]
    store_head = [cell.value for cell in workbook["店铺利润-CNY"][1]]
    assert store_head[:4] == ["日期", "组别", "店铺名", "销量"] and "FBA途损" in store_head and "最终毛利" in store_head
    group_head = [cell.value for cell in workbook["小组利润-CNY"][1]]
    assert "补充费用" in group_head and "FBA途损抵扣" in group_head
    assert workbook["店铺利润-CNY"].cell(2, 1).value == "2026-09-01~2026-09-30"
    assert workbook["小组利润-CNY"].cell(workbook["小组利润-CNY"].max_row, 1).value == "总计"


# ----------------------------------------------------------- 接口、调度、迁移
@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


def test_api_routes(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "get_report", lambda month: seen.setdefault("report", month) and {"ok": 1})
    monkeypatch.setattr(service, "create_adjustment", lambda payload, operator: seen.update(created=(payload, operator)) or {"id": 7})
    monkeypatch.setattr(service, "delete_adjustment", lambda adjustment_id: seen.update(deleted=adjustment_id) or {"id": adjustment_id})
    assert client.get("/api/v1/finance/amz-monthly-profit/report", params={"stat_month": "2026-09"}).status_code == 200
    assert seen["report"] == "2026-09"
    assert client.get("/api/v1/finance/amz-monthly-profit/report", params={"stat_month": "2026-13"}).status_code == 422
    body = {"stat_month": "2026-09", "row_code": "MJ", "fee_item": "warehouse_fee", "amount": -1, "operator": "admin"}
    assert client.post("/api/v1/finance/amz-monthly-profit/adjustments", json=body).json()["data"] == {"id": 7}
    assert seen["created"][1] == "admin"
    assert client.delete("/api/v1/finance/amz-monthly-profit/adjustments/7").status_code == 200
    assert seen["deleted"] == 7

    def bad(month):
        raise ValueError("2026-09 还没有拉取")

    monkeypatch.setattr(service, "get_report", bad)
    response = client.get("/api/v1/finance/amz-monthly-profit/report", params={"stat_month": "2026-09"})
    assert response.status_code == 400 and "还没有拉取" in response.json()["detail"]


def test_scheduler_registers_the_monthly_task():
    spec = scheduler_service.TASK_SPECS["amz_monthly_profit_sync"]
    assert spec.name == "AMZ月度利润表数据拉取" and spec.default_previous_month is True
    assert spec.lock_name(type("Ctx", (), {"month": "2026-09"})()) == "lingxing:amz-monthly-profit:2026-09"
    assert sync.AmzMonthlyProfitSyncError in scheduler_service._STAGED_ERRORS


def test_migration_is_ascii_idempotent_and_creates_the_tables():
    raw = MIGRATION.read_bytes()
    sql = raw.decode("ascii")
    statements = [" ".join(line for line in item.splitlines() if not line.strip().startswith("--")).strip()
                  for item in split_sql_statements(sql)]
    statements = [item for item in statements if item]
    assert statements[0] == "USE `date-project`" and statements[1] == "SET NAMES utf8mb4"
    for table in ("ods_lingxing_profit_report_msku_month", "ods_lingxing_profit_report_seller_month",
                  "fin_amz_monthly_profit_adjustment"):
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in sql
    upper = sql.upper()
    for forbidden in ("DROP ", "TRUNCATE", "DELETE ", "ALTER "):
        assert forbidden not in upper
    assert "ON DUPLICATE KEY UPDATE" in sql and "'amz_monthly_profit_sync'" in sql
    for column in service.repo.MSKU_COLUMNS:
        if column != "other_fees_json":
            assert f"`{column}`" in sql, column


def test_insert_only_binds_table_columns():
    """pymysql 会转义参数字典里的所有值：行里带的 other_fees（dict）不能传给 executemany。"""
    from backend.repositories import amz_monthly_profit_repository as repo

    class Cursor:
        def __init__(self):
            self.batches = []

        def executemany(self, sql, rows):
            self.batches.append(rows)

    cursor = Cursor()
    row = {**sync.msku_row(record(), COMMON), "other_fees_json": "{}"}
    assert isinstance(row["other_fees"], dict)
    assert repo._insert(cursor, repo.MSKU_TABLE, repo.MSKU_COLUMNS, [row]) == 1
    sent = cursor.batches[0][0]
    assert list(sent) == list(repo.MSKU_COLUMNS) and "other_fees" not in sent
