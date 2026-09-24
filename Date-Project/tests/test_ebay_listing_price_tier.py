"""eBay 在售刊登 ODS->DWD->DWS 分层、以及基于它的价格结构报表与两张图。"""
from decimal import Decimal
from fractions import Fraction
from unittest.mock import MagicMock

import pytest

from backend.repositories import ebay_listing_price_repository as repo
from backend.services import ebay_price_tier_service as api
from backend.services import listing_price_tier_service as engine


# ------------------------------------------------------------------ 换汇

RATES = {"USD": (Decimal("6.7787"), "2026-09"),
         "EUR": (Decimal("7.8397"), "2026-09"),
         "GBP": (Decimal("9.1195"), "2026-09")}


def test_usd_listing_bypasses_fx_entirely():
    """原币就是美元时一步汇率都不经过，汇率表有没有都不影响它。"""
    usd, own, denominator = repo._usd_price(Decimal("49.99"), "USD", {})
    assert usd == Fraction(Decimal("49.99")) and own == (Decimal(1), "")
    assert denominator == (Decimal(1), "")


def test_other_currency_goes_through_rate_org_both_ways():
    """美元价 = 原币价 × rate_org(原币) ÷ rate_org(USD)。"""
    usd, own, denominator = repo._usd_price(Decimal("10"), "EUR", RATES)
    assert usd == Fraction(10) * Fraction(Decimal("7.8397")) / Fraction(Decimal("6.7787"))
    assert own[1] == "2026-09" and denominator[1] == "2026-09"
    # 11.5 上下，确实比欧元原价高
    assert Decimal("11.5") < Decimal(usd.numerator) / Decimal(usd.denominator) < Decimal("11.6")


def test_missing_rate_returns_none_so_the_row_can_be_counted_not_guessed():
    usd, _own, _denominator = repo._usd_price(Decimal("10"), "PLN", RATES)
    assert usd is None


def test_fx_is_exact_rational_so_tier_boundaries_do_not_flip():
    """原币÷美元几乎必然是无限循环小数；提前四舍五入会让压在边界上的价格翻档。

    构造一个换算后恰好等于 20 的价格：20 × rate(USD) / rate(EUR)。
    左闭右开，20 必须落到「20-50」这一档，不能因为算成 19.999999 掉进「5-20」。
    """
    price = Decimal(20) * Decimal("6.7787") / Decimal("7.8397")
    usd, _o, _d = repo._usd_price(price, "EUR", RATES)
    # Decimal 除法本身有截断，这里比的是"没有因为链路上再截一刀而掉档"
    assert engine.tier_index(usd, "USD") + 1 in (2, 3)
    assert engine.tier_index(Fraction(20), "USD") + 1 == 3


def test_rate_lookup_falls_back_per_currency_not_globally():
    """每个币种各自回退到自己最近一个有正值的月份，不取未来月份。"""
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"currency_code": " eur ", "rate_month": "2026-08", "rate": Decimal("7.8")},
        {"currency_code": "USD", "rate_month": "2026-09", "rate": Decimal("6.7")}]
    rates = repo.rates_for(cursor, "2026-09")
    assert rates["EUR"] == (Decimal("7.8"), "2026-08")
    assert rates["USD"] == (Decimal("6.7"), "2026-09")
    sql, args = cursor.execute.call_args[0]
    assert "rate_month <= %s" in sql and "MAX(x.rate_month)" in sql
    assert args == ("2026-09", "2026-09")


# ------------------------------------------------------------ 清洗层 SQL

def test_variations_are_expanded_and_parent_row_is_not_double_counted():
    """多规格刊登按变体逐个展开；父级那行只在没有变体时才用。

    不拆会把 N 个SKU塌缩成 1 个，而且各变体价格不同，分档也会错。
    """
    assert "JSON_TABLE" in repo._CANDIDATES_CTE
    assert "l.variations_json IS NULL" in repo._CANDIDATES_CTE
    assert "l.variations_json IS NOT NULL" in repo._CANDIDATES_CTE


def test_dirty_rows_are_dropped_by_the_same_condition_that_counts_them():
    """过滤条件只有一份：丢弃计数和实际过滤分叉的话，报的就不是真丢的那些行。"""
    assert repo._CLEAN_WHERE in repo._INSERT_DWD
    for fragment in ("raw_sku", "raw_site", "raw_price"):
        assert fragment in repo._COUNT_CANDIDATES


def test_insert_puts_the_cte_after_insert_into_because_mysql_requires_it():
    """MySQL 不接受 WITH 写在 INSERT 前面（那是 PostgreSQL 写法），会直接1064。"""
    assert repo._INSERT_DWD.strip().startswith("INSERT INTO")
    assert repo._INSERT_DWD.index("INSERT INTO") < repo._INSERT_DWD.index("WITH candidates")


def test_union_branches_force_one_collation():
    """ODS 是 utf8mb4_bin，JSON_TABLE 取出来是另一套；不显式指定会报 1271。"""
    assert repo._CANDIDATES_CTE.count("COLLATE utf8mb4_unicode_ci") >= 8


# ------------------------------------------------------------ 汇总层去重

def dwd_rows(*rows):
    return [dict(seller_user_id=u, seller_account=a, site=s, sku=k,
                 currency=c, price_original=Decimal(p))
            for u, a, s, k, c, p in rows]


def build_dws(monkeypatch, rows, rates=RATES):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = {"rows_": None, "shops": 1, "skus": 1}
    monkeypatch.setattr(repo, "rates_for", lambda cur, month: rates)
    written = []
    cursor.executemany.side_effect = lambda sql, values: written.extend(values)

    def fetchone():
        return {"rows_": len(written), "shops": 1, "skus": 1}
    cursor.fetchone.side_effect = fetchone
    result = repo.build_dws(cursor, "2026-09", "batch", "now")
    return written, result


def test_same_shop_site_sku_keeps_only_the_cheapest_listing(monkeypatch):
    """同一店铺同一站点同一SKU挂多条时只留最低价，并记下合并了几条。

    每条都留的话，铺得多的SKU会在档位占比里被重复计。
    """
    written, result = build_dws(monkeypatch, dwd_rows(
        ("u1", "shopA", "DE", "SKU-1", "USD", "80"),
        ("u1", "shopA", "DE", "SKU-1", "USD", "30"),
        ("u1", "shopA", "DE", "SKU-1", "USD", "55")))
    assert result["dws_rows"] == 1
    row = written[0]
    assert row[6] == Decimal("30")          # price_original
    assert row[8] == 3                      # tier_no: 20-50
    assert row[13] == 3                     # listing_count


def test_different_sites_stay_separate_rows(monkeypatch):
    written, result = build_dws(monkeypatch, dwd_rows(
        ("u1", "shopA", "DE", "SKU-1", "EUR", "30"),
        ("u1", "shopA", "UK", "SKU-1", "GBP", "30")))
    assert result["dws_rows"] == 2
    assert {row[3] for row in written} == {"DE", "UK"}


def test_rows_without_a_rate_are_counted_not_silently_dropped(monkeypatch):
    _written, result = build_dws(monkeypatch, dwd_rows(
        ("u1", "shopA", "PL", "SKU-1", "PLN", "30")))
    assert result["dropped_no_rate"] == 1
    assert result["missing_currencies"] == ["PLN"]


def test_write_count_mismatch_raises_instead_of_losing_rows_quietly(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = dwd_rows(("u1", "shopA", "DE", "SKU-1", "USD", "30"))
    cursor.fetchone.return_value = {"rows_": 0, "shops": 0, "skus": 0}
    monkeypatch.setattr(repo, "rates_for", lambda cur, month: RATES)
    with pytest.raises(ValueError, match="行数校验失败"):
        repo.build_dws(cursor, "2026-09", "batch", "now")


# ------------------------------------------------------ 报表：月份与店铺

def breakdown(monkeypatch, shop_rows, site_rows=(), months=("2026-09", "2026-08"),
              shops=("shopA", "shopB"), distinct=0, state=None, stale=False):
    captured = {}

    def fake(stat_month="", shop=""):
        captured["args"] = (stat_month, shop)
        return dict(stat_month=stat_month or months[0], months=list(months), shops=list(shops),
                    shop_rows=list(shop_rows), site_rows=list(site_rows),
                    distinct_sku_count=distinct, stale=stale,
                    state=state or {"rate_month": "2026-09", "ods_rows": 18013,
                                    "computed_at": "2026-09-24 10:00:00"},
                    rates={"EUR": "7.8397"}, rate_months={"EUR": "2026-09"})
    monkeypatch.setattr(repo, "tier_breakdown", fake)
    return captured


def shop_tier(shop, tier_no, count):
    return {"seller_account": shop, "tier_no": tier_no, "sku_count": count}


def site_tier(shop, site, tier_no, count, currencies="EUR"):
    return {"seller_account": shop, "site": site, "tier_no": tier_no,
            "sku_count": count, "currencies": currencies}


def test_report_groups_by_shop_with_percent(monkeypatch):
    breakdown(monkeypatch, [shop_tier("shopA", 2, 2), shop_tier("shopA", 3, 6),
                            shop_tier("shopB", 3, 1)])
    result = api.read_report()
    assert result["state"] == "READY" and result["shop_count"] == 2
    assert result["total_sku_count"] == 9
    top = result["items"][0]
    assert top["store_name"] == "shopA" and top["group_sku_count"] == 8
    assert [t["sku_count"] for t in top["tiers"]] == [0, 2, 6, 0, 0, 0, 0]
    # 占比按本店铺的归档SKU总数算，不是全平台。
    assert top["tiers"][1]["sku_percent"] == "25.00"
    assert top["tiers"][2]["sku_percent"] == "75.00"


def test_site_children_come_back_so_the_row_can_expand(monkeypatch):
    """在售刊登有站点字段，站点明细是真数据，不是和店铺行同值的占位。"""
    breakdown(monkeypatch, [shop_tier("shopA", 3, 2)],
              [site_tier("shopA", "DE", 3, 2), site_tier("shopA", "UK", 3, 1, "GBP")])
    result = api.read_report()
    children = result["items"][0]["children"]
    assert [c["site"] for c in children] == ["DE", "UK"]
    assert children[1]["currencies"] == ["GBP"]
    # 店铺行按SKU去重（2），站点行各站点分别计（2+1），两者本来就不相等。
    assert result["items"][0]["group_sku_count"] == 2
    assert sum(c["group_sku_count"] for c in children) == 3
    assert result["site_group_count"] == 2


def test_month_and_shop_are_passed_through(monkeypatch):
    captured = breakdown(monkeypatch, [shop_tier("shopA", 2, 1)])
    api.read_report("2026-07", "shopA")
    assert captured["args"] == ("2026-07", "shopA")


def test_month_options_returned_so_the_page_can_offer_history(monkeypatch):
    breakdown(monkeypatch, [shop_tier("shopA", 2, 1)])
    result = api.read_report()
    assert result["months"] == ["2026-09", "2026-08"]
    assert result["shops"] == ["shopA", "shopB"]


def test_empty_source_reports_empty_and_says_what_to_run(monkeypatch):
    monkeypatch.setattr(repo, "tier_breakdown",
                        lambda stat_month="", shop="": dict(stat_month="", months=[], shops=[],
                                                            shop_rows=[], site_rows=[],
                                                            distinct_sku_count=0, state={},
                                                            rates={}, rate_months={}, stale=False))
    result = api.read_report()
    assert result["state"] == "EMPTY" and result["items"] == []
    assert "每月同步" in result["message"]


def test_report_declares_usd_and_carries_the_fx_month(monkeypatch):
    """页面靠 target_currency 判口径；换汇回来了，汇率月份必须跟着报表走。"""
    breakdown(monkeypatch, [shop_tier("shopA", 2, 1)])
    result = api.read_report()
    assert result["target_currency"] == "USD" and result["version"] == engine.USD_VERSION
    assert result["rate_month"] == "2026-09" and result["rate_field"] == "rate_org"
    assert result["rates"] == {"EUR": "7.8397"}


def test_source_pulled_again_marks_the_report_stale(monkeypatch):
    breakdown(monkeypatch, [shop_tier("shopA", 2, 1)], stale=True)
    assert api.read_report()["stale"] is True


def test_cleaning_losses_surface_on_the_report(monkeypatch):
    """清洗丢了多少行必须看得见，页面那条异常提示读的就是这几个数。"""
    breakdown(monkeypatch, [shop_tier("shopA", 2, 1)],
              state={"dropped_no_sku": 3, "dropped_no_site": 1, "dropped_bad_price": 2,
                     "dropped_no_rate": 4, "missing_currencies": "PLN,SEK",
                     "rate_month": "2026-09"})
    result = api.read_report()
    assert result["missing_sku_rows"] == 3
    assert result["invalid_price_rows"] == 3        # 空站点 + 价格异常
    assert result["missing_rate_rows"] == 4
    assert result["missing_currencies"] == ["PLN", "SEK"]


def test_unknown_tier_number_is_refused(monkeypatch):
    breakdown(monkeypatch, [shop_tier("shopA", 9, 1)])
    with pytest.raises(ValueError, match="档位异常"):
        api.read_report()


def test_refresh_runs_both_etls_then_reads(monkeypatch):
    """刷新既要重跑刊登三层，也要重算飞书那张不良交易量表。"""
    from backend.repositories import ebay_sku_unit_price_repository as unit_price
    calls = []
    monkeypatch.setattr(repo, "refresh", lambda months=None: calls.append("listing") or {"dws_rows": 9})
    monkeypatch.setattr(unit_price, "refresh", lambda months=None: calls.append("defect") or {"rows": 5})
    breakdown(monkeypatch, [shop_tier("shopA", 2, 1)])
    result = api.refresh_report("2026-08")
    assert calls == ["defect", "listing"]
    assert result["etl"] == {"dws_rows": 9} and result["defect_refresh"] == {"rows": 5}


# -------------------------------------------------------------- 产品结构

def structure(monkeypatch, sales=(), defects=(), tiers=None, used=None, years=("2026",)):
    monkeypatch.setattr(repo, "structure_years", lambda cur: list(years))
    monkeypatch.setattr(repo, "sales_by_sku", lambda cur, year=None: list(sales))
    monkeypatch.setattr(repo, "defect_by_sku", lambda cur, year=None: list(defects))
    monkeypatch.setattr(repo, "sku_tier_lookup",
                        lambda cur, wanted: (tiers or {}, used or {m: m for m in wanted}))
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr("backend.services.ebay_price_tier_service.db_connection", lambda: context)
    return api.product_structure("2026")


def sale(month, sku, qty, rows=1, refund=0):
    return {"stat_month": month, "sku": sku, "qty": qty, "order_rows": rows,
            "order_count": rows, "refund_qty": refund}


def defect(month, sku, total, bad):
    return {"stat_month": month, "sku": sku, "total_qty": total, "defect_qty": bad}


def test_sales_share_sums_to_one_per_month(monkeypatch):
    result = structure(monkeypatch,
                       sales=[sale("2026-08", "A", 25), sale("2026-08", "B", 75)],
                       tiers={"2026-08": {"A": {"tier_no": 2}, "B": {"tier_no": 3}}})
    points = {s["label"]: s["points"][0] for s in result["sales"]["series"]}
    assert points["5-20"] == "0.2500" and points["20-50"] == "0.7500"
    assert sum(Decimal(p) for p in points.values() if p) == 1


def test_unmatched_sales_excluded_from_denominator_but_reported(monkeypatch):
    """配不上价格档的销量不塞进任何一档，也不当成0——覆盖率要说得清。"""
    result = structure(monkeypatch,
                       sales=[sale("2026-08", "A", 50), sale("2026-08", "X", 50)],
                       tiers={"2026-08": {"A": {"tier_no": 2}}})
    coverage = result["sales"]["coverage"][0]
    assert coverage["matched_qty"] == 50 and coverage["unmatched_qty"] == 50
    assert coverage["rate"] == "0.5000"
    assert [s["points"][0] for s in result["sales"]["series"]][1] == "1.0000"


def test_month_with_no_matched_sales_is_null_not_zero(monkeypatch):
    result = structure(monkeypatch, sales=[sale("2026-08", "X", 10)], tiers={"2026-08": {}})
    assert all(s["points"][0] is None for s in result["sales"]["series"])


def test_quantities_carry_absolute_numbers_and_refunds(monkeypatch):
    """光看百分比分不清是"卖得多"还是"基数小"；退货量也带出来，好判断毛净差多少。"""
    result = structure(monkeypatch, sales=[sale("2026-08", "A", 40, rows=7, refund=4)],
                       tiers={"2026-08": {"A": {"tier_no": 3}}})
    row = result["sales"]["quantities"][0]
    assert row["tiers"][3] == {"qty": 40, "order_rows": 7, "sku_count": 1}
    assert row["matched_qty"] == 40 and row["matched_orders"] == 7
    assert row["refund_qty"] == 4


def test_defect_rate_is_defect_over_total_with_an_overall_line(monkeypatch):
    result = structure(monkeypatch,
                       defects=[defect("2026-08", "A", 100, 10), defect("2026-08", "B", 100, 30)],
                       tiers={"2026-08": {"A": {"tier_no": 2}, "B": {"tier_no": 3}}})
    by_label = {s["label"]: s["points"][0] for s in result["series"]}
    assert by_label["5-20"] == "0.1000" and by_label["20-50"] == "0.3000"
    assert by_label["总体"] == "0.2000"


def test_overall_line_includes_skus_without_a_price_tier(monkeypatch):
    """总体线问的是整体不良率，不该因为某个SKU没挂在售刊登就被排除。"""
    result = structure(monkeypatch,
                       defects=[defect("2026-08", "A", 100, 10), defect("2026-08", "X", 100, 50)],
                       tiers={"2026-08": {"A": {"tier_no": 2}}})
    by_label = {s["label"]: s["points"][0] for s in result["series"]}
    assert by_label["总体"] == "0.3000"
    assert by_label["5-20"] == "0.1000"


def test_every_tier_gets_a_series_even_with_no_data(monkeypatch):
    result = structure(monkeypatch, defects=[defect("2026-08", "A", 10, 1)],
                       tiers={"2026-08": {"A": {"tier_no": 1}}})
    assert [s["label"] for s in result["series"]] == list(engine.USD_LABELS) + ["总体"]
    assert [s["label"] for s in result["sales"]["series"]] == list(engine.USD_LABELS)


def test_borrowed_price_month_is_stated_in_the_note(monkeypatch):
    """没有当月刊登快照时借用邻近月份的挂牌价，这件事必须写在图下面。"""
    result = structure(monkeypatch, sales=[sale("2026-05", "A", 10)],
                       tiers={"2026-05": {"A": {"tier_no": 2}}},
                       used={"2026-05": "2026-09"})
    assert "2026-05→2026-09" in result["note"]


def test_note_states_the_defect_denominator_caveat(monkeypatch):
    result = structure(monkeypatch, defects=[defect("2026-08", "A", 10, 1)],
                       tiers={"2026-08": {"A": {"tier_no": 1}}})
    assert "只收录有不良交易的刊登" in result["note"]
    assert "rate_org" in result["note"]


# ---------------------------------------------------------- 档位回退取月份

def test_tier_lookup_prefers_the_same_month(monkeypatch):
    monkeypatch.setattr(repo, "months", lambda cursor=None: ["2026-09", "2026-08"])
    monkeypatch.setattr(repo, "sku_tiers", lambda cur, month: {"A": {"tier_no": 1, "month": month}})
    tiers, used = repo.sku_tier_lookup(MagicMock(), ["2026-08", "2026-09"])
    assert used == {"2026-08": "2026-08", "2026-09": "2026-09"}
    assert tiers["2026-08"]["A"]["month"] == "2026-08"


def test_tier_lookup_falls_back_to_the_latest_snapshot_not_after_that_month(monkeypatch):
    """优先用不晚于该月的最近快照；该月之前一个快照都没有才用最早的那个。"""
    monkeypatch.setattr(repo, "months", lambda cursor=None: ["2026-09", "2026-07"])
    monkeypatch.setattr(repo, "sku_tiers", lambda cur, month: {"A": {"tier_no": 1, "month": month}})
    _tiers, used = repo.sku_tier_lookup(MagicMock(), ["2026-05", "2026-08", "2026-10"])
    assert used == {"2026-05": "2026-07", "2026-08": "2026-07", "2026-10": "2026-09"}


def test_tier_lookup_on_an_empty_warehouse_returns_nothing(monkeypatch):
    monkeypatch.setattr(repo, "months", lambda cursor=None: [])
    assert repo.sku_tier_lookup(MagicMock(), ["2026-08"]) == ({}, {})
