"""按历史最大月销与利润率计算产品等级；阈值与业务方Excel公式逐档对齐。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.ebay_inventory_grade_rule import GRADES, calculate_grade
from backend.services.ebay_inventory_workbook import normalize_site


@pytest.mark.parametrize("alias,expected", [
    ("GERMANY", "德国"), ("GB", "英国"), ("UNITED KINGDOM", "英国"),
    ("USA", "美国"), ("UNITED STATES", "美国"), ("FR", "法国"),
    ("德国", "德国"), ("英国", "英国"), ("美国", "美国"),
])
def test_normalize_site_aliases(alias, expected):
    assert normalize_site(alias) == expected


@pytest.mark.parametrize("sales,rate,expected", [
    # K<=4：只有一个档，0.15以下一律E，这一档永远评不到S/A/B。
    (0, "0.9", "D"), (4, "0.15", "D"), (4, "0.1499", "E"), (0, "0", "E"),
    # K<=9：最高只到C。
    (5, "0.15", "C"), (9, "0.1", "D"), (9, "0.05", "E"), (9, "0.049", "E"),
    # K<=14：有A无S，0.3与0.2同为A，0.1与0.05同为D。
    (10, "0.3", "A"), (14, "0.2", "A"), (14, "0.18", "B"), (14, "0.15", "C"),
    (14, "0.1", "D"), (14, "0.05", "D"), (14, "0.0499", "E"),
    # K<=19：0.3起评S，0.1降为C。
    (15, "0.3", "S"), (19, "0.2", "A"), (19, "0.18", "B"), (19, "0.15", "C"),
    (19, "0.1", "C"), (19, "0.05", "D"), (19, "0.04", "E"),
    # K<=29：与上一档同表。
    (20, "0.3", "S"), (29, "0.2", "A"), (29, "0.1", "C"), (29, "0.05", "D"),
    # K>=30：S的门槛降到0.2，且没有0.3档。
    (30, "0.2", "S"), (30, "0.19", "B"), (30, "0.18", "B"), (30, "0.15", "C"),
    (30, "0.1", "C"), (30, "0.05", "D"), (30, "0.0499", "E"), (9999, "1", "S"),
])
def test_grade_matches_business_formula(sales, rate, expected):
    assert calculate_grade(sales, Decimal(rate)) == expected


def test_boundaries_are_inclusive_on_both_axes():
    """公式用的是K<=n与J>=x，边界值必须落在本档，不能滑到下一档。"""
    assert calculate_grade(4, Decimal("0.15")) == "D"      # K=4仍在第一档
    assert calculate_grade(5, Decimal("0.15")) == "C"      # K=5进入第二档
    assert calculate_grade(29, Decimal("0.2")) == "A"      # K=29仍是A
    assert calculate_grade(30, Decimal("0.2")) == "S"      # K=30起同利润率变S


def test_missing_profit_rate_gives_no_grade_instead_of_worst_grade():
    """三月销售额为0时Excel是#DIV/0!，不是"利润率低"，不能落到E。"""
    assert calculate_grade(47, None) is None
    assert calculate_grade(0, None) is None


def test_missing_sales_counts_as_zero_not_as_missing():
    assert calculate_grade(None, Decimal("0.2")) == "D"    # 等同K=0落第一档
    assert calculate_grade(None, Decimal("0.1")) == "E"


def test_negative_profit_rate_is_lowest_grade():
    assert calculate_grade(100, Decimal("-0.5")) == "E"


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity")])
def test_non_finite_profit_rate_gives_no_grade(bad):
    assert calculate_grade(10, bad) is None


def test_accepts_plain_numbers_and_strings():
    assert calculate_grade(10, 0.3) == "A"
    assert calculate_grade("10", "0.3") == "A"


def test_every_returned_grade_is_a_known_level():
    for sales in (0, 5, 12, 17, 25, 40):
        for rate in ("-1", "0", "0.05", "0.1", "0.15", "0.18", "0.2", "0.3", "1"):
            assert calculate_grade(sales, Decimal(rate)) in GRADES
