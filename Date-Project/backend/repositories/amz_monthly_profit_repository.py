"""AMZ 月度利润表的取数与落库。

    ods_lingxing_profit_report_msku_month     领星利润报表-MSKU（结算、按月汇总、人民币），按月整月替换
    ods_lingxing_profit_report_seller_month   领星利润报表-店铺（同口径），只用来核对 MSKU 拉全了没有
    fin_amz_monthly_profit_adjustment         手工补充费用（按月、按末级行、按列）
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from itertools import islice
from typing import Any

from backend.database import db_connection

MSKU_TABLE = "ods_lingxing_profit_report_msku_month"
SELLER_TABLE = "ods_lingxing_profit_report_seller_month"
ADJUSTMENT_TABLE = "fin_amz_monthly_profit_adjustment"

QTY_COLUMNS = ("sales_qty", "refunds_qty", "returns_qty")
MONEY_COLUMNS = (
    "sales_amount", "shipping_credits", "promotional_rebates", "fba_inventory_credit",
    "cash_on_delivery", "other_in_amount", "sales_refunds", "fee_refunds", "platform_fee",
    "fba_delivery_fee", "other_transaction_fees", "ads_cost", "promotion_fee", "storage_fee",
    "inbound_convenience_fee", "international_inbound_fee", "adjustment_fee", "platform_other_fee",
    "custom_order_fee", "sales_tax", "sales_tax_refund", "market_tax", "market_tax_refund",
    "purchase_cost", "first_leg_cost", "other_cost", "gross_profit", "transit_loss",
)
MSKU_COLUMNS = (
    "stat_month", "sid", "msku", "store_name", "local_sku", "local_name", "currency_code",
    *QTY_COLUMNS, *MONEY_COLUMNS, "other_fees_json", "sync_batch_id", "pulled_at",
)
SELLER_COLUMNS = (
    "stat_month", "sid", "store_name", "country_code", "currency_code", "sales_qty",
    "sales_amount", "gross_profit", "sync_batch_id", "pulled_at",
)
_BATCH = 500


def _insert(cursor, table: str, columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> int:
    names = ",".join(f"`{column}`" for column in columns)
    marks = ",".join(f"%({column})s" for column in columns)
    sql = f"INSERT INTO `{table}` ({names}) VALUES ({marks})"
    # pymysql 会转义参数字典里的每个值：只留表里的列，避免带上 other_fees 这类非标量字段。
    iterator, inserted = ({column: row.get(column) for column in columns} for row in rows), 0
    while batch := list(islice(iterator, _BATCH)):
        cursor.executemany(sql, batch)
        inserted += len(batch)
    return inserted


def replace_month(month: str, msku_rows: Sequence[dict[str, Any]],
                  seller_rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    """两张源表同一事务整月替换：任何一步失败回滚，原有月份保持不变。"""
    rows = [{**row, "other_fees_json": json.dumps(row.get("other_fees") or {}, ensure_ascii=False)}
            for row in msku_rows]
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{MSKU_TABLE}` WHERE stat_month=%s", (month,))
                deleted = cursor.rowcount
                cursor.execute(f"DELETE FROM `{SELLER_TABLE}` WHERE stat_month=%s", (month,))
                msku = _insert(cursor, MSKU_TABLE, MSKU_COLUMNS, rows)
                seller = _insert(cursor, SELLER_TABLE, SELLER_COLUMNS, seller_rows)
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{MSKU_TABLE}` WHERE stat_month=%s", (month,))
                stored = int((cursor.fetchone() or {}).get("n") or 0)
                if stored != len(rows):
                    raise ValueError(f"AMZ月度利润 MSKU 写入行数校验失败：本次{len(rows)}行，库里{stored}行，已回滚")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"msku_rows": msku, "seller_rows": seller, "deleted_rows": deleted}


def _query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return list(cursor.fetchall())


def months(limit: int = 36) -> list[dict[str, Any]]:
    return _query(
        f"SELECT stat_month,COUNT(*) msku_rows,MAX(pulled_at) pulled_at,MAX(sync_batch_id) sync_batch_id "
        f"FROM `{MSKU_TABLE}` GROUP BY stat_month ORDER BY stat_month DESC LIMIT %s", (int(limit),))


def msku_rows(month: str) -> list[dict[str, Any]]:
    columns = ",".join(f"`{column}`" for column in MSKU_COLUMNS)
    rows = _query(f"SELECT {columns} FROM `{MSKU_TABLE}` WHERE stat_month=%s", (month,))
    for row in rows:
        raw = row.get("other_fees_json")
        row["other_fees"] = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    return rows


def seller_rows(month: str) -> list[dict[str, Any]]:
    return _query(f"SELECT sid,store_name,sales_qty,sales_amount,gross_profit FROM `{SELLER_TABLE}` "
                  "WHERE stat_month=%s", (month,))


# ------------------------------------------------------------ 补充费用
def adjustments(month: str) -> list[dict[str, Any]]:
    return _query(
        f"SELECT id,stat_month,row_code,fee_item,amount,remark,created_by,updated_by,created_at,updated_at "
        f"FROM `{ADJUSTMENT_TABLE}` WHERE stat_month=%s ORDER BY row_code,fee_item,id", (month,))


def adjustment(adjustment_id: int) -> dict[str, Any] | None:
    rows = _query(f"SELECT id,stat_month,row_code,fee_item,amount,remark FROM `{ADJUSTMENT_TABLE}` "
                  "WHERE id=%s", (int(adjustment_id),))
    return rows[0] if rows else None


def insert_adjustment(row: dict[str, Any]) -> int:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO `{ADJUSTMENT_TABLE}` (stat_month,row_code,fee_item,amount,remark,created_by,updated_by) "
            "VALUES (%(stat_month)s,%(row_code)s,%(fee_item)s,%(amount)s,%(remark)s,%(operator)s,%(operator)s)",
            row)
        connection.commit()
        return int(cursor.lastrowid)


def update_adjustment(adjustment_id: int, row: dict[str, Any]) -> int:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE `{ADJUSTMENT_TABLE}` SET row_code=%(row_code)s,fee_item=%(fee_item)s,amount=%(amount)s,"
            "remark=%(remark)s,updated_by=%(operator)s WHERE id=%(id)s",
            {**row, "id": int(adjustment_id)})
        connection.commit()
        return cursor.rowcount


def delete_adjustment(adjustment_id: int) -> int:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM `{ADJUSTMENT_TABLE}` WHERE id=%s", (int(adjustment_id),))
        connection.commit()
        return cursor.rowcount
