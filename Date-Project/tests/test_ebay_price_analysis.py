"""eBay 价格分析 BI：状态判定、刷表落库、看板聚合与接口层。

重点盯三件会让看板说谎的事：
1. 未关联到库存的刊登被静默丢掉（实测 US 站近两成关联不上）
2. 近 7 日无销量时 cover_days 被写成 0 或极大值
3. 汇率缺失时 price_usd 被补成 0
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.deps import require_internal_access
from backend.api.v1 import ebay_price_analysis as api
from backend.config import PROJECT_ROOT
from backend.repositories import ebay_price_analysis_repository as repo
from backend.services import ebay_price_analysis_service as service
from backend.sql_statements import split_sql_statements

MIGRATION = PROJECT_ROOT / "migrations" / "20261110_ebay_price_analysis.sql"
STAT_DATE = date(2026, 9, 23)
REFRESHED_AT = datetime(2026, 9, 23, 10, 15, 11)
RATES = {"USD": Decimal("6.523541"), "EUR": Decimal("7.308659"),
         "GBP": Decimal("8.647065")}


def source(**overrides):
    """一条「健康」的源记录，各测试只覆盖自己关心的字段。"""
    row = {
        "seller_account": "aplus-shop", "item_id": "3948", "sku": "TYT-90245-0772",
        "site": "DE", "site_name": "德国", "title": "For Toyota Sensor",
        "image_url": "https://img/1.jpg", "view_item_url": "https://ebay.de/itm/3948",
        "currency": "EUR", "current_price": "52.9", "ebay_quantity": 100,
        "ebay_quantity_available": 36, "ebay_quantity_sold": 64, "watch_count": 7,
        "overseas_sellable": Decimal("120"), "overseas_in_transit": Decimal("10"),
        "chengdu_sellable": Decimal("40"), "pending_outbound": Decimal("2"),
        "sales_qty_7d": Decimal("3"), "sales_qty_30d": Decimal("14"),
        "purchase_cost_cny": Decimal("186.4"),
    }
    row.update(overrides)
    return row


def build(**overrides):
    return service.build_row(source(**overrides), stat_date=STAT_DATE, rates=RATES,
                             batch_id="batch-1", refreshed_at=REFRESHED_AT)


# ----------------------------------------------------------- 状态判定 6 个分支
def test_status_covers_every_branch_top_down():
    # 未匹配优先于一切：没有库存就谈不上超卖或断货。
    assert build(overseas_sellable=None, chengdu_sellable=None,
                 overseas_in_transit=None, pending_outbound=None)["status"] == "未匹配"
    # 超卖：eBay 可售 > 谷仓 + 成都
    assert build(ebay_quantity_available=500)["status"] == "超卖风险"
    # 断货：谷仓为 0 且仍在售，但没超过谷仓+成都
    assert build(overseas_sellable=Decimal("0"), chengdu_sellable=Decimal("50"),
                 ebay_quantity_available=10)["status"] == "断货"
    # 待补货：覆盖天数不足 15 天（7 可售 ÷ (7/7=1 件/日) = 7 天）
    replenish = build(overseas_sellable=Decimal("7"), sales_qty_7d=Decimal("7"))
    assert replenish["cover_days"] == Decimal("7.00")
    assert replenish["status"] == "待补货"
    # 滞销：近 30 日无销量但谷仓有货
    assert build(sales_qty_7d=Decimal("0"),
                 sales_qty_30d=Decimal("0"))["status"] == "滞销"
    # 健康：其余
    assert build()["status"] == "健康"


def test_status_order_puts_oversell_before_out_of_stock():
    """谷仓 0、成都 0、仍在售：两个条件同时成立时按表格顺序取「超卖风险」。"""
    assert build(overseas_sellable=Decimal("0"),
                 chengdu_sellable=Decimal("0"))["status"] == "超卖风险"


def test_status_does_not_guess_when_ebay_available_is_missing():
    """接口没给可售量时不拿 None 当 0：既不判超卖也不判断货，缺口也不算。"""
    row = build(ebay_quantity_available=None, overseas_sellable=Decimal("0"),
                chengdu_sellable=Decimal("0"), sales_qty_7d=Decimal("0"),
                sales_qty_30d=Decimal("5"))
    assert row["ebay_quantity_available"] is None
    assert row["stock_gap"] is None
    assert row["status"] == "健康"
    assert service.resolve_status(
        inventory_matched=True, ebay_quantity_available=None, overseas_sellable=0,
        chengdu_sellable=0, cover_days_value=None, sales_qty_30d=5) == "健康"


# ----------------------------------------------------------- 三个边界
def test_zero_overseas_stock_is_kept_as_a_real_zero():
    """谷仓可售为 0 是真实的 0：仍算匹配，参与缺口计算，不退化成未匹配。"""
    row = build(overseas_sellable=Decimal("0"), chengdu_sellable=Decimal("0"),
                ebay_quantity_available=4)
    assert row["inventory_matched"] == 1
    assert row["overseas_sellable"] == 0
    assert row["stock_gap"] == -4
    assert row["cover_days"] == Decimal("0.00")


def test_zero_seven_day_sales_leaves_cover_days_null():
    for sales in (Decimal("0"), None):
        row = build(sales_qty_7d=sales)
        assert row["sales_qty_7d"] == 0
        assert row["cover_days"] is None, "近7日无销量必须留 NULL，不写 0 也不写极大值"
    assert service.cover_days(120, 0) is None
    assert service.cover_days(120, None) is None
    assert service.cover_days(None, 7) is None


def test_missing_rate_leaves_price_usd_null():
    row = service.build_row(source(currency="PLN"), stat_date=STAT_DATE, rates=RATES,
                            batch_id="b", refreshed_at=REFRESHED_AT)
    assert row["current_price"] == Decimal("52.9")
    assert row["price_usd"] is None, "汇率缺失必须留 NULL，不补 0"
    # 连 USD 汇率都没有时，本币有汇率也不折算
    assert service.price_usd(Decimal("10"), "EUR", {"EUR": Decimal("7.3")}) is None
    # USD 原币短路，不经过汇率
    assert service.price_usd(Decimal("10"), "usd", {}) == Decimal("10")


def test_price_usd_uses_my_rate_ratio():
    row = build()
    assert row["price_usd"] == (Decimal("52.9") * RATES["EUR"] / RATES["USD"]
                               ).quantize(Decimal("0.000001"))


def test_invalid_listing_price_is_null_not_zero():
    for raw in ("", None, "abc", "0", "0.00", "-1", "1,5"):
        row = build(current_price=raw)
        assert row["current_price"] is None
        assert row["price_usd"] is None


def test_cover_days_is_capped_to_the_stored_column_width():
    row = build(overseas_sellable=Decimal("500000"), sales_qty_7d=Decimal("1"))
    assert row["cover_days"] <= service.COVER_DAYS_MAX


# ----------------------------------------------------------- 落库行
def test_unmatched_listing_is_kept_with_null_inventory():
    row = build(sku="ZZZ-00001-0001", overseas_sellable=None, overseas_in_transit=None,
                chengdu_sellable=None, pending_outbound=None)
    assert row["inventory_matched"] == 0
    assert row["status"] == "未匹配"
    for key in ("overseas_sellable", "overseas_in_transit", "chengdu_sellable",
                "pending_outbound", "cover_days", "stock_gap"):
        assert row[key] is None, f"{key} 未匹配时必须留 NULL，0 会被算进缺口和超卖"


def test_sku_segments_and_stock_gap():
    row = build()
    assert (row["brand_code"], row["mid_code"]) == ("TYT", "TYT-90245")
    assert row["stock_gap"] == 120 - 36
    assert row["site_name"] == "德国"
    assert row["stat_date"] == STAT_DATE and row["refreshed_at"] == REFRESHED_AT
    assert service.mid_code("SINGLE") is None
    assert service.brand_code(None) is None


def test_build_rows_keeps_every_listing_including_unmatched():
    payload = {
        "batch": {"stat_date": STAT_DATE, "stat_month": "2026-09"},
        "rates": RATES,
        "rows": [source(), source(item_id="1", overseas_sellable=None,
                                  chengdu_sellable=None),
                 source(item_id="2", site="FR", site_name=None,
                        overseas_sellable=None, chengdu_sellable=None)],
    }
    rows = service.build_rows(payload, batch_id="b", refreshed_at=REFRESHED_AT)
    assert len(rows) == 3
    assert [row["status"] for row in rows] == ["健康", "未匹配", "未匹配"]
    assert rows[2]["site"] == "FR" and rows[2]["site_name"] is None
    assert service.build_rows({"batch": {}, "rows": []}, batch_id="b",
                              refreshed_at=REFRESHED_AT) == []


# ----------------------------------------------------------- 刷表
@pytest.fixture
def refresh_repo(monkeypatch):
    calls = {}
    monkeypatch.setattr(repo, "read_source", lambda: {
        "batch": {"stat_date": STAT_DATE, "stat_month": "2026-09",
                  "pulled_at": REFRESHED_AT, "listing_rows": 2, "account_count": 2},
        "rates": RATES,
        "rows": [source(), source(seller_account="b-shop", item_id="9",
                                  overseas_sellable=None, chengdu_sellable=None)],
    })

    def replace(rows):
        calls["rows"] = rows
        return {"rows": len(rows), "deleted_rows": 7}

    monkeypatch.setattr(repo, "replace_rows", replace)
    return calls


def test_refresh_replaces_the_whole_table_and_reports_per_account(refresh_repo):
    result = service.refresh_price_analysis()
    assert result["status"] == "success"
    assert result["rows"] == 2 and result["deleted_rows"] == 7
    assert result["stat_date"] == "2026-09-23"
    assert result["accounts"] == [{"seller_account": "aplus-shop", "rows": 1},
                                 {"seller_account": "b-shop", "rows": 1}]
    assert result["matched_rows"] == 1
    assert result["status_counts"] == {"健康": 1, "未匹配": 1}
    assert {row["sync_batch_id"] for row in refresh_repo["rows"]} == {result["sync_batch_id"]}


def test_refresh_without_listing_batch_raises_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(repo, "read_source", lambda: {"batch": {}, "rows": [], "rates": {}})
    writer = MagicMock()
    monkeypatch.setattr(repo, "replace_rows", writer)
    with pytest.raises(ValueError, match="没有任何在售刊登"):
        service.refresh_price_analysis()
    writer.assert_not_called()


def test_refresh_write_failure_propagates_to_the_scheduler(monkeypatch):
    monkeypatch.setattr(repo, "read_source", lambda: {
        "batch": {"stat_date": STAT_DATE}, "rates": RATES, "rows": [source()]})
    monkeypatch.setattr(repo, "replace_rows", MagicMock(side_effect=RuntimeError("lock wait")))
    with pytest.raises(RuntimeError, match="lock wait"):
        service.refresh_price_analysis()


# ----------------------------------------------------------- 看板聚合
def point(key, price, overseas, available, statuses, listings=1):
    return {"group_key": key, "mid_code": key.rsplit("-", 1)[0], "price_sum": price,
            "price_rows": 1 if price is not None else 0, "overseas_sellable": overseas,
            "ebay_available": available, "statuses": statuses,
            "listing_count": listings, "matched_listing_count": listings,
            "sales_qty_30d": 3}


@pytest.fixture
def board(monkeypatch):
    state = {
        "summary": {
            "listing_count": 18013, "sku_count": 9821, "ebay_available": Decimal("52140"),
            "matched_ebay_available": Decimal("50000"), "avg_price_usd": Decimal("42.1812"),
            "missing_price_usd": 12, "overseas_sellable": Decimal("38920"),
            "chengdu_sellable": Decimal("100"), "overseas_in_transit": Decimal("5"),
            "status_counts": {"超卖风险": 412, "未匹配": 1447, "健康": 16000},
        },
        "points": [point("AAA-1-1", Decimal("10"), 900, 40, "健康"),
                   point("BBB-2-2", Decimal("30"), 0, 5, "断货,滞销"),
                   point("CCC-3-3", Decimal("50"), 100, 20, "健康"),
                   point("DDD-4-4", None, None, 7, "未匹配")],
        "stores": [{"seller_account": "aplus-shop", "site": "DE",
                    "ebay_available": Decimal("2140"), "listing_count": 981,
                    "overseas_sellable": Decimal("1820")}],
    }
    monkeypatch.setattr(repo, "meta", lambda: {
        "stat_date": STAT_DATE, "refreshed_at": REFRESHED_AT, "rows": 18013})
    monkeypatch.setattr(repo, "summary", lambda criteria: state["summary"])
    monkeypatch.setattr(repo, "store_compare", lambda criteria: state["stores"])
    monkeypatch.setattr(repo, "dimension_points",
                        lambda criteria, dimension: state["points"])
    return state


def test_overview_kpis_match_the_contract(board):
    data = service.overview()
    assert data["stat_date"] == "2026-09-23"
    assert data["refreshed_at"] == "2026-09-23 10:15:11"
    kpis = {item["key"]: item for item in data["kpis"]}
    assert [item["key"] for item in data["kpis"]] == [
        "listing_count", "sku_count", "ebay_available", "overseas_sellable",
        "stock_gap", "oversell_count", "unmatched_count", "avg_price_usd"]
    assert kpis["listing_count"]["value"] == 18013
    assert kpis["overseas_sellable"]["value"] == 38920
    # 缺口只对关联上的刊登算：38920 − 50000
    assert kpis["stock_gap"]["value"] == -11080
    assert kpis["oversell_count"]["value"] == 412
    assert kpis["unmatched_count"]["value"] == 1447
    assert kpis["avg_price_usd"]["value"] == 42.18
    assert kpis["avg_price_usd"]["unit"] == "USD"


def test_overview_scatter_median_and_gap_top(board):
    data = service.overview()
    assert data["scatter_sampled"] is False
    assert [item["sku"] for item in data["scatter"]] == [
        "AAA-1-1", "BBB-2-2", "CCC-3-3", "DDD-4-4"]
    assert data["scatter"][0]["price_usd"] == 10.0
    assert "stock_gap" not in data["scatter"][0]
    # 中位数只取有值的点：价格 10/30/50 -> 30，库存 0/100/900 -> 100
    assert data["scatter_median"] == {"price_usd": 30.0, "overseas_sellable": 100.0}
    # 未匹配的点没有库存，不进缺口榜；按缺口绝对值排序
    assert [item["sku"] for item in data["stock_gap_top"]] == [
        "AAA-1-1", "CCC-3-3", "BBB-2-2"]
    assert data["stock_gap_top"][0]["stock_gap"] == 860
    assert data["stock_gap_top"][2]["stock_gap"] == -5


def test_overview_aggregated_status_takes_the_most_severe(board):
    data = service.overview()
    statuses = {item["sku"]: item["status"] for item in data["scatter"]}
    assert statuses["BBB-2-2"] == "断货", "断货比滞销严重，聚合后取断货"
    assert statuses["DDD-4-4"] == "未匹配"


def test_overview_samples_scatter_above_the_limit(board):
    board["points"] = [point(f"S-{index}-1", Decimal(index), index, index, "健康")
                       for index in range(service.SCATTER_LIMIT + 500)]
    data = service.overview()
    assert data["scatter_sampled"] is True
    assert len(data["scatter"]) == service.SCATTER_LIMIT
    assert data["scatter_total"] == service.SCATTER_LIMIT + 500
    # 抽样不改参考线：中位数仍按全量点算
    assert data["scatter_median"]["price_usd"] == pytest.approx(
        (service.SCATTER_LIMIT + 499) / 2, abs=1)


def test_overview_risks_cover_every_non_healthy_status(board):
    risks = {item["key"]: item for item in service.overview()["risks"]}
    assert set(risks) == {"oversell", "out_of_stock", "replenish", "unmatched",
                          "slow_moving"}
    assert risks["oversell"]["count"] == 412 and risks["oversell"]["impact"] == 1
    assert risks["oversell"]["filter"] == {"status": "超卖风险"}
    assert risks["out_of_stock"]["count"] == 0
    assert [risks[key]["impact"] for key in
            ("oversell", "out_of_stock", "replenish", "unmatched", "slow_moving")] == [
        1, 2, 3, 4, 5]


def test_overview_rejects_unknown_dimension_and_status(board):
    with pytest.raises(ValueError, match="dimension"):
        service.overview(dimension="brand")
    with pytest.raises(ValueError, match="状态取值无效"):
        service.overview(status="爆单")


def test_filters_are_parsed_into_bound_parameters(board, monkeypatch):
    seen = {}
    monkeypatch.setattr(repo, "summary", lambda criteria: seen.setdefault(
        "criteria", criteria) or board["summary"])
    service.overview(stat_date="2026-09-23", sites="de,uk,de", accounts="a,b",
                     status="未匹配", keyword=" sensor ")
    criteria = seen["criteria"]
    assert criteria["stat_date"] == STAT_DATE
    assert criteria["sites"] == ["DE", "UK"]
    assert criteria["accounts"] == ["a", "b"]
    assert criteria["statuses"] == ["未匹配"]
    assert criteria["keyword"] == "sensor"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.overview(stat_date="2026/09/23")


# ----------------------------------------------------------- 明细
def stored_row(**overrides):
    row = {
        "seller_account": "aplus-shop", "site": "DE", "site_name": "德国",
        "item_id": "3948", "sku": "TYT-90245-0772", "mid_code": "TYT-90245",
        "brand_code": "TYT", "title": "t", "image_url": "i", "view_item_url": "v",
        "currency": "EUR", "current_price": Decimal("52.900000"),
        "price_usd": Decimal("58.200000"), "ebay_quantity": 100,
        "ebay_quantity_available": 36, "ebay_quantity_sold": 64, "watch_count": 7,
        "overseas_sellable": 120, "overseas_in_transit": 0, "chengdu_sellable": 40,
        "pending_outbound": 2, "inventory_matched": 1, "sales_qty_7d": 3,
        "sales_qty_30d": 14, "cover_days": Decimal("280.00"), "stock_gap": 84,
        "purchase_cost_cny": Decimal("186.400000"), "status": "健康",
        "stat_date": STAT_DATE,
    }
    row.update(overrides)
    return row


def test_detail_paginates_and_keeps_nulls(monkeypatch):
    seen = {}

    def rows(criteria, **kwargs):
        seen.update(kwargs)
        return [stored_row(), stored_row(item_id="9", inventory_matched=0,
                                        status="未匹配", overseas_sellable=None,
                                        cover_days=None, stock_gap=None,
                                        price_usd=None)]

    monkeypatch.setattr(repo, "detail_rows", rows)
    monkeypatch.setattr(repo, "detail_count", lambda criteria: 18013)
    data = service.detail(page=3, page_size=50, sort_by="stock_gap", sort_order="asc")
    assert (data["total"], data["page"], data["page_size"]) == (18013, 3, 50)
    assert seen == {"sort_by": "stock_gap", "sort_order": "asc", "offset": 100,
                    "limit": 50}
    first, unmatched = data["rows"]
    assert first["current_price"] == 52.9 and first["price_usd"] == 58.2
    assert first["cover_days"] == 280.0 and first["stat_date"] == "2026-09-23"
    assert unmatched["overseas_sellable"] is None
    assert unmatched["cover_days"] is None and unmatched["stock_gap"] is None
    assert unmatched["price_usd"] is None


def test_detail_summary_mode_uses_sku_grain(monkeypatch):
    monkeypatch.setattr(repo, "summary_rows", lambda criteria, **kwargs: [stored_row(
        statuses="健康,断货", listing_count=4, store_count=2)])
    monkeypatch.setattr(repo, "summary_count", lambda criteria: 9821)
    monkeypatch.setattr(repo, "detail_rows", MagicMock(
        side_effect=AssertionError("summary 模式不应走明细取数")))
    data = service.detail(mode="summary")
    assert data["total"] == 9821 and data["mode"] == "summary"
    row = data["rows"][0]
    assert row["status"] == "断货"
    assert (row["listing_count"], row["store_count"]) == (4, 2)
    assert "seller_account" not in row and "item_id" not in row


def test_detail_clamps_page_size_and_rejects_unknown_mode(monkeypatch):
    monkeypatch.setattr(repo, "detail_rows", lambda criteria, **kwargs: [])
    monkeypatch.setattr(repo, "detail_count", lambda criteria: 0)
    assert service.detail(page=0, page_size=10_000)["page_size"] == service.MAX_PAGE_SIZE
    with pytest.raises(ValueError, match="mode"):
        service.detail(mode="chart")


# ----------------------------------------------------------- 导出
def sheet_values(content):
    from openpyxl import load_workbook
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        return [list(row) for row in workbook.active.iter_rows(values_only=True)]
    finally:
        workbook.close()


def test_export_respects_the_allowed_column_list(monkeypatch):
    monkeypatch.setattr(repo, "detail_rows", lambda criteria, **kwargs: [stored_row()])
    name, content = service.export(columns="sku,status,unknown_column")
    assert name.startswith("eBay价格分析明细-") and name.endswith(".xlsx")
    rows = sheet_values(content)
    assert rows[0] == ["SKU", "状态"], "未授权的列不应出现在导出件里"
    assert rows[1] == ["TYT-90245-0772", "健康"]
    assert len(rows) == 2


def test_export_without_columns_exports_everything_and_refuses_empty(monkeypatch):
    monkeypatch.setattr(repo, "detail_rows", lambda criteria, **kwargs: [stored_row()])
    _, content = service.export()
    assert sheet_values(content)[0] == [label for _, label in service.EXPORT_COLUMNS]
    monkeypatch.setattr(repo, "detail_rows", lambda criteria, **kwargs: [])
    with pytest.raises(ValueError, match="没有可导出的数据"):
        service.export()


def test_export_writes_placeholder_for_missing_values(monkeypatch):
    monkeypatch.setattr(repo, "detail_rows", lambda criteria, **kwargs: [
        stored_row(cover_days=None, price_usd=None)])
    _, content = service.export(columns="cover_days,price_usd")
    assert sheet_values(content)[1] == ["--", "--"], "缺失值写 -- 而不是 0"


# ----------------------------------------------------------- 接口层
@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None

    @app.middleware("http")
    async def add_request_id(request, call_next):
        request.state.request_id = "price-analysis-test"
        return await call_next(request)

    with TestClient(app) as test_client:
        yield test_client, app


def test_api_overview_and_detail_pass_filters_through(client, monkeypatch):
    test_client, _ = client
    seen = {}
    monkeypatch.setattr(service, "overview", lambda **kwargs: seen.setdefault(
        "overview", kwargs) or {"kpis": []})
    monkeypatch.setattr(service, "detail", lambda **kwargs: seen.setdefault(
        "detail", kwargs) or {"total": 0, "rows": []})
    overview = test_client.get("/api/v1/ebay-price-analysis/overview",
                               params={"sites": "DE", "dimension": "mid"})
    assert overview.status_code == 200 and overview.json()["code"] == 0
    assert seen["overview"]["sites"] == "DE"
    assert seen["overview"]["dimension"] == "mid"
    detail = test_client.get("/api/v1/ebay-price-analysis/detail",
                             params={"mode": "summary", "mid_code": "TYT-90245"})
    assert detail.status_code == 200
    assert seen["detail"]["mode"] == "summary"
    assert seen["detail"]["mid_code_filter"] == "TYT-90245"


def test_api_maps_value_error_to_400_and_failures_to_500(client, monkeypatch):
    test_client, _ = client

    def bad(**kwargs):
        raise ValueError("状态取值无效：爆单")

    monkeypatch.setattr(service, "overview", bad)
    response = test_client.get("/api/v1/ebay-price-analysis/overview")
    assert response.status_code == 400
    assert "状态取值无效" in response.json()["detail"]

    def broken(**kwargs):
        raise RuntimeError("table missing")

    monkeypatch.setattr(service, "overview", broken)
    failed = test_client.get("/api/v1/ebay-price-analysis/overview")
    assert failed.status_code == 500
    assert "20261110_ebay_price_analysis.sql" in failed.json()["detail"]
    assert "table missing" not in failed.json()["detail"]


def test_api_export_streams_xlsx(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(service, "export", lambda **kwargs: ("名称.xlsx", b"PK\x03\x04x"))
    response = test_client.get("/api/v1/ebay-price-analysis/export",
                               params={"columns": "sku"})
    assert response.status_code == 200
    assert response.headers["content-type"] == service.EXCEL_CONTENT_TYPE
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"PK\x03\x04x"


def test_api_requires_internal_access(client, monkeypatch):
    test_client, app = client
    reader = MagicMock()
    monkeypatch.setattr(service, "overview", reader)

    def deny():
        raise HTTPException(status_code=403, detail="internal access denied")

    app.dependency_overrides[require_internal_access] = deny
    assert test_client.get("/api/v1/ebay-price-analysis/overview").status_code == 403
    reader.assert_not_called()


# ----------------------------------------------------------- SQL 与迁移脚本
def strip_comments(statement):
    body = "\n".join(line for line in statement.splitlines()
                     if not line.strip().startswith("--"))
    return body.strip()


def test_migration_is_idempotent_and_additive_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [strip_comments(item) for item in split_sql_statements(sql)]
    assert len(statements) == 1, "只建 dws_ebay_price_analysis 一张表，别夹带其他语句"
    for statement in statements:
        assert statement.upper().startswith("CREATE TABLE IF NOT EXISTS"), statement[:60]
    upper = sql.upper()
    for forbidden in ("DROP ", "ALTER ", "TRUNCATE", "INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in upper, f"迁移脚本不应包含 {forbidden.strip()}"
    assert repo.TABLE in sql
    assert "refresh_request" not in sql, "页面刷新登记表已取消"
    assert "uk_price_analysis_listing" in sql


def test_migration_declares_every_column_the_loader_writes():
    sql = MIGRATION.read_text(encoding="utf-8")
    for column in repo.COLUMNS:
        assert f"\n  {column} " in sql, f"迁移脚本缺少列 {column}"


def test_source_query_keeps_unmatched_listings_and_uses_the_agreed_warehouses():
    query = repo._inventory_ctes()
    assert "18699,18700,18701,18702" in query and "18674,18675,18676" in query
    assert "德国" in query and "英国" in query and "美国" in query
    assert "weekly_inventory_bin" in query, "只认跑出过成功周报导出的那批快照"
    assert repo.SITE_NAME_BY_SITE == {"DE": "德国", "UK": "英国", "US": "美国"}
    listing = repo._listing_cte(None)
    assert "ORDER BY MAX(pulled_at) DESC" in listing


def test_filters_bind_every_value_and_whitelist_sort_columns():
    where, params = repo._filters({"stat_date": STAT_DATE, "sites": ["DE", "UK"],
                                   "accounts": ["a"], "statuses": ["未匹配"],
                                   "keyword": "sen", "sku": "A-1-1",
                                   "mid_code": "A-1"})
    assert where.count("%s") == len(params) == 11
    assert "DROP" not in where
    assert repo._filters({}) == ("", [])
    for column in ("status", "cover_days", "stock_gap", "price_usd"):
        assert column in repo.SORTABLE


def test_detail_sort_falls_back_for_unknown_columns(monkeypatch):
    captured = {}

    def fake_query(sql, params):
        captured["sql"] = sql
        return []

    monkeypatch.setattr(repo, "_query", fake_query)
    repo.detail_rows({}, sort_by="1=1; DROP TABLE x", sort_order="asc", limit=10,
                     offset=0)
    assert "DROP TABLE" not in captured["sql"]
    assert "ORDER BY (stock_gap IS NULL) ASC,stock_gap ASC" in captured["sql"]
    repo.summary_rows({}, sort_by="store_count", sort_order="desc")
    assert "store_count DESC" in captured["sql"]


def test_page_refresh_registration_route_is_gone(client):
    test_client, _ = client
    assert test_client.post("/api/v1/ebay-price-analysis/refresh").status_code in (404, 405)
    assert not hasattr(service, "request_refresh")
    for name in ("REQUEST_TABLE", "insert_request", "finish_requests", "pending_requests"):
        assert not hasattr(repo, name), name
    # 定时任务的数据生产通道保留
    assert service.TASK_CODE == "ebay_price_analysis_refresh"
    assert callable(service.refresh_price_analysis)
