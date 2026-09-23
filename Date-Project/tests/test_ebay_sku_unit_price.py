"""eBay SKU美元单价表与产品结构：口径、分档、覆盖策略。不连库。"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.repositories import ebay_sku_unit_price_repository as repo
from backend.services import ebay_price_tier_service as api
from backend.services import listing_price_tier_service as engine


def agg(month, shop, sku, amount, qty, defect=1, listings=1, reg="2026-09-23"):
    return {"stat_month": month, "shop": shop, "sku": sku, "reg_date": reg,
            "listing_count": listings, "total_amount": Decimal(amount),
            "total_qty": Decimal(qty), "defect_qty": Decimal(defect)}


def cursor_with(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    return cursor


# ------------------------------------------------------------------ 单价口径

def test_unit_price_is_amount_over_qty_per_shop():
    """同一SKU不同店铺单价不同，必须分店铺算——实测FRD-70361-4-0734就是这样。"""
    rows, skipped = repo.aggregate(cursor_with([
        agg("2026-09", "Celestio-eBay-Allteile-Motor", "FRD-70361-4-0734", "419.826971", "18"),
        agg("2026-09", "帝蓝泰江-ebay-AOE-Master", "FRD-70361-4-0734", "379.822291", "19"),
        agg("2026-09", "ebay-帝蓝泰江pieces_saleshop", "FRD-70361-4-0734", "415.994015", "16"),
    ]))
    assert skipped == 0
    prices = {r["shop"]: round(float(r["unit_price"]), 2) for r in rows}
    assert prices["Celestio-eBay-Allteile-Motor"] == 23.32
    assert prices["帝蓝泰江-ebay-AOE-Master"] == 19.99
    assert prices["ebay-帝蓝泰江pieces_saleshop"] == 26.00
    # 19.99 落「5-20」而 23.32 落「20-50」：不分店铺就会把两个档算成一个。
    tiers = {r["shop"]: r["tier_no"] for r in rows}
    assert tiers["帝蓝泰江-ebay-AOE-Master"] == 2
    assert tiers["Celestio-eBay-Allteile-Motor"] == 3


@pytest.mark.parametrize("amount,qty,tier", [
    ("4.99", "1", 1), ("5", "1", 2), ("19.99", "1", 2), ("20", "1", 3),
    ("100", "2", 4), ("499.99", "1", 6), ("500", "1", 7), ("1000", "1", 7),
])
def test_tier_follows_the_same_bounds_as_the_page(amount, qty, tier):
    rows, _ = repo.aggregate(cursor_with([agg("2026-09", "s", "k", amount, qty)]))
    assert rows[0]["tier_no"] == tier
    # 档位逻辑只此一处，与页面分档共用同一套阈值。
    assert rows[0]["tier_no"] == engine.tier_index(rows[0]["unit_price"], "USD") + 1


@pytest.mark.parametrize("amount,qty", [("100", "0"), ("100", None), (None, "5"), ("-1", "5")])
def test_unusable_rows_are_skipped_not_priced_as_zero(amount, qty):
    """总交易量为0算不出单价，丢掉并计数，不拿0冒充价格。"""
    rows, skipped = repo.aggregate(cursor_with([agg("2026-09", "s", "k", amount or "0", qty or "0")
                                                | {"total_amount": None if amount is None else Decimal(amount),
                                                   "total_qty": None if qty is None else Decimal(qty)}]))
    assert rows == [] and skipped == 1


def test_only_the_latest_batch_of_each_month_is_used():
    """源表每周三更新，一个月有4~5批；SQL用MAX(reg_date)只取该月最新那批。"""
    assert "MAX(reg_date)" in repo._AGGREGATE_SQL
    assert "DATE_FORMAT(reg_date,'%%Y-%%m')" in repo._AGGREGATE_SQL


def test_months_filter_narrows_the_aggregate():
    cursor = cursor_with([])
    repo.aggregate(cursor, ["2026-09"])
    sql, args = cursor.execute.call_args.args
    assert "HAVING l.stat_month IN (%s)" in sql and args == ("2026-09",)


# ------------------------------------------------------------ 分档候选

def test_unit_price_candidates_are_native_usd_so_fx_is_bypassed():
    """金额本来就是美元，标成USD让换汇整条链路短路，不受汇率表影响。"""
    rows = [{"shop": "店铺A", "sku": "SKU-1", "unit_price": Decimal("23.32")}]
    report = engine.summarize(engine.unit_price_candidates(rows), {}, target_currency="USD")
    assert report["missing_currencies"] == [] and report["missing_rate_rows"] == 0
    assert report["total_sku_count"] == 1
    assert report["items"][0]["tiers"][2]["sku_count"] == 1     # 20-50
    assert report["items"][0]["store_name"] == "店铺A"


def test_candidates_carry_a_placeholder_site_so_the_tree_still_renders():
    """源表没有站点字段；占位站点保证店铺下仍有一层子节点，页面结构不变。"""
    rows = [{"shop": "店铺A", "sku": "SKU-1", "unit_price": Decimal("9")}]
    report = engine.summarize(engine.unit_price_candidates(rows), {}, target_currency="USD")
    assert report["items"][0]["children"][0]["site"] == engine.UNIT_PRICE_SITE


def test_usd_version_bumped_so_old_fx_based_snapshots_are_refused():
    """口径从"挂牌价换汇"改成"成交均价"，旧快照必须判过期，不能两套口径画一张图。"""
    assert engine.USD_VERSION >= 5


# -------------------------------------------------------------- 产品结构

def build(monkeypatch, rows, years=("2026",)):
    monkeypatch.setattr(repo, "defect_rate_by_tier", lambda year=None: (rows, list(years)))
    monkeypatch.setitem(__import__("sys").modules, "x", None)
    return api.product_structure("2026")


def row(month, tier, total, defect, skus=1):
    return {"stat_month": month, "tier_no": tier, "sku_count": skus,
            "total_qty": total, "defect_qty": defect}


def test_defect_rate_is_defect_over_total_with_an_overall_line(monkeypatch):
    monkeypatch.setattr(repo, "defect_rate_by_tier", lambda year=None: (
        [row("2026-08", 2, 100, 10), row("2026-08", 3, 100, 30),
         row("2026-09", 2, 200, 10), row("2026-09", 3, 100, 20)], ["2026"]))
    result = api.product_structure("2026")
    assert result["months"] == ["2026-08", "2026-09"]
    by_label = {s["label"]: s["points"] for s in result["series"]}
    assert by_label["5-20"] == ["0.1000", "0.0500"]
    assert by_label["20-50"] == ["0.3000", "0.2000"]
    # 总体线是各档合计，不是各档平均：200/8月 -> 40/200=0.2
    assert by_label["总体"] == ["0.2000", "0.1000"]


def test_month_without_sales_in_a_tier_is_null_not_zero(monkeypatch):
    """分母为0代表这一档当月没有成交，线该断开；画成0会是一条假线。"""
    monkeypatch.setattr(repo, "defect_rate_by_tier", lambda year=None: (
        [row("2026-08", 2, 100, 10), row("2026-09", 3, 50, 5)], ["2026"]))
    result = api.product_structure("2026")
    by_label = {s["label"]: s["points"] for s in result["series"]}
    assert by_label["5-20"] == ["0.1000", None]
    assert by_label["20-50"] == [None, "0.1000"]


def test_every_tier_gets_a_series_even_with_no_data(monkeypatch):
    monkeypatch.setattr(repo, "defect_rate_by_tier", lambda year=None: ([], []))
    result = api.product_structure("")
    # 七档 + 总体
    assert len(result["series"]) == len(engine.USD_LABELS) + 1
    assert [s["label"] for s in result["series"]][:-1] == list(engine.USD_LABELS)
    assert result["months"] == [] and result["years"] == []


def test_note_states_the_denominator_caveat(monkeypatch):
    """口径必须写在返回里：这里的不良率高于eBay官方面板，不能直接对数。"""
    monkeypatch.setattr(repo, "defect_rate_by_tier", lambda year=None: ([], ["2026"]))
    note = api.product_structure("2026")["note"]
    assert "只收录有不良交易的刊登" in note and "eBay官方面板" in note


def test_year_filter_passed_through(monkeypatch):
    seen = []
    monkeypatch.setattr(repo, "defect_rate_by_tier", lambda year=None: (seen.append(year), ([], []))[1])
    api.product_structure(" 2025 ")
    assert seen == ["2025"]
    api.product_structure("")
    assert seen == ["2025", None]
