"""eBay 实时只读工具：汇总口径、单店失败不计 0、数据范围限制、错误分类、日期范围限制。"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

import pytest
import requests

from backend.agent import ebay_live
from backend.agent import runner as runner_module
from backend.agent.context import SCOPE_EBAY, AgentAccess, AgentContext, ToolPermissionError
from backend.agent.ebay_live import EbayReadError, StoreTarget, read_error
from backend.agent.tools import ebay_live_tools as live
from backend.ebay_api.credentials import EbayCredentials
from tests.test_ai_agent import FakeConversations, FakeRepo, ScriptedLlm, call, reply

REAL_GET = ebay_live.StoreReader.get  # 其他用例用替身替换 get，这里保留真实实现测重试逻辑
CRED = EbayCredentials("id", "secret", "refresh")
STORES = [StoreTarget("b1", "Store-DE", "de_login", CRED), StoreTarget("b2", "Store-UK", "uk_login", CRED)]
TODAY = datetime.now(live.BEIJING).date()


def ctx(scope="all", permissions=("finance:salesDashboard:list", "operations:ebayReturnOverview:list")):
    scopes = {SCOPE_EBAY: None if scope == "all" else ["张三"]}
    return AgentContext(1, "tester", AgentAccess(frozenset(permissions), scopes), "req")


@pytest.fixture(autouse=True)
def fake_ebay(monkeypatch):
    ebay_live.clear_caches()
    monkeypatch.setattr(live, "store_targets", lambda: STORES)
    responses: dict[tuple[str, str], object] = {}

    def fake_get(self, path, params=None, **kwargs):
        value = responses.get((self.store.key, path), {})
        if isinstance(value, Exception):
            raise value
        return value(params) if callable(value) else value

    monkeypatch.setattr(ebay_live.StoreReader, "get", fake_get)
    monkeypatch.setattr(ebay_live.StoreReader, "registration_marketplace", lambda self: "EBAY_US")
    yield responses
    ebay_live.clear_caches()


def order(order_id, sku, qty, value, cur="EUR", cancelled=False, created=None):
    created = created or datetime.now(live.BEIJING).isoformat()
    return {"orderId": order_id, "creationDate": created,
            "cancelStatus": {"cancelState": "CANCELED" if cancelled else "NONE_REQUESTED"},
            "lineItems": [{"sku": sku, "quantity": qty, "title": f"title {sku}", "listingMarketplaceId": "EBAY_DE",
                           "total": {"value": str(value), "currency": cur}}]}


def test_orders_group_by_store_excludes_cancelled_and_reports_failed_store(fake_ebay):
    fake_ebay[("b1", "/sell/fulfillment/v1/order")] = {"total": 3, "orders": [
        order("o1", "DAS-1", 2, 20.5), order("o2", "DAS-2", 1, 9.5), order("o3", "DAS-1", 5, 99, cancelled=True)]}
    fake_ebay[("b2", "/sell/fulfillment/v1/order")] = EbayReadError("x", "NO_SCOPE", 403)
    result = live.ebay_orders_summary(ctx(), live.OrdersArgs())
    assert result.rows == [{"group": "Store-DE", "currency": "EUR", "orders": 2, "units": 3, "amount": 30.0}]
    assert result.summary["订单数"] == 2 and result.summary["销售额（EUR）"] == 30.0
    assert any("取消订单 1 单" in n for n in result.notes)
    assert any("Store-UK（店铺授权里没有这类数据的权限" in n for n in result.notes)


def test_orders_group_by_sku_with_filter_and_top(fake_ebay):
    fake_ebay[("b1", "/sell/fulfillment/v1/order")] = {"total": 2, "orders": [
        order("o1", "DAS-1", 2, 20), order("o2", "BMW-9", 7, 70)]}
    fake_ebay[("b2", "/sell/fulfillment/v1/order")] = {"total": 1, "orders": [order("o3", "DAS-1", 1, 10)]}
    result = live.ebay_orders_summary(ctx(), live.OrdersArgs(group_by="sku", sku="das"))
    assert [(r["group"], r["units"], r["orders"]) for r in result.rows] == [("DAS-1", 3, 2)]


def test_finance_summary_classifies_transactions(fake_ebay):
    fake_ebay[("b1", "/sell/finances/v1/transaction")] = {"total": 4, "transactions": [
        {"transactionType": "SALE", "bookingEntry": "CREDIT", "amount": {"value": "100", "currency": "USD"},
         "totalFeeAmount": {"value": "12"}},
        {"transactionType": "NON_SALE_CHARGE", "feeType": "AD_FEE", "bookingEntry": "DEBIT",
         "amount": {"value": "5", "currency": "USD"}},
        {"transactionType": "REFUND", "bookingEntry": "DEBIT", "amount": {"value": "20", "currency": "USD"}},
        {"transactionType": "PAYOUT", "bookingEntry": "DEBIT", "amount": {"value": "60", "currency": "USD"}}]}
    fake_ebay[("b1", "/sell/finances/v1/payout")] = {"payouts": [
        {"payoutStatus": "SUCCEEDED", "amount": {"value": "60", "currency": "USD"}}]}
    fake_ebay[("b1", "/sell/finances/v1/seller_funds_summary")] = {
        "totalFunds": {"value": "300", "currency": "USD"}, "fundsOnHold": {"value": "40", "currency": "USD"}}
    fake_ebay[("b2", "/sell/finances/v1/transaction")] = EbayReadError("x", "NO_SCOPE", 403)
    result = live.ebay_finance_summary(ctx(), live.LiveArgs(store="Store"))
    row = result.rows[0]
    assert (row["sales_net"], row["fees"], row["ad_fees"], row["refunds"], row["net"]) == (100, -12, -5, -20, 75)
    assert (row["payouts"], row["balance"], row["on_hold"], row["currency"]) == (60, 300, 40, "USD")
    assert result.summary["净额（USD）"] == 75


def test_after_sales_counts_and_details(fake_ebay):
    fake_ebay[("b1", "/post-order/v2/return/search")] = {"members": [
        {"returnId": "r1", "orderId": "o1", "creationInfo": {"creationDate": {"value": "2026-11-01T10:00:00Z"},
                                                             "reason": "DEFECTIVE"},
         "sellerResponseDue": {"activityDue": "SELLER_APPROVE"}}], "paginationOutput": {"totalPages": 1}}
    fake_ebay[("b1", "/post-order/v2/inquiry/search")] = {"members": [
        {"inquiryId": "i1", "inquiryStatusEnum": "CLOSED", "creationDate": {"value": "2026-11-01T10:00:00Z"}}]}
    fake_ebay[("b1", "/sell/fulfillment/v1/payment_dispute_summary")] = EbayReadError("x", "NO_SCOPE", 403)
    fake_ebay[("b2", "/post-order/v2/return/search")] = {"members": []}
    summary = live.ebay_after_sales(ctx(), live.AfterSalesArgs())
    de = next(r for r in summary.rows if r["store"] == "Store-DE")
    assert (de["退货"], de["未收到货"], de["open"]) == (1, 1, 1) and summary.summary["待处理合计"] == 1
    assert summary.summary["退货（待处理）"] == 1 and summary.summary["未收到货（待处理）"] == 0
    assert summary.summary["未收到货（总数）"] == 1
    details = live.ebay_after_sales(ctx(), live.AfterSalesArgs(include_details=True))
    assert {r["kind"] for r in details.rows} == {"退货", "未收到货"}


def test_seller_standards_and_traffic_and_campaigns(fake_ebay):
    profile = {"standardsProfiles": [
        {"program": "PROGRAM_DE", "standardsLevel": "BELOW_STANDARD", "cycle": {"cycleType": "CURRENT"},
         "metrics": [{"metricKey": "DEFECTIVE_TRANSACTION_RATE", "value": {"value": "2.5"}}]},
        {"program": "PROGRAM_UK", "standardsLevel": "TOP_RATED", "cycle": {"cycleType": "PROJECTED"}, "metrics": []}]}
    fake_ebay[("b1", "/sell/analytics/v1/seller_standards_profile")] = profile
    standards = live.ebay_seller_standards(ctx(), live.StoreOnlyArgs(store="Store-DE"))
    assert standards.rows[0]["PROGRAM_DE"] == "不合格" and standards.rows[0]["defect_rate"] == 2.5
    assert standards.rows[0]["PROGRAM_UK"] == "" and standards.summary["有站点不合格的店铺数"] == 1

    def report(params):
        if "EBAY_GB" in params["filter"]:
            raise EbayReadError("x", "ERROR", 400)
        return {"header": {"metrics": [{"key": "LISTING_IMPRESSION_TOTAL"}, {"key": "LISTING_VIEWS_TOTAL"},
                                       {"key": "TRANSACTION"}]},
                "records": [{"dimensionValues": [{"value": "20261101"}],
                             "metricValues": [{"value": 1000}, {"value": 50}, {"value": 5}]}]}
    fake_ebay[("b1", "/sell/analytics/v1/traffic_report")] = report
    fake_ebay[("b2", "/sell/analytics/v1/traffic_report")] = EbayReadError("x", "RATE_LIMIT", 429)
    traffic = live.ebay_traffic(ctx(), live.TrafficArgs(marketplaces=["EBAY_DE", "EBAY_GB"]))
    assert traffic.rows == [{"group": "Store-DE", "impressions": 1000, "views": 50, "transactions": 5,
                             "view_rate": 0.05, "conversion": 0.1}]
    assert any("Store-UK（eBay 限流" in n for n in traffic.notes)

    fake_ebay[("b1", "/sell/marketing/v1/ad_campaign")] = {"total": 2, "campaigns": [
        {"campaignName": "A", "campaignStatus": "RUNNING", "fundingStrategy": {"bidPercentage": "5.0"}},
        {"campaignName": "B", "campaignStatus": "ENDED", "fundingStrategy": {}}]}
    campaigns = live.ebay_campaigns(ctx(), live.StoreOnlyArgs(store="de"))
    assert campaigns.summary["进行中"] == 1 and campaigns.summary["进行中平均广告费率%"] == 5.0


def test_live_tools_require_all_ebay_scope_and_page_permission():
    limited = ctx(scope="self")
    with pytest.raises(ToolPermissionError, match="全部数据"):
        live.ebay_orders_summary(limited, live.OrdersArgs())
    tools = {t.name: t for t in live.EBAY_LIVE_TOOLS}
    assert not tools["ebay_finance_summary"].available_to(limited)
    assert tools["ebay_finance_summary"].available_to(ctx())
    assert not tools["ebay_after_sales"].available_to(ctx(permissions=("finance:salesDashboard:list",)))
    admin = AgentContext(1, "admin", AgentAccess(frozenset({"*:*:*"}), {}), "req")
    assert all(t.available_to(admin) for t in live.EBAY_LIVE_TOOLS)


def test_runner_hides_live_tools_and_rejects_direct_calls_for_limited_scope():
    llm = ScriptedLlm([reply(tool_calls=[call("a", "ebay_orders_summary")]), reply(content="无法查询")])
    repo = FakeRepo()
    runner = runner_module.AgentRunner(llm=llm, tools=live.EBAY_LIVE_TOOLS, repo=repo,
                                       conversations=FakeConversations())
    asyncio.run(runner.run("run-1", ctx(scope="self"), "conv-1", "今天eBay卖了多少", None))
    offered = {s["function"]["name"] for s in llm.requests[0]["tools"]}
    assert not offered & {t.name for t in live.EBAY_LIVE_TOOLS}
    assert repo.steps[0]["status"] == "denied"


def test_date_window_limits():
    with pytest.raises(ValueError, match="31 天"):
        live.window(live.LiveArgs(start_date=TODAY - timedelta(days=40), end_date=TODAY), ctx())
    win = live.window(live.LiveArgs(), ctx())
    assert (win.end - win.start).days == 6 and win.end == TODAY
    traffic = live.window(live.TrafficArgs(), ctx(), max_days=90, end_offset=1)
    assert traffic.end == TODAY - timedelta(days=1)
    with pytest.raises(ValueError):
        live.LiveArgs(start_date=date(2026, 11, 2), end_date=date(2026, 11, 1))


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body, self.headers, self.content = status, body, {}, b"x"

    def json(self):
        return self._body


def test_read_error_classification():
    assert read_error("/p", FakeResponse(403, {"errors": [{"errorId": 1100, "message": "Access denied"}]})).kind == "NO_SCOPE"
    assert read_error("/p", FakeResponse(400, {"errors": [{"errorId": 215122, "message": "x"}]})).kind == "SIGNATURE"
    assert read_error("/p", FakeResponse(429, {})).kind == "RATE_LIMIT"
    assert read_error("/p", FakeResponse(403, {"errors": [{"errorId": 1, "message": "Forbidden"}]})).kind == "DENIED"


def test_reader_retries_network_errors_and_refreshes_on_401(monkeypatch):
    ebay_live.clear_caches()

    class Session:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append(url)
            if url == ebay_live.TOKEN_URL:
                return FakeResponse(200, {"access_token": f"t{len(self.calls)}", "expires_in": 7200})
            if len(self.calls) == 2:
                raise requests.ConnectionError("reset")
            if len([c for c in self.calls if c != ebay_live.TOKEN_URL]) == 2:
                return FakeResponse(401, {})
            return FakeResponse(200, {"ok": True})

    session = Session()
    reader = ebay_live.StoreReader(STORES[0], session=session, sleep=lambda s: None)
    assert REAL_GET(reader, "/sell/x") == {"ok": True}
    assert session.calls.count(ebay_live.TOKEN_URL) == 2  # 401 后重新取令牌
    ebay_live.clear_caches()
