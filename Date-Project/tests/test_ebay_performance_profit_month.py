from io import BytesIO

import pandas as pd
import pytest

from backend.parsers.ebay_performance_profit_parser import parse_ebay_profit_excel
from backend.parsers.performance_common import normalize_text
from backend.parsers.performance_owner_rule_parser import parse_owner_rule_excel
from backend.repositories.performance_repository import normalize_principal


def _workbook(frame: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def _profit_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "SKU": "BMW-10001-0001",
                "图片": "https://example.test/bmw.jpg",
                "是否多属性": "否",
                "利润": 10,
                "商品销售额": 100,
                "应收运费": 5,
                "退款金额": 2,
            },
            {
                "SKU": "AMZ-BMW-10001-0001",
                "图片": None,
                "是否多属性": None,
                "利润": 999,
                "商品销售额": 999,
                "应收运费": 0,
                "退款金额": 0,
            },
            {
                "SKU": None,
                "图片": None,
                "是否多属性": None,
                "利润": 1009,
                "商品销售额": 1099,
                "应收运费": 5,
                "退款金额": 2,
            },
            {
                "SKU": "[SKU 未填写]",
                "图片": None,
                "是否多属性": None,
                "利润": -1000,
                "商品销售额": 0,
                "应收运费": 0,
                "退款金额": 0,
            },
            {
                "SKU": "JMH-20001-0001",
                "图片": None,
                "是否多属性": None,
                "利润": 3,
                "商品销售额": 30,
                "应收运费": 0,
                "退款金额": 0,
            },
            {
                "SKU": "YCL-20001-0001",
                "图片": None,
                "是否多属性": None,
                "利润": 4,
                "商品销售额": 40,
                "应收运费": 0,
                "退款金额": 0,
            },
            {
                "SKU": "OTH-20001-0001",
                "图片": None,
                "是否多属性": None,
                "利润": 5,
                "商品销售额": 50,
                "应收运费": 0,
                "退款金额": 0,
            },
        ]
    )


def test_explicit_stat_month_wins_over_download_month_and_filters_non_ebay_rows():
    parsed = parse_ebay_profit_excel(
        _workbook(_profit_frame()),
        "SKU利润表-20260901090424.xlsx",
        "batch-1",
        stat_month="2026-08",
    )

    assert parsed["stat_month"] == "2026-08"
    # AMZ 开头的 SKU 由 eBay 导出提供，销量与实际达成都要计入，因此不过滤；
    # 只有空 SKU 和 [SKU 未填写] 这类汇总行会被跳过。
    assert {row["sku"] for row in parsed["rows"]} == {
        "BMW-10001-0001",
        "AMZ-BMW-10001-0001",
        "JMH-20001-0001",
        "YCL-20001-0001",
        "OTH-20001-0001",
    }
    assert all(row["stat_month"] == "2026-08" for row in parsed["rows"])
    assert all(row["sold_quantity"] == 0 for row in parsed["rows"])


def test_optional_sold_quantity_is_persisted_and_keeps_amz_rows():
    """售出数按行保留，AMZ开头的SKU一并计入月度库存销量。"""
    frame = _profit_frame().iloc[:2].copy()
    frame["售出数"] = [7, 999]

    parsed = parse_ebay_profit_excel(
        _workbook(frame),
        "ebay-profit.xlsx",
        "batch-sold",
        stat_month="2026-08",
    )

    assert len(parsed["rows"]) == 2
    by_sku = {row["sku"]: row["sold_quantity"] for row in parsed["rows"]}
    assert str(by_sku["BMW-10001-0001"]) == "7.000000"
    assert str(by_sku["AMZ-BMW-10001-0001"]) == "999.000000"
    assert parsed["totals"]["sold_quantity"] == "1006.000000"


def test_old_caller_can_still_fall_back_to_filename_month():
    parsed = parse_ebay_profit_excel(
        _workbook(_profit_frame().iloc[:1]),
        "ebay-profit-202607.xlsx",
        "batch-2",
    )
    assert parsed["stat_month"] == "2026-07"


@pytest.mark.parametrize("stat_month", ["", "2026-13", "202608", "26-08"])
def test_explicit_invalid_stat_month_is_rejected(stat_month):
    with pytest.raises(ValueError, match="YYYY-MM"):
        parse_ebay_profit_excel(
            _workbook(_profit_frame().iloc[:1]),
            "ebay-profit-without-month.xlsx",
            "batch-3",
            stat_month=stat_month,
        )


def test_nan_owner_cells_are_empty_and_future_empty_month_is_not_imported():
    owner_file = _workbook(
        pd.DataFrame(
            [{"品牌": "BMW", "202608负责人": "方黎力", "202609负责人": float("nan")}]
        )
    )

    parsed = parse_owner_rule_excel(
        owner_file, "eBay负责人.xlsx", "ebay", "owner-batch"
    )

    assert normalize_text(float("nan")) == ""
    assert normalize_text(pd.NA) == ""
    assert normalize_principal(float("nan")) == "未分配"
    assert normalize_text("NULL") == ""
    assert normalize_principal("null") == "未分配"
    assert parsed["months"] == ["2026-08"]
    assert [(row["stat_month"], row["principal_name"]) for row in parsed["rules"]] == [
        ("2026-08", "方黎力")
    ]
