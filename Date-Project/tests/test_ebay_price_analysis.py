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
        "rate_months": {"USD": "2026-09", "EUR": "2026-08"},
        "goodcang": {"exists": True, "rows": 4913},
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
    assert result["rate_months"] == {"EUR": "2026-08", "USD": "2026-09"}


def test_refresh_without_listing_batch_raises_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(repo, "read_source", lambda: {"batch": {}, "rows": [], "rates": {}})
    writer = MagicMock()
    monkeypatch.setattr(repo, "replace_rows", writer)
    with pytest.raises(ValueError, match="没有任何在售刊登"):
        service.refresh_price_analysis()
    writer.assert_not_called()


@pytest.mark.parametrize("goodcang,message", [
    ({"exists": False, "rows": 0}, "ods_goodcang_product_inventory_latest 不存在"),
    ({"exists": True, "rows": 0}, "谷仓库存快照为空"),
    (None, "不存在"),
])
def test_refresh_refuses_missing_or_empty_goodcang_snapshot(monkeypatch, goodcang, message):
    source_data = {"batch": {"stat_date": STAT_DATE}, "rates": RATES, "rows": []}
    if goodcang is not None:
        source_data["goodcang"] = goodcang
    monkeypatch.setattr(repo, "read_source", lambda: source_data)
    writer = MagicMock()
    monkeypatch.setattr(repo, "replace_rows", writer)
    with pytest.raises(ValueError, match=message) as error:
        service.refresh_price_analysis()
    assert "看板保持上一次结果" in str(error.value)
    writer.assert_not_called()


class _SnapshotCursor:
    def __init__(self, table_exists, rows):
        self.answers = [{"n": 1 if table_exists else 0}, {"n": rows}]
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append((sql, params))

    def fetchone(self):
        return self.answers.pop(0)


def test_goodcang_snapshot_checks_table_then_counts_only_dashboard_warehouses():
    cursor = _SnapshotCursor(True, 4913)
    assert repo.goodcang_snapshot(cursor) == {"exists": True, "rows": 4913}
    assert "information_schema.TABLES" in cursor.sql[0][0]
    assert cursor.sql[0][1] == (repo.GOODCANG_TABLE,)
    assert cursor.sql[1][0].startswith("SELECT COUNT(*)")
    assert cursor.sql[1][1] == ("DE", "UK", "USEA", "USWE")
    missing = _SnapshotCursor(False, 0)
    assert repo.goodcang_snapshot(missing) == {"exists": False, "rows": 0}
    assert len(missing.sql) == 1, "表不存在时不再查表"


def test_refresh_write_failure_propagates_to_the_scheduler(monkeypatch):
    monkeypatch.setattr(repo, "read_source", lambda: {
        "batch": {"stat_date": STAT_DATE}, "rates": RATES, "rows": [source()],
        "goodcang": {"exists": True, "rows": 1}})
    monkeypatch.setattr(repo, "replace_rows", MagicMock(side_effect=RuntimeError("lock wait")))
    with pytest.raises(RuntimeError, match="lock wait"):
        service.refresh_price_analysis()


# ----------------------------------------------------------- 店铺汇总与 SKU 跨店
def test_overview_and_its_helpers_are_gone():
    for name in ("overview", "_kpis", "_point", "_sample", "_median", "SCATTER_LIMIT", "RISKS"):
        assert not hasattr(service, name), name
    for name in ("summary", "store_compare", "dimension_points"):
        assert not hasattr(repo, name), name


def test_stores_shapes_rows_and_only_takes_site_and_account_filters(monkeypatch):
    seen = {}

    def rows(criteria):
        seen["criteria"] = criteria
        return [{"seller_account": "aplus-shop", "site": "DE", "site_name": "德国",
                 "listing_count": 981, "sku_count": 960, "ebay_available": Decimal("2140"),
                 "out_of_stock_listed": Decimal("37"), "site_oversell_sku_count": 12,
                 "unmatched_count": Decimal("21")}]

    monkeypatch.setattr(repo, "store_rows", rows)
    monkeypatch.setattr(repo, "meta", lambda: {"stat_date": STAT_DATE, "refreshed_at": REFRESHED_AT})
    data = service.stores(sites="de,uk,de", accounts="aplus-shop")
    assert data == {"stat_date": "2026-09-23", "refreshed_at": "2026-09-23 10:15:11", "rows": [{
        "seller_account": "aplus-shop", "site": "DE", "site_name": "德国",
        "listing_count": 981, "sku_count": 960, "ebay_available": 2140,
        "out_of_stock_listed": 37, "site_oversell_sku_count": 12, "unmatched_count": 21}]}
    assert seen["criteria"]["sites"] == ["DE", "UK"]
    assert seen["criteria"]["accounts"] == ["aplus-shop"]


def test_sku_listings_reports_every_store_and_one_inventory_per_site(monkeypatch):
    seen = {}
    monkeypatch.setattr(repo, "meta", lambda: {"stat_date": STAT_DATE, "refreshed_at": REFRESHED_AT})
    monkeypatch.setattr(repo, "sku_listings", lambda sku: seen.setdefault("sku", sku) and [
        {"seller_account": "a", "site": "DE", "site_name": "德国", "item_id": "1",
         "view_item_url": "v", "currency": "EUR", "current_price": Decimal("52.9"),
         "price_usd": Decimal("58.2"), "ebay_quantity_available": 10, "status": "超卖风险",
         "title": "t", "image_url": "i", "out_of_stock_listed": 1},
        {"seller_account": "b", "site": "DE", "site_name": "德国", "item_id": "2",
         "view_item_url": "v2", "currency": "EUR", "current_price": None, "price_usd": None,
         "ebay_quantity_available": 10, "status": "超卖风险", "title": "t", "image_url": "i"}])
    monkeypatch.setattr(repo, "sku_sites", lambda sku: [
        {"site": "DE", "site_name": "德国", "site_overseas_sellable": 20,
         "site_overseas_in_transit": 0, "site_chengdu_sellable": None,
         "site_pending_outbound": 2, "site_ebay_available_total": Decimal("30"),
         "site_store_count": 3, "site_oversell": 1}])
    data = service.sku_listings(sku="  TYT-90245-0772 ")
    assert seen["sku"] == "TYT-90245-0772", "TRIM 后精确匹配"
    assert data["sku"] == "TYT-90245-0772" and data["title"] == "t" and data["image_url"] == "i"
    assert data["stat_date"] == "2026-09-23" and data["refreshed_at"] == "2026-09-23 10:15:11"
    assert [row["seller_account"] for row in data["listings"]] == ["a", "b"]
    assert data["listings"][0]["price_usd"] == 58.2 and data["listings"][1]["price_usd"] is None
    assert data["listings"][0]["out_of_stock_listed"] is True
    assert data["listings"][1]["out_of_stock_listed"] is False, "缺字段按 False，不报错"
    assert data["sites"] == [{"site": "DE", "site_name": "德国", "overseas_sellable": 20,
                              "overseas_in_transit": 0, "chengdu_sellable": None,
                              "pending_outbound": 2, "ebay_available_total": 30,
                              "store_count": 3, "site_oversell": True}]


def test_sku_listings_unknown_sku_returns_empty_arrays_and_requires_sku(monkeypatch):
    monkeypatch.setattr(repo, "meta", lambda: {"stat_date": None, "refreshed_at": None})
    monkeypatch.setattr(repo, "sku_listings", lambda sku: [])
    monkeypatch.setattr(repo, "sku_sites", MagicMock(side_effect=AssertionError("没有刊登就不查站点")))
    data = service.sku_listings(sku="NOPE-1-1")
    assert data["listings"] == [] and data["sites"] == [] and data["title"] is None
    with pytest.raises(ValueError, match="sku 必填"):
        service.sku_listings(sku="  ")


def test_detail_rows_carry_cross_store_comparison(monkeypatch):
    monkeypatch.setattr(repo, "meta", lambda: {"stat_date": STAT_DATE, "refreshed_at": REFRESHED_AT})
    seen = {}

    def rows(criteria, **kwargs):
        seen["criteria"] = criteria
        return [stored_row(site_store_count=3, site_ebay_available_total=Decimal("30"),
                           site_price_usd_min=Decimal("50"), site_price_usd_max=Decimal("70"),
                           price_vs_site_min_pct=Decimal("0.164"), site_oversell=1,
                           out_of_stock_listed=0)]

    monkeypatch.setattr(repo, "detail_rows", rows)
    monkeypatch.setattr(repo, "detail_count", lambda criteria: 1)
    data = service.detail(site_oversell=True, out_of_stock_listed=True)
    row = data["rows"][0]
    assert (row["site_store_count"], row["site_ebay_available_total"]) == (3, 30)
    assert (row["site_price_usd_min"], row["site_price_usd_max"]) == (50.0, 70.0)
    assert row["price_vs_site_min_pct"] == 0.164
    assert row["site_oversell"] is True and row["out_of_stock_listed"] is False
    assert seen["criteria"]["site_oversell"] is True
    assert seen["criteria"]["out_of_stock_listed"] is True


def test_summary_rows_carry_price_range_and_oversell_but_not_per_listing_columns(monkeypatch):
    monkeypatch.setattr(repo, "meta", lambda: {"stat_date": STAT_DATE, "refreshed_at": REFRESHED_AT})
    monkeypatch.setattr(repo, "summary_rows", lambda criteria, **kwargs: [stored_row(
        statuses="健康", listing_count=3, store_count=3, price_usd_min=Decimal("50"),
        price_usd_max=Decimal("70"), site_oversell=1, site_store_count=3)])
    monkeypatch.setattr(repo, "summary_count", lambda criteria: 1)
    row = service.detail(mode="summary")["rows"][0]
    assert (row["store_count"], row["price_usd_min"], row["price_usd_max"]) == (3, 50.0, 70.0)
    assert row["site_oversell"] is True
    for key in ("site_store_count", "site_price_usd_min", "price_vs_site_min_pct"):
        assert key not in row


def test_filters_are_parsed_into_bound_parameters(monkeypatch):
    seen = {}
    monkeypatch.setattr(repo, "meta", lambda: {})
    monkeypatch.setattr(repo, "detail_count", lambda criteria: seen.setdefault("criteria", criteria) and 0)
    monkeypatch.setattr(repo, "detail_rows", lambda criteria, **kwargs: [])
    service.detail(stat_date="2026-09-23", sites="de,uk,de", accounts="a,b",
                   status="未匹配", keyword=" sensor ")
    criteria = seen["criteria"]
    assert criteria["stat_date"] == STAT_DATE
    assert criteria["sites"] == ["DE", "UK"]
    assert criteria["accounts"] == ["a", "b"]
    assert criteria["statuses"] == ["未匹配"]
    assert criteria["keyword"] == "sensor"
    assert criteria["site_oversell"] is False and criteria["out_of_stock_listed"] is False
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.detail(stat_date="2026/09/23")
    with pytest.raises(ValueError, match="状态取值无效"):
        service.detail(status="爆单")


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


@pytest.fixture(autouse=True)
def snapshot_meta(monkeypatch):
    monkeypatch.setattr(repo, "meta", lambda: {
        "stat_date": STAT_DATE, "refreshed_at": REFRESHED_AT, "rows": 18013})


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
    assert data["stat_date"] == "2026-09-23"
    assert data["refreshed_at"] == "2026-09-23 10:15:11"
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
    assert data["stat_date"] == "2026-09-23"


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


def test_api_stores_sku_listings_and_detail_pass_filters_through(client, monkeypatch):
    test_client, _ = client
    seen = {}
    monkeypatch.setattr(service, "stores", lambda **kwargs: seen.setdefault(
        "stores", kwargs) or {"rows": []})
    monkeypatch.setattr(service, "sku_listings", lambda **kwargs: seen.setdefault(
        "sku_listings", kwargs) or {"listings": []})
    monkeypatch.setattr(service, "detail", lambda **kwargs: seen.setdefault(
        "detail", kwargs) or {"total": 0, "rows": []})
    stores = test_client.get("/api/v1/ebay-price-analysis/stores",
                             params={"sites": "DE", "accounts": "a,b"})
    assert stores.status_code == 200 and stores.json()["code"] == 0
    assert seen["stores"] == {"sites": "DE", "accounts": "a,b"}
    listings = test_client.get("/api/v1/ebay-price-analysis/sku-listings",
                               params={"sku": "TYT-90245-0772"})
    assert listings.status_code == 200
    assert seen["sku_listings"] == {"sku": "TYT-90245-0772"}
    assert test_client.get("/api/v1/ebay-price-analysis/sku-listings").status_code == 422
    detail = test_client.get("/api/v1/ebay-price-analysis/detail",
                             params={"mode": "summary", "mid_code": "TYT-90245",
                                     "site_oversell": "true", "out_of_stock_listed": "true"})
    assert detail.status_code == 200
    assert seen["detail"]["mode"] == "summary"
    assert seen["detail"]["mid_code_filter"] == "TYT-90245"
    assert seen["detail"]["site_oversell"] is True
    assert seen["detail"]["out_of_stock_listed"] is True
    assert test_client.get("/api/v1/ebay-price-analysis/overview").status_code == 404


def test_api_maps_value_error_to_400_and_failures_to_500(client, monkeypatch):
    test_client, _ = client

    def bad(**kwargs):
        raise ValueError("状态取值无效：爆单")

    monkeypatch.setattr(service, "stores", bad)
    response = test_client.get("/api/v1/ebay-price-analysis/stores")
    assert response.status_code == 400
    assert "状态取值无效" in response.json()["detail"]

    def broken(**kwargs):
        raise RuntimeError("table missing")

    monkeypatch.setattr(service, "stores", broken)
    failed = test_client.get("/api/v1/ebay-price-analysis/stores")
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


def test_api_export_passes_the_two_flag_filters(client, monkeypatch):
    test_client, _ = client
    seen = {}
    monkeypatch.setattr(service, "export", lambda **kwargs: seen.update(kwargs) or ("a.xlsx", b"PK"))
    response = test_client.get("/api/v1/ebay-price-analysis/export",
                               params={"site_oversell": "true", "out_of_stock_listed": "false"})
    assert response.status_code == 200
    assert seen["site_oversell"] is True and seen["out_of_stock_listed"] is False


@pytest.mark.parametrize("mode,repo_fn", [("detail", "detail_rows"), ("summary", "summary_rows")])
def test_export_with_site_oversell_matches_detail_filtering(monkeypatch, mode, repo_fn):
    """勾了「只看多店超卖」再导出：导出与 /detail 走同一套筛选，拿到的是同一批行。"""
    seen = []
    flagged = [stored_row(item_id="1", site_oversell=1, statuses="超卖风险"),
               stored_row(item_id="2", sku="FRD-1-1", site_oversell=1, statuses="超卖风险")]

    def rows(criteria, **kwargs):
        seen.append(criteria)
        return flagged if criteria["site_oversell"] else [*flagged, stored_row(item_id="3")]

    monkeypatch.setattr(repo, repo_fn, rows)
    monkeypatch.setattr(repo, "detail_count", lambda criteria: 2)
    monkeypatch.setattr(repo, "summary_count", lambda criteria: 2)
    listed = service.detail(mode=mode, sites="DE", site_oversell=True, page_size=200)
    _, content = service.export(mode=mode, sites="DE", site_oversell=True, columns="sku")
    assert seen[0] == seen[1], "导出与明细的筛选条件完全一致"
    assert seen[1]["site_oversell"] is True and seen[1]["sites"] == ["DE"]
    exported = [row[0] for row in sheet_values(content)[1:]]
    assert exported == [row["sku"] for row in listed["rows"]] == ["TYT-90245-0772", "FRD-1-1"]


def test_export_columns_are_unchanged_by_the_new_flags():
    keys = [key for key, _ in service.EXPORT_COLUMNS]
    for added in ("site_oversell", "out_of_stock_listed", "site_store_count",
                  "site_price_usd_min", "price_vs_site_min_pct"):
        assert added not in keys, "导出列不变，否则要改列权限 SQL"


def test_api_requires_internal_access(client, monkeypatch):
    test_client, app = client
    reader = MagicMock()
    monkeypatch.setattr(service, "stores", reader)

    def deny():
        raise HTTPException(status_code=403, detail="internal access denied")

    app.dependency_overrides[require_internal_access] = deny
    assert test_client.get("/api/v1/ebay-price-analysis/stores").status_code == 403
    reader.assert_not_called()


# ----------------------------------------------------------- SQL 与迁移脚本
def strip_comments(statement):
    body = "\n".join(line for line in statement.splitlines()
                     if not line.strip().startswith("--"))
    return body.strip()


def test_migration_is_idempotent_and_additive_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [strip_comments(item) for item in split_sql_statements(sql)]
    statements = [item for item in statements if item]
    # 约定：第一条语句前只允许 USE `date-project` 与 SET NAMES utf8mb4（防 Windows 客户端按 gbk 执行）
    preamble = {"USE `DATE-PROJECT`", "SET NAMES UTF8MB4"}
    head = [item for item in statements[:2] if item.upper().rstrip(";").strip() in preamble]
    assert {item.upper().rstrip(";").strip() for item in head} == preamble, "开头缺 USE / SET NAMES"
    body = statements[len(head):]
    assert len(body) == 1, "只建 dws_ebay_price_analysis 一张表，别夹带其他语句"
    assert body[0].upper().startswith("CREATE TABLE IF NOT EXISTS"), body[0][:60]
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
    # 海外仓改取谷仓区域仓：DE/UK/USEA/USWE，美国两仓合计，CZ 不纳入；不再读领星海外仓 wid。
    assert repo.GOODCANG_TABLE in query
    assert "'DE','UK','USEA','USWE'" in query and "'CZ'" not in query
    assert "WHEN 'USEA' THEN '美国' WHEN 'USWE' THEN '美国'" in query
    assert "SUM(COALESCE(g.onway,0)) overseas_in_transit" in query, "海外在途取 onway，不取 total_onway"
    assert "total_onway" not in query
    assert "SUM(COALESCE(g.reserved,0)) overseas_pending_outbound" in query
    for wid in (18699, 18700, 18701, 18702):
        assert str(wid) not in query
    # 成都中转仓仍取领星周快照、只认成功周报导出的那批。
    assert "WHERE i.wid IN (18674,18675,18676)" in query
    assert "weekly_inventory_bin" in query, "只认跑出过成功周报导出的那批快照"
    assert "德国" in query and "英国" in query and "美国" in query
    assert repo.SITE_NAME_BY_SITE == {"DE": "德国", "UK": "英国", "US": "美国"}
    listing = repo._listing_cte(None)
    assert "ORDER BY MAX(pulled_at) DESC" in listing


@pytest.mark.parametrize("sku,key", [
    ("JMH-10437-0774", "10437-0774"),
    ("DAS-10437-0774", "10437-0774"),
    ("JMH-10437-0774-YXR", "10437-0774-YXR"),
    ("JMH-30020-2-0018", "30020-2-0018"),
    ("BMW-30020-2-0018", "30020-2-0018"),
    ("JMH-10022", "10022"),
    (" jmh-10022 ", "10022"),
    ("NOPREFIX", None),
    ("JMH-", None),
    (None, None),
])
def test_inventory_key_strips_only_the_first_segment(sku, key):
    assert repo.inventory_key(sku) == key


def test_overseas_join_uses_the_same_key_expression_on_both_sides():
    query = repo._inventory_ctes()
    # 谷仓侧与 listing 侧都用 _inventory_key_sql 取 key
    assert repo._inventory_key_sql("g.product_sku") in query
    listing_key = repo._inventory_key_sql("listing.sku")
    assert "SUBSTRING(" in listing_key and "LOCATE('-'" in listing_key


def test_source_query_matches_overseas_by_key_and_chengdu_by_full_sku(monkeypatch):
    captured = {}

    class Cursor:
        def execute(self, sql, params=()):
            captured["sql"] = sql

        def fetchall(self):
            return []

    repo._source_rows(Cursor(), "2026-11", date(2026, 11, 10))
    sql = captured["sql"]
    assert "LEFT JOIN overseas_inventory overseas" in sql
    assert repo._inventory_key_sql("listing.sku") in sql
    assert "LEFT JOIN chengdu_inventory chengdu" in sql
    # 两边都没关联上才留 NULL，任一关联上即算匹配
    assert "WHEN overseas.site_name IS NULL AND chengdu.site_name IS NULL THEN NULL" in sql


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


# ----------------------------------------------------------- 多店超卖与库存口径
# 跨店聚合是一段纯标准 SQL（COUNT DISTINCT / SUM / MIN / MAX / CASE / COALESCE），
# 用内存 sqlite 直接执行同一段 SQL 文本验证口径；单元测试不连真实 MySQL。
def _site_sku(rows):
    import sqlite3

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE t (seller_account TEXT, site TEXT, sku TEXT, ebay_quantity_available INT,"
        " price_usd REAL, inventory_matched INT, overseas_sellable INT, chengdu_sellable INT,"
        " overseas_in_transit INT, pending_outbound INT, stat_date TEXT)")
    connection.executemany(
        "INSERT INTO t VALUES (:seller_account,:site,:sku,:ebay_quantity_available,:price_usd,"
        ":inventory_matched,:overseas_sellable,:chengdu_sellable,:overseas_in_transit,"
        ":pending_outbound,:stat_date)",
        [{"overseas_in_transit": 0, "pending_outbound": 0, "stat_date": "2026-11-10",
          "chengdu_sellable": 0, "price_usd": 50.0, "inventory_matched": 1, **row} for row in rows])
    result = {(row["site"], row["sku"]): dict(row)
              for row in connection.execute(repo.site_sku_sql("t"))}
    connection.close()
    return result


def test_three_stores_with_10_each_on_a_20_unit_warehouse_is_site_oversell():
    rows = [{"seller_account": store, "site": "DE", "sku": "TYT-1-1",
             "ebay_quantity_available": 10, "overseas_sellable": 20,
             "price_usd": price} for store, price in (("a", 50.0), ("b", 55.0), ("c", 60.0))]
    site = _site_sku(rows)[("DE", "TYT-1-1")]
    # 库存按站点共享：三条刊登挂的是同一份 20 件，绝不能被加成 60
    assert site["site_overseas_sellable"] == 20
    assert site["site_ebay_available_total"] == 30, "eBay 可售各店各自一份，相加"
    assert site["site_store_count"] == 3
    assert (site["site_price_usd_min"], site["site_price_usd_max"]) == (50.0, 60.0)
    assert site["site_oversell"] == 1, "30 > 20 + 0，判多店超卖"


def test_chengdu_stock_counts_and_single_store_view_cannot_see_the_oversell():
    rows = [{"seller_account": store, "site": "DE", "sku": "TYT-1-1",
             "ebay_quantity_available": 10, "overseas_sellable": 20, "chengdu_sellable": 10}
            for store in ("a", "b", "c")]
    assert _site_sku(rows)[("DE", "TYT-1-1")]["site_oversell"] == 0, "30 ≤ 20 + 10，不超卖"
    # 每家店单看都是 10 ≤ 20，只有按站点合计才看得出来
    each = [{"seller_account": "a", "site": "DE", "sku": "TYT-1-1",
             "ebay_quantity_available": 10, "overseas_sellable": 20}]
    assert _site_sku(each)[("DE", "TYT-1-1")]["site_oversell"] == 0


def test_oversell_is_per_site_and_only_for_matched_inventory():
    rows = [
        {"seller_account": "a", "site": "DE", "sku": "TYT-1-1", "ebay_quantity_available": 15,
         "overseas_sellable": 20},
        {"seller_account": "a", "site": "UK", "sku": "TYT-1-1", "ebay_quantity_available": 15,
         "overseas_sellable": 20},
        {"seller_account": "a", "site": "US", "sku": "TYT-2-2", "ebay_quantity_available": 5,
         "overseas_sellable": None, "chengdu_sellable": None, "inventory_matched": 0},
    ]
    result = _site_sku(rows)
    # DE、UK 各自 15 ≤ 20：跨站点不合并 eBay 可售，也不合并库存
    assert result[("DE", "TYT-1-1")]["site_oversell"] == 0
    assert result[("UK", "TYT-1-1")]["site_oversell"] == 0
    assert result[("US", "TYT-2-2")]["site_oversell"] == 0, "未匹配库存不判超卖"
    assert result[("US", "TYT-2-2")]["site_overseas_sellable"] is None


def test_site_aggregates_never_sum_shared_inventory():
    sql = repo.SITE_AGGREGATES_SQL
    for column in ("overseas_sellable", "chengdu_sellable", "overseas_in_transit", "pending_outbound"):
        assert f"SUM({column})" not in sql and f"THEN {column} END)" in sql
    assert "SUM(ebay_quantity_available) site_ebay_available_total" in sql


def test_listing_view_compares_against_every_store_in_the_site():
    view, params = repo._listing_view({"stat_date": STAT_DATE, "accounts": ["a"]})
    assert params == [STAT_DATE], "跨店聚合只受快照日期约束，不受店铺筛选"
    assert "LEFT JOIN site_sku s ON s.site<=>d.site AND s.sku=d.sku" in view
    assert "s.site_price_usd_min=0 THEN NULL" in view
    assert "WHEN d.inventory_matched=1 THEN COALESCE(s.site_oversell,0) ELSE 0 END" in view
    where, values = repo._filters({"site_oversell": True, "out_of_stock_listed": True})
    assert where == " WHERE site_oversell=1 AND out_of_stock_listed=1" and values == []


def test_summary_applies_flag_filters_after_grouping(monkeypatch):
    captured = {}
    monkeypatch.setattr(repo, "_query", lambda sql, params: captured.update(sql=sql, params=list(params)) or [])
    repo.summary_rows({"accounts": ["a"], "site_oversell": True}, limit=10, offset=0)
    sql = captured["sql"]
    grouped, outer = sql.rsplit(") g", 1)
    assert "seller_account IN (%s)" in grouped and "site_oversell=1" not in grouped.split("GROUP BY")[-1]
    assert outer.startswith(" WHERE site_oversell=1")
    # SKU 维度的跨店对比列取自 site_sku（全站点），与明细的同站点对比同一口径
    assert "MAX(site_price_usd_min) price_usd_min,MAX(site_price_usd_max) price_usd_max" in sql
    assert "MAX(site_store_count) store_count" in sql
    assert "COUNT(DISTINCT seller_account) store_count" not in sql
    assert "MIN(price_usd) price_usd_min" not in sql
    # 行级汇总列仍按筛选后的刊登算
    assert "SUM(ebay_quantity_available) ebay_quantity_available" in sql
    assert "COUNT(*) listing_count" in sql
    assert captured["params"] == ["a"]


def test_store_rows_count_distinct_oversell_skus_and_ignore_status_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(repo, "_query", lambda sql, params: captured.update(sql=sql, params=list(params)) or [])
    repo.store_rows({"sites": ["DE"], "accounts": ["a"], "statuses": ["健康"], "keyword": "x"})
    sql = captured["sql"]
    assert "COUNT(DISTINCT CASE WHEN site_oversell=1 THEN sku END) site_oversell_sku_count" in sql
    assert "GROUP BY seller_account,site ORDER BY seller_account,site" in sql
    assert captured["params"] == ["DE", "a"]


# ----------------------------------------------------------- 汇率按币种回退
class _SqliteCursor:
    """把同一段 rate_lookup SQL 交给内存 sqlite 执行（%s → ?），验证回退口径；不连真实 MySQL。"""

    def __init__(self, rows):
        import sqlite3

        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            f"CREATE TABLE {repo.RATE_TABLE} (rate_month TEXT, currency_code TEXT, my_rate REAL)")
        self.connection.executemany(f"INSERT INTO {repo.RATE_TABLE} VALUES (?,?,?)", rows)
        self.result = []

    def execute(self, sql, params=()):
        self.result = [dict(row) for row in self.connection.execute(sql.replace("%s", "?"), params)]

    def fetchall(self):
        return self.result


def test_rates_fall_back_per_currency_to_the_latest_published_month():
    cursor = _SqliteCursor([
        ("2026-07", "USD", 7.10), ("2026-07", "EUR", 7.80), ("2026-07", "GBP", 9.00),
        ("2026-08", "USD", 7.15),                       # 8 月只出了 USD
        ("2026-12", "EUR", 9.99),                       # 晚于快照月，不能用
        ("2026-08", "GBP", 0),                          # 无效汇率，跳过
    ])
    rates, months = repo.rate_lookup(cursor, "2026-11")
    # 当月（11 月）缺：USD 用上月最近的 8 月；EUR、GBP 在 8 月缺或无效，各自跳到 7 月
    assert months == {"USD": "2026-08", "EUR": "2026-07", "GBP": "2026-07"}
    assert rates["USD"] == Decimal("7.15") and rates["EUR"] == Decimal("7.8")
    assert repo.rates(cursor, "2026-11") == rates


def test_rates_use_the_snapshot_month_when_it_is_published():
    cursor = _SqliteCursor([("2026-10", "USD", 7.0), ("2026-11", "USD", 7.2), ("2026-11", "EUR", 7.9)])
    rates, months = repo.rate_lookup(cursor, "2026-11")
    assert months == {"USD": "2026-11", "EUR": "2026-11"}
    assert rates["USD"] == Decimal("7.2")


def test_rates_without_any_published_month_stay_missing_so_price_usd_is_null():
    cursor = _SqliteCursor([("2026-12", "USD", 7.3)])
    rates, months = repo.rate_lookup(cursor, "2026-11")
    assert rates == {} and months == {}
    assert service.price_usd(Decimal("10"), "EUR", rates) is None


def test_sku_listings_flags_out_of_stock_listed_with_the_same_rule_as_detail(monkeypatch):
    captured = {}
    monkeypatch.setattr(repo, "_query", lambda sql, params: captured.update(sql=sql) or [])
    repo.sku_listings("TYT-1-1")
    assert f"{repo.out_of_stock_listed_sql()} out_of_stock_listed" in captured["sql"]
    view, _ = repo._listing_view({})
    assert f"{repo.out_of_stock_listed_sql('d.')} out_of_stock_listed" in view, "与明细同一段判定"


@pytest.mark.parametrize("matched,overseas,chengdu,available,expected", [
    (1, 0, 0, 5, 1),      # 已匹配、仓里 0、eBay 还在卖 -> 断货在售
    (1, 0, None, 5, 1),   # 成都缺值按 0
    (1, 0, 3, 5, 0),      # 成都还有货
    (1, 2, 0, 5, 0),      # 谷仓还有货
    (1, 0, 0, 0, 0),      # eBay 也不卖了
    (0, None, None, 5, 0),  # 未匹配不判
])
def test_out_of_stock_listed_rule(matched, overseas, chengdu, available, expected):
    import sqlite3

    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE t (inventory_matched INT, overseas_sellable INT,"
                       " chengdu_sellable INT, ebay_quantity_available INT)")
    connection.execute("INSERT INTO t VALUES (?,?,?,?)", (matched, overseas, chengdu, available))
    value = connection.execute(f"SELECT {repo.out_of_stock_listed_sql()} FROM t").fetchone()[0]
    connection.close()
    assert value == expected
