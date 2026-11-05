from datetime import date
from decimal import Decimal

import pytest

from backend.services import amz_profit_report_sync_service as service
from backend.services import scheduler_service


class FakeClient:
    """Serves settlement records per 7-day window and one OrderProfit page."""

    def __init__(self, seller=None, msku=None, order=None, codes=None):
        self.calls = []
        self.seller = seller if seller is not None else self._seller
        self.msku = msku if msku is not None else self._msku
        self.order = order if order is not None else self._order
        self.codes = list(codes or [])

    def post_signed_query_auth(self, path, body):
        self.calls.append((path, dict(body)))
        if self.codes:
            return {"code": self.codes.pop(0), "data": None}
        if path == service.SELLER_PATH:
            return self.seller(body)
        if path == service.MSKU_PATH:
            return self.msku(body)
        return self.order(body)

    @staticmethod
    def _seller(body):
        day = body["startDate"]
        return {"code": 0, "data": {"total": 1, "records": [{
            "sid": 101, "storeName": "US1-川服喜-US", "countryCode": "US",
            "postedDateLocale": day, "totalSalesQuantity": 2,
            "totalSalesAmount": "100.50", "grossProfit": "20.25",
        }]}}

    @staticmethod
    def _msku(body):
        day = body["startDate"]
        return {"code": 0, "data": {"total": 2, "records": [
            {"sid": 101, "msku": "A-1", "asin": "B1", "dataDate": day,
             "localSku": "LS-1", "totalSalesQuantity": 2, "totalSalesAmount": 100.5,
             "grossProfit": 20.25, "totalAdsCost": -3,
             "estimateFeeStr": [{"name": "仓库费用", "amount": -1.5}]},
            {"sid": 101, "msku": "", "dataDate": day, "otherInAmount": 0},
        ]}}

    @staticmethod
    def _order(body):
        return {"code": 0, "total": 2, "data": [
            {"price_list": [{"sid": "101", "seller_sku": "A-1", "asin": "B1", "local_sku": "LS-1"}],
             "seller_store_countries": [{"country": "美国", "name": "US1-川服喜-US"}], "volume": 9, "amount": "500.00",
             "gross_profit": "80.00", "refund_quantity": "1"},
            {"price_list": [{"sid": "", "seller_sku": ""}]},
        ]}


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    stored = {}
    monkeypatch.setattr(service.source_repo, "amazon_seller_ids", lambda *args, **kwargs: ["101"])
    monkeypatch.setattr(service.repo, "replace_month", lambda month, *rows: stored.update(
        month=month, seller=rows[0], msku=rows[1], order=rows[2],
    ) or {"deleted_rows": 0, "seller_rows": len(rows[0]),
          "msku_rows": len(rows[1]), "order_rows": len(rows[2])})
    return stored


def test_month_windows_never_exceed_seven_days():
    windows = service.month_windows("2026-02")
    assert windows[0] == (date(2026, 2, 1), date(2026, 2, 7))
    assert windows[-1] == (date(2026, 2, 22), date(2026, 2, 28))
    assert all((end - start).days < 7 for start, end in windows)
    assert len(service.month_windows("2026-09")) == 5


def test_sync_pulls_usd_by_window_and_sums_msku_to_month(scope):
    client = FakeClient()
    result = service.sync_amz_profit_report("2026-09", client=client, sleep=lambda _s: None)

    assert result["status"] == "completed"
    settlement_calls = [body for path, body in client.calls if path != service.ORDER_PATH]
    assert len(settlement_calls) == 10  # 5 windows × (seller + msku)
    assert {body["currencyCode"] for _path, body in client.calls} == {"USD"}
    order_calls = [body for path, body in client.calls if path == service.ORDER_PATH]
    assert order_calls == [{"sids": ["101"], "startDate": "2026-09-01", "endDate": "2026-09-30",
                            "currencyCode": "USD", "offset": 0, "length": service.ORDER_PAGE_SIZE}]

    assert len(scope["seller"]) == 5
    assert scope["seller"][0]["raw_json"]["storeName"] == "US1-川服喜-US"
    msku = {row["msku"]: row for row in scope["msku"]}
    assert msku["A-1"]["total_sales_quantity"] == 10
    assert msku["A-1"]["total_sales_amount"] == Decimal("502.5")
    assert msku["A-1"]["total_ads_cost"] == Decimal("-15")
    assert msku["A-1"]["source_rows"] == 5
    assert msku["A-1"]["estimate_fees_json"] == {"仓库费用": "-7.5"}
    assert "-" in msku  # store-level allocation row is kept
    [order] = scope["order"]
    assert order["gross_profit"] == Decimal("80.00") and order["refund_quantity"] == 1
    assert order["country"] == "美国" and order["local_sku"] == "LS-1"
    assert result["skipped_rows"] == 1
    assert result["reconcile_diff_stores"] == []


def test_paginates_until_total_is_reached(scope):
    pages = []

    def msku(body):
        pages.append(body["offset"])
        if body["offset"] == 0:
            return {"code": 0, "data": {"total": 2, "records": [
                {"sid": 101, "msku": "A", "dataDate": body["startDate"]}]}}
        return {"code": 0, "data": {"total": 2, "records": [
            {"sid": 101, "msku": "B", "dataDate": body["startDate"]}]}}

    service.sync_amz_profit_report("2026-09", client=FakeClient(msku=msku), sleep=lambda _s: None)
    assert pages[:2] == [0, service.SETTLEMENT_PAGE_SIZE]
    assert {row["msku"] for row in scope["msku"]} == {"A", "B"}


def test_rate_limit_code_is_retried(scope):
    sleeps = []
    client = FakeClient(codes=["3001008"])
    service.sync_amz_profit_report("2026-09", client=client, sleep=sleeps.append)
    assert len(scope["seller"]) == 5
    assert any(delay >= 2 for delay in sleeps)


def test_server_error_code_is_retried_and_orders_run_first(scope):
    client = FakeClient(codes=["500"])
    service.sync_amz_profit_report("2026-09", client=client, sleep=lambda _s: None)
    assert client.calls[0][0] == service.ORDER_PATH
    assert client.calls[1][0] == service.ORDER_PATH  # retried after code 500
    assert len(scope["order"]) == 1


def test_empty_source_keeps_existing_month(monkeypatch, scope):
    client = FakeClient(order=lambda body: {"code": 0, "total": 0, "data": []})
    with pytest.raises(service.AmzProfitReportSyncError) as error:
        service.sync_amz_profit_report("2026-09", client=client, sleep=lambda _s: None)
    assert error.value.stage == "TRANSFORM"
    assert "订单利润" in str(error.value)
    assert scope == {}


def test_duplicate_settlement_day_is_rejected(scope):
    def seller(body):
        record = {"sid": 101, "postedDateLocale": "2026-09-01"}
        return {"code": 0, "data": {"total": 1, "records": [record]}}

    with pytest.raises(service.AmzProfitReportSyncError, match="重复返回"):
        service.sync_amz_profit_report("2026-09", client=FakeClient(seller=seller), sleep=lambda _s: None)
    assert scope == {}


def test_store_and_msku_totals_are_reconciled():
    seller = [{"sid": "1", "total_sales_amount": Decimal("100"), "gross_profit": Decimal("10")}]
    msku = [{"sid": "1", "total_sales_amount": Decimal("100.4"), "gross_profit": Decimal("7")}]
    assert service.reconcile_stores(seller, msku) == [
        {"sid": "1", "field": "gross_profit", "difference": "3"},
    ]


def test_scheduler_registers_monthly_task():
    spec = scheduler_service.TASK_SPECS[service.TASK_CODE]
    assert spec.default_previous_month is True
    assert spec.lock_name(scheduler_service.TaskContext(task_code=service.TASK_CODE, month="2026-09")) \
        == "lingxing:amz-profit-report:2026-09"
    assert service.AmzProfitReportSyncError in scheduler_service._STAGED_ERRORS


def test_progress_is_logged_for_each_stage_window_and_retry(scope, caplog):
    caplog.set_level("INFO", logger=service.LOG.name)
    client = FakeClient(codes=["3001008"])
    service.sync_amz_profit_report("2026-09", client=client, sleep=lambda _s: None)
    messages = [record.getMessage() for record in caplog.records if record.name == service.LOG.name]
    assert messages[0].startswith("AMZ利润报表拉取开始 month=2026-09")
    for stage in ("EXTRACT_ORDER", "EXTRACT_SELLER", "EXTRACT_MSKU", "TRANSFORM", "LOAD"):
        assert any(f"阶段={stage}（" in m for m in messages), stage
    # 5 个周窗口 × 1 个店铺组，店铺和 MSKU 各 5 条进度
    assert sum("阶段=EXTRACT_SELLER 进度" in m for m in messages) == 5
    assert any("进度5/5 窗口2026-09-29~2026-09-30" in m for m in messages)
    assert any("领星重试" in m and "业务错误码 3001008" in m for m in messages)
    assert messages[-1].startswith("AMZ利润报表拉取完成 month=2026-09")


def test_failure_is_logged_with_stage(scope, caplog):
    caplog.set_level("INFO", logger=service.LOG.name)
    client = FakeClient(order=lambda body: {"code": 0, "total": 0, "data": []})
    with pytest.raises(service.AmzProfitReportSyncError):
        service.sync_amz_profit_report("2026-09", client=client, sleep=lambda _s: None)
    assert any("拉取失败 month=2026-09" in r.getMessage() and "阶段=TRANSFORM" in r.getMessage()
               for r in caplog.records)


def test_duplicate_trigger_names_the_run_in_progress(monkeypatch):
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    named = SimpleNamespace(name=service.TASK_NAME)
    context = SimpleNamespace(task_code=service.TASK_CODE, month="2026-10")
    started = datetime.now() - timedelta(minutes=18)
    monkeypatch.setattr(scheduler_service.repo, "running_scheduler_run",
                        lambda code, month, exclude: {"run_id": "r-1", "started_at": started}
                        if (code, month, exclude) == (service.TASK_CODE, "2026-10", "new") else None)
    message =scheduler_service._already_running_message(named, context, "new")
    assert message.startswith("AMZ利润报表数据拉取正在执行：2026-10 这次拉取于 ")
    assert "已执行约 18 分钟" in message and "run_id=r-1" in message
    monkeypatch.setattr(scheduler_service.repo, "running_scheduler_run", lambda *a: None)
    assert scheduler_service._already_running_message(named, context, "new") == "AMZ利润报表数据拉取正在执行"
