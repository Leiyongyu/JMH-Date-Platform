"""eBay SKU美元单价表与产品结构：口径、分档、覆盖策略。不连库。"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.repositories import ebay_sku_unit_price_repository as repo
from backend.services import listing_price_tier_service as engine


def agg(month, shop, sku, amount, qty, defect=1, listings=1, reg="2026-09-23",
        peak_qty=None, peak_defect=None):
    """模拟SQL的输出：price_* 来自该SKU自己最大登记日期那一批，
    total_qty/defect_qty 是整月各批次的最大值。"""
    return {"stat_month": month, "shop": shop, "sku": sku, "reg_date": reg,
            "listing_count": listings,
            "price_amount": None if amount is None else Decimal(amount),
            "price_qty": None if qty is None else Decimal(qty),
            "total_qty": Decimal(peak_qty if peak_qty is not None else qty),
            "defect_qty": Decimal(peak_defect if peak_defect is not None else defect)}


def cursor_with(rows, shops=()):
    """第一次 fetchall 是 shop_aliases 查店铺名，第二次才是聚合结果。"""
    cursor = MagicMock()
    cursor.fetchall.side_effect = [[{"shop": s} for s in shops], rows]
    return cursor


# ------------------------------------------------------------------ 单价口径

def test_unit_price_is_amount_over_qty_per_shop():
    """同一SKU不同店铺单价不同，必须分店铺算——实测FRD-70361-4-0734就是这样。"""
    rows, skipped, _ = repo.aggregate(cursor_with([
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
    rows, _, _ = repo.aggregate(cursor_with([agg("2026-09", "s", "k", amount, qty)]))
    assert rows[0]["tier_no"] == tier
    # 档位逻辑只此一处，与页面分档共用同一套阈值。
    assert rows[0]["tier_no"] == engine.tier_index(rows[0]["unit_price"], "USD") + 1


@pytest.mark.parametrize("amount,qty", [("100", "0"), ("100", None), (None, "5"), ("-1", "5")])
def test_unusable_rows_are_skipped_not_priced_as_zero(amount, qty):
    """总交易量为0算不出单价，丢掉并计数，不拿0冒充价格。"""
    rows, skipped, _ = repo.aggregate(cursor_with([
        agg("2026-09", "s", "k", amount, qty, peak_qty="1", peak_defect="1")]))
    assert rows == [] and skipped == 1


def test_sku_universe_is_the_whole_month_not_just_the_last_batch():
    """SKU全集取整月并集：只看最后一批会漏掉当月出现过、末批没出现的SKU。"""
    assert "ROW_NUMBER() OVER" in repo.AGGREGATE_TEMPLATE and "rn = 1" in repo.AGGREGATE_TEMPLATE
    assert "ORDER BY p.reg_date DESC" in repo.AGGREGATE_TEMPLATE


def test_quantities_take_month_max_never_sum_across_batches():
    """同一店铺SKU每批都重报一次累计数，跨批次相加会翻倍，必须取最大。"""
    assert "MAX(p.total_qty)  OVER" in repo.AGGREGATE_TEMPLATE
    assert "MAX(p.defect_qty) OVER" in repo.AGGREGATE_TEMPLATE


def test_shop_name_whitespace_is_normalised():
    """源表店铺名带首尾空白甚至换行，不清掉会把同一个店铺拆成两个。"""
    assert "CHAR(10)" in repo.SHOP_EXPR and "TRIM(BOTH ',' FROM" in repo.SHOP_EXPR


def test_price_comes_from_that_skus_own_latest_batch_while_qty_is_month_max():
    """单价与交易量来自不同口径：单价同批可比，交易量取整月峰值。"""
    rows, _, _ = repo.aggregate(cursor_with([
        agg("2026-09", "店铺A", "SKU-1", "397.5715", "7", reg="2026-09-16",
            peak_qty="7", peak_defect="2")]))
    row = rows[0]
    assert round(float(row["unit_price"]), 2) == 56.80     # 397.5715 / 7，同一批
    assert float(row["total_qty"]) == 7                    # 整月最大，不是 6+7+7=20
    assert float(row["defect_qty"]) == 2                   # 峰值在中间批次


def test_months_filter_narrows_the_aggregate():
    cursor = cursor_with([])
    repo.aggregate(cursor, ["2026-09"])
    sql, args = cursor.execute.call_args.args
    assert "AND stat_month IN (%s)" in sql and args[-1] == "2026-09"


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

# -------------------------------------------------------------- 店铺改名归一

def aliases_from(names):
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"shop": n} for n in names]
    return repo.shop_aliases(cursor)


def test_renamed_shop_merges_into_the_new_name():
    """业务方在 2026-09-23 那批给店铺加了公司前缀，历史批次仍是短名。

    不归一的话同一个店铺被当成两家，SKU 也被拆成两份（实测9月店铺数虚增到73）。
    """
    aliases, warnings = aliases_from(["Aplus-Shop", "帝蓝泰江-ebay-Aplus-Shop"])
    assert aliases == {"Aplus-Shop": "帝蓝泰江-ebay-Aplus-Shop"} and warnings == []


def test_ambiguous_suffix_is_left_alone_and_reported():
    """一个短名能匹配到多个长名时不合并——宁可少合也不能错合。"""
    aliases, warnings = aliases_from(["shop", "A-shop", "B-shop"])
    assert aliases == {} and len(warnings) == 1 and "shop" in warnings[0]


def test_alias_chain_points_at_the_final_name():
    aliases, _ = aliases_from(["c", "b-c", "a-b-c"])
    # b-c -> a-b-c；c 匹配到两个，属于歧义不合并。
    assert aliases.get("b-c") == "a-b-c"


def test_whitespace_and_leading_comma_cleaned_before_matching():
    """源表有 ' allteile-motor'、', stellar-hub' 这类脏值，不清掉会拆成两个店铺。"""
    assert repo._clean_name("  allteile-motor ") == "allteile-motor"
    assert repo._clean_name(", stellar-hub") == "stellar-hub"
    assert repo._clean_name(chr(10) + ", stellar-hub") == "stellar-hub"


def test_no_aliases_means_plain_cleaning_only():
    """业务方把历史批次改成新名之后短名消失，映射自然变空，SQL退回纯清洗。"""
    sql, params = repo._aggregate_sql({})
    assert params == [] and "CASE" not in sql.split("FROM")[0]


def test_alias_map_becomes_case_expression_with_bound_params():
    sql, params = repo._aggregate_sql({"旧": "新"})
    assert "CASE" in sql and "WHEN %s THEN %s" in sql
    assert params == ["旧", "新"]


def test_placeholder_reg_date_is_excluded():
    """没有真实登记日期的行不参与统计：业务方把空值填成了占位的 1999-01-01，
    混进来会在月份选择器里多出一个「1999-01」的假月份。"""
    assert "b.reg_date >= '{min_reg_date}'" in repo.AGGREGATE_TEMPLATE
    assert repo.MIN_REG_DATE == "2020-01-01"
    sql, _ = repo._aggregate_sql({})
    assert "b.reg_date >= '2020-01-01'" in sql and "b.reg_date IS NOT NULL" in sql


def test_alias_derivation_also_skips_placeholder_rows():
    """占位批次里的旧店铺名不该参与映射推导，否则会把已经改好的名字又拉回去。"""
    import inspect
    source = inspect.getsource(repo.shop_aliases)
    assert "MIN_REG_DATE" in source and "reg_date IS NOT NULL" in source


def test_match_ignores_case_and_separators():
    """改名时大小写与分隔符都不一致，只按原样后缀匹配会漏掉985行。"""
    assert repo._match_key("Ace-autoteile") == repo._match_key("ACE_Autoteile")
    assert repo._match_key("treasures-zone") == repo._match_key("Treasures Zone")
    aliases, warnings = aliases_from(["autoteile-hub", "帝蓝泰江-eBay-Autoteile Hub"])
    assert aliases == {"autoteile-hub": "帝蓝泰江-eBay-Autoteile Hub"} and warnings == []
    aliases, _ = aliases_from(["Ace-autoteile", "ace-autoteile", "ebay-湘彦-ACE_Autoteile"])
    # 仅大小写不同的两个都归到带前缀的那个，而不是互相指。
    assert aliases == {"Ace-autoteile": "ebay-湘彦-ACE_Autoteile",
                       "ace-autoteile": "ebay-湘彦-ACE_Autoteile"}


def test_full_recompute_drops_months_that_no_longer_produce_rows():
    """整表重算时「本次没算出结果」等于「不该存在」。

    按月清理管不到「整个月份消失」：加了登记日期下限后 1999-01 不再产出，
    但它上一次算出的414行没人删，月份选择器里会一直挂着一个假月份。
    """
    import inspect
    source = inspect.getsource(repo.refresh)
    assert "_drop_all_stale" in source and "months is None" in source

