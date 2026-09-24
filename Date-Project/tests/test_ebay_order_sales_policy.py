"""Regression coverage without database writes or external calls."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
import sqlite3

import pandas as pd
import pytest

from backend.services import ebay_sku_analysis_service as orders
from backend.repositories import ebay_inventory_detail_repository as inventory


def order(number="A", status="已发货", quantity=2, sku="DAS-10053-0121"):
    row = dict.fromkeys(orders.ORDER_TEMPLATE_COLUMNS, None)
    row.update({"平台订单号": number, "发货状态": status, "购买数量": quantity,
                "库存SKU": sku, "平台SKU": sku, "付款时间": "2026-09-20 12:00:00",
                "站点": "德国", "币种": "EUR", "汇率": 8,
                "应收货款(订单级别)": 100, "退款金额": 100})
    return row


def test_voided_rows_excluded_before_allocation_but_preserved_for_replacement():
    rows = [order(status="已发货,已作废", quantity=8),
            order(status="已发货,已退款", quantity=2),
            order("B", status=None)]
    valid, replaceable = orders._prepare_order_frame(pd.DataFrame(rows))
    assert len(replaceable) == 3
    assert valid["_quantity"].tolist() == [2, 2]
    assert valid["_weight"].tolist() == [1, 1]
    assert valid["_refund_quantity"].tolist() == [2, 0]
    assert valid["_paid_original"].tolist() == [100, 100]


@pytest.mark.parametrize("statuses", [
    ["已作废"],
    ["已退款,已作废", "已作废,已发货"],
])
def test_all_voided_upload_still_replaces_old_rows(monkeypatch, statuses):
    frame = pd.DataFrame([order(str(i), status=status) for i, status in enumerate(statuses)])
    valid, replaceable = orders._prepare_order_frame(frame)
    assert valid.empty and len(replaceable) == len(statuses)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(orders, "db_connection", lambda: connection)
    result = orders._persist_orders(valid, replaceable, "batch", "orders.xlsx", "Sheet1", "test", len(frame))
    deletes = [call for call in cursor.execute.call_args_list if call.args[0].startswith("DELETE")]
    assert len(deletes) == 2
    assert all("DATE(payment_time)" in call.args[0] for call in deletes)
    assert all(str(i) in deletes[0].args[1] for i in range(len(statuses)))
    assert result["valid_rows"] == 0
    assert result["skipped_rows"] == len(statuses)
    assert result["replaced_order_count"] == len(statuses)
    assert all(not call.args[1] for call in cursor.executemany.call_args_list)
    connection.commit.assert_called_once()


def test_existing_template_and_amz_missing_identifiers_rules_unchanged():
    frame = pd.DataFrame([order(), order("AMZ", sku="amz-123"),
                          order("NO-PAY"), order(""), order("NO-SKU", sku="")])
    frame.loc[2, "付款时间"] = "not a date"
    orders._validate_order_template_columns(frame.columns)
    valid, _ = orders._prepare_order_frame(frame)
    assert valid["_order_no"].tolist() == ["A"]
    with pytest.raises(ValueError, match="格式不正确"):
        orders._validate_order_template_columns(list(frame.columns)[::-1])


@pytest.mark.parametrize("today,start", [
    (date(2026, 9, 21), date(2026, 8, 22)),
    (date(2026, 1, 1), date(2025, 12, 2)),
    (date(2024, 3, 1), date(2024, 1, 31)),
])
def test_recent_window_exactly_30_days_excludes_today(today, start):
    assert inventory._recent_sales_window(today) == (start, today)
    assert (today - start).days == 30


def test_recent_window_uses_beijing_date(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz.utcoffset(None) == timedelta(hours=8)
            return datetime(2026, 9, 20, 16, 5, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(inventory, "datetime", Clock)
    assert inventory._recent_sales_window() == (date(2026, 8, 22), date(2026, 9, 21))


def test_actual_sales_ctes_exclude_voided_and_upper_date_boundary():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    inventory._source_rows(cursor,
        sales_window=(date(2026, 6, 1), date(2026, 9, 1)),
        recent_window=(date(2026, 8, 22), date(2026, 9, 21)))
    sql, params = cursor.execute.call_args.args
    assert params == (date(2026, 8, 22), date(2026, 9, 21), date(2026, 6, 1), date(2026, 9, 1))
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE dwd_ebay_sku_analysis_order (site_name TEXT,inventory_sku TEXT,payment_time TEXT,purchase_quantity NUMERIC,shipping_status TEXT,order_profit_cny NUMERIC,paid_amount_cny NUMERIC,refund_amount_cny NUMERIC)")
        entries = [
            ("2026-08-21 23:59:59", 100, "已发货"),
            ("2026-08-22 00:00:00", 2, "已发货"),
            ("2026-09-20 23:59:59", 3, "已退款"),
            ("2026-09-21 00:00:00", 1000, "已发货"),
            ("2026-09-22 10:00:00", 2000, "已发货"),
            ("2026-09-01 10:00:00", 700, "已发货,已作废,已退款"),
            ("2026-09-02 10:00:00", 5, None),
            ("2026-05-31 23:59:59", 10000, "已发货"),
            ("2026-06-01 00:00:00", 11, "已发货"),
            ("2026-08-31 23:59:59", 13, "已发货"),
            ("2026-07-01 00:00:00", 900, "已作废"),
        ]
        db.executemany("INSERT INTO dwd_ebay_sku_analysis_order VALUES ('德国','DAS-10053-0121',?,?,?,0,0,0)", entries)
        # Execute the production SELECT bodies, not a separately rewritten predicate.
        for name, bounds, expected in [
            ("recent_sales", params[:2], 23),
            ("complete_month_sales", params[2:], 126),
        ]:
            body = sql.split(name + " AS (", 1)[1].split("\n        ),", 1)[0]
            body = body.replace("%s", "?").replace("%%", "%")
            actual = db.execute(body, tuple(str(day) for day in bounds)).fetchall()
            # 本用例只校验作废过滤与日期边界；月度CTE另外带的利润/销售额列
            # 由利润率用例覆盖，这里不比对列数。
            assert [row[:3] for row in actual] == [("德国", "DAS-10053-0121", expected)]
    finally:
        db.close()


# --------------------------------------------------------------- 店铺名称列

def test_platform_account_is_the_first_template_column():
    """数字酋长 2026-09-24 起在最前面加了「平台账号」。

    模板校验是按位置逐列比对的，顺序错了会把整份文件拒掉，所以钉住第一列。
    """
    assert orders.ORDER_TEMPLATE_COLUMNS[0] == "平台账号"
    assert orders.ORDER_TEMPLATE_COLUMNS[1] == "站点"
    assert orders.SOURCE_COLUMN_MAP["平台账号"] == "source_platform_account"


def test_old_template_without_shop_column_is_rejected_pointing_at_column_one():
    """旧模板必须被拒，且报错要指到第1列，不能只说"列数不对"。"""
    old = [c for c in orders.ORDER_TEMPLATE_COLUMNS if c != "平台账号"]
    with pytest.raises(ValueError) as error:
        orders._validate_order_template_columns(old, "旧模板.xlsx")
    assert "第1列应为“平台账号”" in str(error.value)


def test_seller_account_reaches_both_layers():
    """ODS 存源文件原值，DWD 存清洗后的值，两边都要有。

    这一列的值就是 eBay 卖家账号，与 dws_ebay_listing_price_tier.seller_account
    完全相等，所以不需要映射表，DWD 那列也直接叫 seller_account。
    """
    frame = pd.DataFrame([{**order(), "平台账号": "  oyeah-motor  "}])
    valid, _ = orders._prepare_order_frame(frame)
    row = orders._row(valid.iloc[0], "batch", "f.xlsx", "Sheet1")
    assert row["source_platform_account"] == "oyeah-motor"
    assert row["seller_account"] == "oyeah-motor"


@pytest.mark.parametrize("value", [None, "", "  ", "-", "nan"])
def test_missing_shop_becomes_empty_string_not_a_fake_shop(value):
    """旧版文件里确实有空账号的行（实测5951行里369行是空的；改成平台账号后是0行）。

    空串的含义是"这行没有店铺"，按店铺筛时落进"未知店铺"，
    绝不能变成一家叫 nan 或 - 的店。
    """
    frame = pd.DataFrame([{**order(), "平台账号": value}])
    valid, _ = orders._prepare_order_frame(frame)
    assert orders._row(valid.iloc[0], "b", "f", "s")["seller_account"] == ""


def test_account_column_is_declared_in_the_schema_migration():
    """自动补列表里少了它，老库升级上来就没有这两列，上传会直接报字段不存在。"""
    import inspect
    source = inspect.getsource(orders._initialize_tables)
    assert "source_platform_account" in source and "seller_account" in source
    assert "idx_esa_dwd_account_time" in source


def test_the_short_lived_old_column_names_get_renamed_not_duplicated():
    """当天先按「店铺名称」接过一版，跑过那一版的库里有两个旧列名。

    改名而不是新增：两个列名指的是同一件事，留着旧列只会多一份永远是空的
    数据，以后谁都说不清该读哪个。
    """
    assert orders._RENAMED_COLUMNS["dwd_ebay_sku_analysis_order"] == {
        "shop_name": "seller_account"}
    assert orders._RENAMED_COLUMNS["ods_ebay_sku_analysis_order_raw"] == {
        "source_shop_name": "source_platform_account"}
    import inspect
    # 改名必须发生在补列之前，否则旧列还在、新列又被当成缺失加一遍。
    source = inspect.getsource(orders._initialize_tables)
    assert source.index("_rename_legacy_columns") < source.index("for table_name, columns in")
