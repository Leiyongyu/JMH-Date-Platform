"""eBay 月度利润表：交易归类与拆行、谷仓账单解析、报表计算、接口与调度注册。全部不连真实数据库与外部接口。"""
from __future__ import annotations

import base64
import io
import zipfile
from datetime import datetime, timezone
from decimal import Decimal as D

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api.deps import require_internal_access
from backend.api.v1 import ebay_monthly_profit as api
from backend.repositories import ebay_monthly_profit_repository as repo
from backend.services import ebay_finance_sync_service as fs
from backend.services import ebay_monthly_profit_service as svc
from backend.services import goodcang_bill_sync_service as gb
from backend.services import scheduler_service

MONTH = "2026-10"


def tx(**overrides):
    base = {"transactionId": "T1", "transactionType": "SALE", "bookingEntry": "CREDIT", "transactionStatus": "PAYOUT",
            "transactionDate": "2026-10-10T10:00:00.000Z", "amount": {"value": "40.64", "currency": "USD"}}
    base.update(overrides)
    return base


# ------------------------------------------------------------ 归类
@pytest.mark.parametrize("payload,expected", [
    (tx(), "ORDER"),
    (tx(transactionType="REFUND", references=[{"referenceType": "RETURN_ID", "referenceId": "1"}]), "REFUND"),
    (tx(transactionType="REFUND", references=[{"referenceType": "CANCELLATION_ID", "referenceId": "1"}]), "REFUND"),
    (tx(transactionType="REFUND", references=[{"referenceType": "CASE_ID", "referenceId": "1"}]), "CLAIM"),
    (tx(transactionType="REFUND", references=[{"referenceType": "PAYMENTS_DISPUTE_ID", "referenceId": "1"}]), "PAYMENT_DISPUTE"),
    (tx(transactionType="DISPUTE"), "HOLD"),
    (tx(transactionType="CREDIT", references=[{"referenceType": "CASE_ID", "referenceId": "1"}]), "HOLD"),
    (tx(transactionType="CREDIT"), "CLAIM"),
    (tx(transactionType="NON_SALE_CHARGE", feeType="AD_FEE", transactionMemo="Promoted Listings - General fee"), "AD_FEE"),
    (tx(transactionType="NON_SALE_CHARGE", feeType="OTHER_FEES", transactionMemo="Promoted Offsite fee"), "AD_FEE"),
    (tx(transactionType="NON_SALE_CHARGE", feeType="FINAL_VALUE_FEE", transactionMemo="Final Value Fee"), "AD_FEE"),
    # 店铺订阅费：描述是日期区间，不含广告关键词 → 刊登 / 副标题（与手工表一致）
    (tx(transactionType="NON_SALE_CHARGE", feeType="OTHER_FEES", transactionMemo="2026-09-30 - 2026-10-30"), "LISTING_FEE"),
    (tx(transactionType="NON_SALE_CHARGE", feeType="INSERTION_FEE", transactionMemo="Insertion Fee"), "LISTING_FEE"),
    (tx(transactionType="NON_SALE_CHARGE", feeType="PREMIUM_AD_FEES"), "AD_FEE"),
    (tx(transactionType="SHIPPING_LABEL"), "SHIPPING_LABEL"),
    (tx(transactionType="ADJUSTMENT"), "ADJUSTMENT"),
    (tx(transactionType="TRANSFER"), "OTHER"),
])
def test_classify_matches_the_seller_hub_report_types(payload, expected):
    assert fs.classify(payload) == expected


def test_month_window_follows_pacific_time_including_dst():
    start, end = fs.month_window("2026-10")
    assert start == datetime(2026, 10, 1, 7, tzinfo=timezone.utc)   # PDT
    assert end == datetime(2026, 11, 1, 7, tzinfo=timezone.utc)     # 11-01 00:00 PDT
    start, end = fs.month_window("2026-11")
    assert end == datetime(2026, 12, 1, 8, tzinfo=timezone.utc)     # PST


# ------------------------------------------------------------ 拆行与金额
def test_single_line_sale_gross_is_net_plus_fees_without_tax():
    sale = tx(orderId="12-1", totalFeeBasisAmount={"value": "48.0", "currency": "USD"},
              totalFeeAmount={"value": "7.36", "currency": "USD"},
              ebayCollectedTaxAmount={"value": "3.36", "currency": "USD"},
              orderLineItems=[{"lineItemId": "L1", "feeBasisAmount": {"value": "48.0", "currency": "USD"},
                               "marketplaceFees": [
                                   {"feeType": "FINAL_VALUE_FEE_FIXED_PER_ORDER", "amount": {"value": "0.4"}},
                                   {"feeType": "FINAL_VALUE_FEE", "amount": {"value": "6.29"}},
                                   {"feeType": "INTERNATIONAL_FEE", "amount": {"value": "0.67"}}]}])
    order = {"lineItems": [{"lineItemId": "L1", "sku": "TYT-90223-0190", "title": "Carburetor", "quantity": 1,
                            "legacyItemId": "377343559771"}]}
    rows = fs.normalize("S", sale, {"12-1": order}, {}, MONTH)
    assert len(rows) == 1
    row = rows[0]
    assert row["category"] == "ORDER" and row["sku"] == "TYT-90223-0190" and row["item_id"] == "377343559771"
    assert row["gross_amount"] == D("48.0000")
    assert (row["fvf_fixed"], row["fvf_variable"], row["international_fee"]) == (D("-0.4"), D("-6.29"), D("-0.67"))
    assert row["net_amount"] == D("40.64")


def test_eu_sale_gross_excludes_vat_and_converts_with_the_ebay_rate():
    # 欧洲站计费基数含增值税（100 = 84.03 + 15.97），毛额要用 净额 + 费用 倒推，不能直接用计费基数。
    sale = tx(orderId="O", amount={"value": "85.43", "currency": "USD", "convertedFromCurrency": "EUR",
                                   "convertedFromValue": "73.65"},
              orderLineItems=[{"lineItemId": "A", "feeBasisAmount": {"value": "60"},
                               "marketplaceFees": [{"feeType": "FINAL_VALUE_FEE", "amount": {"value": "6"}}]},
                              {"lineItemId": "B", "feeBasisAmount": {"value": "40"},
                               "marketplaceFees": [{"feeType": "FINAL_VALUE_FEE", "amount": {"value": "4.38"}}]}])
    rows = fs.normalize("S", sale, {}, {}, MONTH)
    assert [row["line_no"] for row in rows] == [1, 2]
    assert rows[0]["tx_currency"] == "EUR"
    assert sum(row["gross_amount"] for row in rows) == D("73.65") + D("10.38")
    assert rows[0]["gross_amount"] == D("50.4180")  # 84.03 × 60%
    assert sum(row["net_amount"] for row in rows) == D("85.43"), "各行净额合计严格等于交易净额"


def test_refund_signs_mirror_the_report_and_fees_come_back_positive():
    refund = tx(transactionType="REFUND", bookingEntry="DEBIT", orderId="11-1",
                amount={"value": "110.49", "currency": "USD"},
                references=[{"referenceType": "RETURN_ID", "referenceId": "5331557000"}],
                orderLineItems=[{"lineItemId": "L", "feeBasisAmount": {"value": "129.19"},
                                 "marketplaceFees": [{"feeType": "FINAL_VALUE_FEE_FIXED_PER_ORDER", "amount": {"value": "0.4"}},
                                                     {"feeType": "FINAL_VALUE_FEE", "amount": {"value": "16.98"}},
                                                     {"feeType": "INTERNATIONAL_FEE", "amount": {"value": "1.32"}}]}])
    row = fs.normalize("S", refund, {}, {}, MONTH)[0]
    assert row["category"] == "REFUND" and row["net_amount"] == D("-110.49")
    assert row["gross_amount"] == D("-129.19")
    assert row["fvf_variable"] == D("16.98") and row["fvf_fixed"] == D("0.4")
    assert "RETURN_ID:5331557000" in row["reference_text"]


def test_fee_row_takes_sku_from_the_listing_map_and_converts_back_to_tx_currency():
    fee = tx(transactionType="NON_SALE_CHARGE", bookingEntry="DEBIT", feeType="INSERTION_FEE",
             transactionMemo="Insertion Fee", amount={"value": "0.41", "currency": "USD",
                                                       "convertedFromCurrency": "GBP", "convertedFromValue": "0.30"},
             references=[{"referenceType": "ITEM_ID", "referenceId": "376907815738"}])
    row = fs.normalize("S", fee, {}, {"376907815738": "BMW-1-1"}, MONTH)[0]
    assert (row["category"], row["sku"], row["tx_currency"]) == ("LISTING_FEE", "BMW-1-1", "GBP")
    assert row["net_amount"] == D("-0.41") and row["gross_amount"] == D("-0.3000")


# ------------------------------------------------------------ 谷仓账单
def _bill_xlsx():
    wb = Workbook()
    wb.active.title = "账单说明"
    ws = wb.create_sheet("订单费用明细")
    ws.append(["业务类型", "业务单号", "关联单号", "跟踪号", "仓库代码", "SKU", "平台", "计费时间", "费用类型", "费用明细",
               "本期费用小计", "币种", "备注"])
    ws.append(["标准订单", "G-1", "17-15218-03700", "H05", "UK", "JMH-30477-0740*1", "EBAY", "2026-10-01 02:43:57",
               "运费", "运输费", 1.93, "GBP", ""])
    ws.append(["标准订单", "G-2", "A-1", "T", "USEA", "JMH-1-1*2", "AMAZON", "2026-10-01", "运费", "运输费", 3, "USD", ""])
    ws = wb.create_sheet("仓租费用明细")
    ws.append(["业务类型", "业务单号", "仓库代码", "费用类型", "费用明细", "本期费用小计", "币种"])
    ws.append(["仓租单", "WTG-USWE", "USWE", "仓租费", "仓储费", 4.39, "USD"])
    ws = wb.create_sheet("理赔及返还费用明细")
    ws.append(["业务类型", "业务单号", "关联单号", "仓库代码", "费用类型", "费用明细", "本期费用小计", "币种", "备注"])
    ws.append(["标准索赔", "CL-1", "G10645-261006-0243", "USWE", "货值赔偿", "运输费", -8.19, "USD",
               "错发货：出库单号：G10645-261006-0243：错发货明细：JMH-20049-0056*1"])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_parse_bill_maps_sheets_platform_amounts_and_claim_sku():
    rows = gb.parse_bill(_bill_xlsx(), {"bill_number": "B1", "account_code": "ACG1064502"}, MONTH)
    by_no = {row["business_no"]: row for row in rows}
    assert by_no["G-1"]["fee_type"] == "出库费用" and by_no["G-1"]["platform"] == "EBAY"
    assert by_no["G-1"]["amount"] == D("1.93") and by_no["G-1"]["related_no"] == "17-15218-03700"
    assert by_no["G-2"]["platform"] == "AMAZON"
    assert by_no["WTG-USWE"]["fee_type"] == "仓储费" and by_no["WTG-USWE"]["platform"] == "EBAY"
    assert by_no["CL-1"]["fee_type"] == "理赔及返还" and by_no["CL-1"]["sku"] == "JMH-20049-0056*1"
    assert by_no["CL-1"]["amount"] == D("-8.19")


def test_unpack_handles_single_xlsx_and_zip_of_bills():
    xlsx = _bill_xlsx()
    bills = [{"bill_number": "B20261015G106450002"}, {"bill_number": "B20261101G106450002"}]
    assert gb.unpack(xlsx, bills[:1]) == {"B20261015G106450002": xlsx}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("B20261015G106450002-2026-10-01至2026-10-14.xlsx", b"a")
        archive.writestr("B20261101G106450002-2026-10-15至2026-10-31.xlsx", b"b")
    assert gb.unpack(buffer.getvalue(), bills) == {"B20261015G106450002": b"a", "B20261101G106450002": b"b"}


def test_bill_sync_lists_month_bills_and_replaces_the_month(monkeypatch):
    class Client:
        def __init__(self):
            self.http = type("H", (), {"close": lambda self: None})()
            self.exported = None

        def fetch_bill_page(self, begin, end, page, account_code=""):
            assert (begin, end) == ("2026-10-01 00:00:00", "2026-10-31 23:59:59")
            return {"code": 0, "data": {"total": 2, "list": [
                {"bill_number": "B1", "account_code": "ACG1064502", "bill_to_time": "2026-10-14 23:59:59"},
                {"bill_number": "X", "account_code": "OTHER", "bill_to_time": "2026-10-31 23:59:59"}]}}

        def export_bills(self, numbers):
            self.exported = numbers
            return {"code": 0, "data": base64.b64encode(_bill_xlsx()).decode()}

    written = {}
    monkeypatch.setattr(repo, "replace_bill_rows", lambda month, rows, **kw: written.update(month=month, rows=rows) or len(rows))
    client = Client()
    result = gb.sync_goodcang_bills(MONTH, client=client)
    assert client.exported == ["B1"], "只取 eBay 账户的账单"
    assert written["month"] == MONTH and result["ods_rows"] == len(written["rows"]) == 4
    assert result["bills"] == ["B1"]


# ------------------------------------------------------------ 订单成本规则
def test_order_costs_dedupe_repeated_lines_like_the_finance_sheet(monkeypatch):
    rows = [
        # 订单行数量 4，同一行被拆成 4 行重复列出 → 只算一次；头程每行重复 → 取一次
        *({"platform_order_no": "04-1", "inventory_sku": "VLV-1", "platform_sku_quantity": D(4),
           "purchase_cost_cny": D("2720"), "first_mile_shipping_cny": D("112.52")} for _ in range(4)),
        # 订单行数量 1、买家拍了两次同一商品 → 逐行相加
        *({"platform_order_no": "01-1", "inventory_sku": "DAS-1", "platform_sku_quantity": D(1),
           "purchase_cost_cny": D("15.741"), "first_mile_shipping_cny": D("8.2")} for _ in range(2)),
        # 不同 SKU 各自相加
        {"platform_order_no": "01-2", "inventory_sku": "A", "platform_sku_quantity": D(1),
         "purchase_cost_cny": D("90"), "first_mile_shipping_cny": D("13.41")},
        {"platform_order_no": "01-2", "inventory_sku": "B", "platform_sku_quantity": D(1),
         "purchase_cost_cny": D("14.5"), "first_mile_shipping_cny": D("13.41")},
    ]
    monkeypatch.setattr(repo, "_query", lambda sql, params=(): rows)
    costs = repo.order_costs(MONTH)
    assert costs["04-1"] == (D("2720"), D("112.52"))
    assert costs["01-1"] == (D("31.482"), D("8.2"))
    assert costs["01-2"] == (D("104.5"), D("13.41"))


# ------------------------------------------------------------ 报表
def frow(store="S1", category="ORDER", currency="USD", sku="TYT-1-1", net="100", gross="120", fx="1", order="O1",
         **fees):
    return {"store_name": store, "category": category, "tx_currency": currency, "sku": sku, "net_amount": D(net),
            "gross_amount": D(gross), "fx_rate": D(fx), "order_id": order, **{k: D(v) for k, v in fees.items()}}


RATES = {"USD": D("7"), "EUR": D("8"), "GBP": D("9")}
OWNERS = {"TYT-1-1": "甲", "BMW-1-1": "乙"}


def build(rows, **kw):
    params = dict(rates=RATES, owner_of=lambda sku: OWNERS.get(sku, "未分配"), costs={}, bills=[], storage=[],
                  age={}, adjustments=[], owners=["甲", "乙"])
    params.update(kw)
    return svc.build_report(MONTH, rows, **params)


def site(report, code):
    return next(row for row in [*report["site_rows"], report["site_total"]] if row["row_code"] == code)


def owner(report, name):
    return next(row for row in [*report["owner_rows"], report["owner_total"]] if row["row_code"] == name)


def test_us_rows_are_not_double_counted_and_eu_is_de_plus_uk():
    rows = [frow(), frow(currency="EUR", sku="BMW-1-1", net="10", gross="12", fx="1.1", order="O2"),
            frow(currency="GBP", sku="BMW-1-1", net="20", gross="15", fx="1.3", order="O3")]
    report = build(rows)
    assert site(report, "US")["platform_income"] == D("840.00")          # 120 × 1 × 7
    assert site(report, "DE")["platform_income"] == D("92.40")           # 12 × 1.1 × 7
    assert site(report, "UK")["platform_income"] == D("136.50")          # 15 × 1.3 × 7
    assert site(report, "EU")["platform_income"] == D("228.90")
    assert site(report, "TOTAL")["platform_income"] == D("1068.90")
    assert site(report, "US")["platform_net"] == D("700.00")


def test_fees_penalty_ads_and_other_columns_and_tax_risk():
    rows = [frow(fvf_fixed="-0.4", fvf_variable="-6", international_fee="-0.6", inad_fee="-1"),
            frow(category="AD_FEE", gross="-2", net="-2", order=None),
            frow(category="LISTING_FEE", gross="-0.35", net="-0.35", order=None),
            frow(category="HOLD", gross="-10", net="-10", order=None)]
    us = site(build(rows), "US")
    assert us["platform_expense"] == D("-7") * 7 + D("-1") * 7 + D("-2") * 7 + D("-2.45") + D("-70")
    assert us["tax_risk"] == -us["platform_income"] * D("0.01")


def test_adjustment_rows_follow_the_store_main_site():
    rows = [frow(store="S", currency="EUR", sku="BMW-1-1", gross="100", net="80"),
            frow(store="S", category="ADJUSTMENT", currency="USD", gross="-5", net="-5", order=None, sku=None)]
    report = build(rows)
    assert site(report, "DE")["platform_expense"] == D("-35.00")
    assert site(report, "US")["platform_expense"] == D("0.00")


def test_costs_bills_storage_and_owner_allocation():
    rows = [frow(sku="TYT-1-1", net="100", gross="100", order="A"),
            frow(sku="BMW-1-1", net="300", gross="300", order="B"),
            frow(category="AD_FEE", sku=None, gross="-40", net="-40", order=None)]
    bills = [{"platform": "EBAY", "currency": "USD", "amount": D("10"), "fee_type": "出库费用", "sku": "TYT-1-1*1",
              "related_no": "A"},
             {"platform": "EBAY", "currency": "USD", "amount": D("4"), "fee_type": "仓储费", "sku": None},
             {"platform": "AMAZON", "currency": "USD", "amount": D("99"), "fee_type": "出库费用", "sku": None}]
    storage = [{"product_sku": "TYT-1-1", "currency": "USD", "amount": D("1")}]
    report = build(rows, costs={"A": (D("50"), D("5")), "B": (D("100"), None)}, bills=bills, storage=storage)
    us = site(report, "US")
    assert us["purchase_cost"] == D("-150.00") and us["first_leg_cost"] == D("-5.00")
    assert us["tail_fee"] == D("-70.00") and us["storage_fee"] == D("-28.00"), "非 eBay 平台的账单行不计入"
    a, b = owner(report, "甲"), owner(report, "乙")
    # 仓储：甲按明细 7 元，差额 21 元两人平均 → 甲 17.5、乙 10.5
    assert (a["storage_fee"], b["storage_fee"]) == (D("-17.50"), D("-10.50"))
    # 没有 SKU 的广告费 -280 按收入占比 1:3 分摊
    assert (a["ads"], b["ads"]) == (D("-70.00"), D("-210.00"))
    assert owner(report, "TOTAL")["platform_net"] == us["platform_net"]
    store = report["store_rows"][0]
    assert store["tail_fee"] == D("-70.00") and store["order_count"] == 2


def test_manual_adjustments_split_by_rule_and_profit_formula():
    rows = [frow(net="1000", gross="1000"), frow(currency="EUR", sku="BMW-1-1", net="1000", gross="1000", order="B")]
    adjustments = [{"fee_item": "store_operation", "row_code": "ALL", "amount": "-400"},
                   {"fee_item": "gu_destruction", "row_code": "ALL", "amount": "-300"},
                   {"fee_item": "points", "row_code": "DE", "amount": "50"},
                   {"fee_item": "points", "row_code": "甲", "amount": "20"},
                   {"fee_item": "points", "row_code": "ALL", "amount": "999"}]  # 积分不允许记总额，忽略
    age = {"site": {"US": {"over_90_180": D("3600"), "over_180": D("0"), "ctu_30": D("0")}},
           "owner": {"甲": {"over_180": D("1500")}}}
    report = build(rows, adjustments=adjustments, age=age)
    assert report["adjustment_count"] == 4
    us, de, eu = site(report, "US"), site(report, "DE"), site(report, "EU")
    assert (us["store_operation"], de["store_operation"]) == (D("-200.00"), D("-100.00"))
    assert (us["gu_destruction"], eu["gu_destruction"]) == (D("-100.00"), D("-200.00"))
    assert eu["points"] == D("50.00") and us["points"] == D("0.00")
    assert us["capital_cost"] == D("-36.00")                           # 3600 × 12% × 30/360
    assert us["gross_profit"] == us["platform_net"] - 200 - 100 - 36 + us["tax_risk"]
    a = owner(report, "甲")
    assert a["store_operation"] == D("-200.00") and a["gu_destruction"] == D("-150.00") and a["points"] == D("20.00")
    assert a["other_cost"] == -a["platform_income"] * D("0.01") - D("1500") * D("0.24") * 30 / 360


def test_ratios_are_none_when_income_is_zero():
    report = build([frow(category="AD_FEE", gross="-1", net="-1", order=None)])
    assert site(report, "DE")["gross_margin"] is None


def test_get_report_requires_transactions_and_usd_rate(monkeypatch):
    monkeypatch.setattr(repo, "finance_rows", lambda month: [])
    with pytest.raises(ValueError, match="还没有拉取 eBay 交易流水"):
        svc.get_report(MONTH)
    monkeypatch.setattr(repo, "finance_rows", lambda month: [frow()])
    monkeypatch.setattr(repo, "rates", lambda month: {"EUR": D("8")})
    with pytest.raises(ValueError, match="中行折算价"):
        svc.get_report(MONTH)


def test_adjustment_scopes_are_enforced():
    with pytest.raises(ValueError, match="只能记在"):
        svc._adjustment_payload(MONTH, {"fee_item": "store_operation", "row_code": "US", "amount": "1"}, None, ["甲"])
    with pytest.raises(ValueError, match="只能记在"):
        svc._adjustment_payload(MONTH, {"fee_item": "packaging", "row_code": "甲", "amount": "1"}, None, ["甲"])
    ok = svc._adjustment_payload(MONTH, {"fee_item": "points", "row_code": "甲", "amount": "12.345"}, "u", ["甲"])
    assert ok["amount"] == D("12.35") and ok["row_code"] == "甲"


def test_rates_are_validated():
    with pytest.raises(ValueError, match="币种代码无效"):
        svc.save_rates(MONTH, {"US": "7"}, None)
    with pytest.raises(ValueError, match="之间"):
        svc.save_rates(MONTH, {"USD": "0"}, None)


# ------------------------------------------------------------ 接口与调度
@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


def test_routes_are_wired(client, monkeypatch):
    monkeypatch.setattr(svc, "get_report", lambda month: {"stat_month": month})
    monkeypatch.setattr(svc, "save_rates", lambda month, rates, operator: {"saved": len(rates), "month": month})
    assert client.get("/api/v1/finance/ebay-monthly-profit/report", params={"stat_month": MONTH}).json()["data"] == {
        "stat_month": MONTH}
    assert client.get("/api/v1/finance/ebay-monthly-profit/report", params={"stat_month": "2026-13"}).status_code == 422
    response = client.put("/api/v1/finance/ebay-monthly-profit/rates",
                          json={"stat_month": MONTH, "rates": {"USD": 6.7253}, "operator": "u"})
    assert response.json()["data"] == {"saved": 1, "month": MONTH}
    monkeypatch.setattr(svc, "get_report", lambda month: (_ for _ in ()).throw(ValueError("请先录入")))
    assert client.get("/api/v1/finance/ebay-monthly-profit/report", params={"stat_month": MONTH}).status_code == 400


def test_both_monthly_pull_tasks_are_registered_and_default_to_previous_month():
    for code in ("goodcang_bill_monthly_sync", "ebay_finance_monthly_sync"):
        spec = scheduler_service.TASK_SPECS[code]
        assert spec.default_previous_month is True
    assert fs.EbayFinanceSyncError in scheduler_service._STAGED_ERRORS
    assert gb.GoodcangBillSyncError in scheduler_service._STAGED_ERRORS


def test_get_report_excludes_the_amz_group_store(monkeypatch):
    monkeypatch.setattr(repo, "finance_rows", lambda month: [frow(), frow(store="eBay-主体27-demo-store-20", order="X")])
    monkeypatch.setattr(repo, "rates", lambda month: RATES)
    monkeypatch.setattr(repo, "bill_rows", lambda month: [])
    monkeypatch.setattr(repo, "storage_rows", lambda month: [])
    monkeypatch.setattr(repo, "order_costs", lambda month: {})
    monkeypatch.setattr(repo, "order_cost_month_rows", lambda month: 1)
    monkeypatch.setattr(repo, "adjustments", lambda month: [])
    monkeypatch.setattr(repo, "finance_months", lambda limit=36: [])
    monkeypatch.setattr(svc, "inventory_age", lambda month: {})
    monkeypatch.setattr(svc, "_owner_resolver", lambda month: (lambda sku: OWNERS.get(sku), ["甲", "乙"]))
    report = svc.get_report(MONTH)
    assert report["store_count"] == 1 and report["transaction_rows"] == 1
    assert any("demo-store-20" in text for text in report["notices"])


def test_inventory_age_uses_the_snapshot_taken_early_next_month(monkeypatch):
    from backend.repositories import clearance_repository as clearance_repo
    from backend.services import clearance_drilldown_service as clearance
    seen = []
    monkeypatch.setattr(clearance_repo, "months", lambda limit=24: [{"pull_month": "2026-11"}])
    monkeypatch.setattr(clearance_repo, "list_site_dimensions", lambda month: seen.append(month) or {"items": [
        {"dimension_name": "DE", "inventory_91_180_cost": D("10"), "inventory_181_270_cost": D("1"),
         "inventory_271_365_cost": D("2"), "inventory_365_plus_cost": D("3")}]})
    monkeypatch.setattr(clearance, "list_dimensions", lambda month, group, dimension=None: seen.append(month) or {"items": [
        {"dimension_name": "甲", "inventory_91_180_cost": D("4"), "ctu_over_30_cost": D("9")}]})
    age = svc.inventory_age("2026-10")
    assert seen == ["2026-11", "2026-11"]
    assert age["site"]["DE"]["over_180"] == D("6") and age["site"]["US"]["ctu_30"] == D("3")
    assert age["owner"]["甲"]["ctu_30"] == D("9")
    monkeypatch.setattr(clearance_repo, "months", lambda limit=24: [{"pull_month": "2026-10"}])
    assert "还没有 2026-12 初的库龄快照" in svc.inventory_age("2026-11")["notices"][0]
