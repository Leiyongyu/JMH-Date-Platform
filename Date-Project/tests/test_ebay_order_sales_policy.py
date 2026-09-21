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
        db.execute("CREATE TABLE dwd_ebay_sku_analysis_order (site_name TEXT,inventory_sku TEXT,payment_time TEXT,purchase_quantity NUMERIC,shipping_status TEXT)")
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
        db.executemany("INSERT INTO dwd_ebay_sku_analysis_order VALUES ('德国','DAS-10053-0121',?,?,?)", entries)
        # Execute the production SELECT bodies, not a separately rewritten predicate.
        for name, bounds, expected in [
            ("recent_sales", params[:2], 23),
            ("complete_month_sales", params[2:], 126),
        ]:
            body = sql.split(name + " AS (", 1)[1].split("\n        ),", 1)[0]
            body = body.replace("%s", "?").replace("%%", "%")
            actual = db.execute(body, tuple(str(day) for day in bounds)).fetchall()
            assert actual == [("德国", "DAS-10053-0121", expected)]
    finally:
        db.close()
