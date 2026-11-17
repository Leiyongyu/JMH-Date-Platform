"""eBay 月度利润表的取数与落库。

    ods_ebay_finance_transaction      eBay Finances 交易流水（按商品行拆开，美元净额 + 交易币种明细），按店铺整月替换
    ods_goodcang_bill_fee             谷仓账单费用明细（入库 / 仓租 / 订单 / 退货 / 增值 / 理赔返还），按账单整月替换
    fin_ebay_monthly_profit_rate      中行折算价月均值（财务每月录入）
    fin_ebay_monthly_profit_adjustment 手工补充费用（按月、按行、按列）

只读复用：
    ods_ebay_sku_analysis_order_raw            「SKU分析」导入的数字酋长订单：采购成本、头程运费（按平台订单号）
    ods_goodcang_wh_inventory_storage_detail   谷仓仓租明细（每周同步）：按 SKU 分到负责人
    ods_ebay_store_listing_latest              在售刊登：刊登号 → SKU（只挂了刊登号的费用行用）
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from itertools import islice
from typing import Any

from backend.database import db_connection

FINANCE_TABLE = "ods_ebay_finance_transaction"
BILL_TABLE = "ods_goodcang_bill_fee"
RATE_TABLE = "fin_ebay_monthly_profit_rate"
ADJUSTMENT_TABLE = "fin_ebay_monthly_profit_adjustment"
ORDER_COST_TABLE = "ods_ebay_sku_analysis_order_raw"
STORAGE_TABLE = "ods_goodcang_wh_inventory_storage_detail"
LISTING_TABLE = "ods_ebay_store_listing_latest"

FINANCE_COLUMNS = (
    "stat_month", "store_name", "transaction_id", "line_no", "transaction_type", "transaction_status",
    "booking_entry", "category", "transaction_time_utc", "transaction_date_pt", "order_id", "payout_id",
    "fee_type", "memo", "reference_text", "line_item_id", "item_id", "sku", "title", "quantity",
    "payout_currency", "net_amount", "tx_currency", "fx_rate", "gross_amount", "fvf_fixed", "fvf_variable",
    "regulatory_fee", "international_fee", "inad_fee", "below_standard_fee", "other_line_fee", "ebay_tax",
    "sync_batch_id", "pulled_at",
)
BILL_COLUMNS = (
    "stat_month", "bill_number", "sheet_name", "row_no", "account_code", "bill_from", "bill_to",
    "fee_type", "fee_detail", "business_type", "business_no", "related_no", "tracking_no",
    "warehouse_code", "sku", "platform", "currency", "amount", "charge_time", "remark",
    "sync_batch_id", "pulled_at",
)
_BATCH = 500


def _insert(cursor, table: str, columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> int:
    names = ",".join(f"`{column}`" for column in columns)
    marks = ",".join(f"%({column})s" for column in columns)
    sql = f"INSERT INTO `{table}` ({names}) VALUES ({marks})"
    iterator, inserted = ({column: row.get(column) for column in columns} for row in rows), 0
    while batch := list(islice(iterator, _BATCH)):
        cursor.executemany(sql, batch)
        inserted += len(batch)
    return inserted


def _query(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return list(cursor.fetchall())


# ------------------------------------------------------------ 交易流水
def replace_finance_rows(month: str, rows_by_store: dict[str, Sequence[dict[str, Any]]], *,
                         batch_id: str, pulled_at: datetime) -> int:
    """按店铺整月替换（同一事务）：只动这次拉取成功的店铺，失败的店保留上一次的数据。"""
    with db_connection() as connection:
        connection.begin()
        try:
            written = 0
            with connection.cursor() as cursor:
                for store, rows in rows_by_store.items():
                    cursor.execute(f"DELETE FROM `{FINANCE_TABLE}` WHERE stat_month=%s AND store_name=%s",
                                   (month, store))
                    written += _insert(cursor, FINANCE_TABLE, FINANCE_COLUMNS,
                                       ({**row, "sync_batch_id": batch_id, "pulled_at": pulled_at} for row in rows))
            connection.commit()
            return written
        except Exception:
            connection.rollback()
            raise


def finance_rows(month: str) -> list[dict[str, Any]]:
    return _query(f"SELECT * FROM `{FINANCE_TABLE}` WHERE stat_month=%s ORDER BY store_name,transaction_id,line_no",
                  (month,))


def finance_months(limit: int = 36) -> list[dict[str, Any]]:
    return _query(
        f"SELECT stat_month,COUNT(*) rows_,COUNT(DISTINCT store_name) stores,MAX(pulled_at) pulled_at "
        f"FROM `{FINANCE_TABLE}` GROUP BY stat_month ORDER BY stat_month DESC LIMIT %s", (limit,))


def listing_item_skus() -> dict[str, str]:
    """刊登号 → SKU（取最近一次拉取到的）。只挂了刊登号的费用行（刊登费等）靠它找 SKU。"""
    rows = _query(
        f"SELECT item_id,sku FROM (SELECT item_id,sku,ROW_NUMBER() OVER "
        f"(PARTITION BY item_id ORDER BY pulled_at DESC,id DESC) rn FROM `{LISTING_TABLE}` "
        f"WHERE item_id IS NOT NULL AND sku IS NOT NULL AND TRIM(sku)<>'') x WHERE rn=1")
    return {str(row["item_id"]).strip(): str(row["sku"]).strip() for row in rows}


# ------------------------------------------------------------ 谷仓账单
def replace_bill_rows(month: str, rows: Sequence[dict[str, Any]], *, batch_id: str,
                      pulled_at: datetime) -> int:
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{BILL_TABLE}` WHERE stat_month=%s", (month,))
                written = _insert(cursor, BILL_TABLE, BILL_COLUMNS,
                                  ({**row, "sync_batch_id": batch_id, "pulled_at": pulled_at} for row in rows))
            connection.commit()
            return written
        except Exception:
            connection.rollback()
            raise


def bill_rows(month: str) -> list[dict[str, Any]]:
    return _query(f"SELECT * FROM `{BILL_TABLE}` WHERE stat_month=%s", (month,))


def bill_months(limit: int = 36) -> list[dict[str, Any]]:
    return _query(f"SELECT stat_month,COUNT(*) rows_,COUNT(DISTINCT bill_number) bills,MAX(pulled_at) pulled_at "
                  f"FROM `{BILL_TABLE}` GROUP BY stat_month ORDER BY stat_month DESC LIMIT %s", (limit,))


# ------------------------------------------------------------ 订单成本、仓租
def order_costs(month: str) -> dict[str, tuple[Any, Any]]:
    """平台订单号 → (采购成本, 头程运费)，人民币，取「SKU分析」该月导入的数字酋长订单文件（交易级别）。

    该文件一个订单可能有多行，按 2026-10 与财务手工表逐单核对得出的规则汇总：
    - 头程运费是整单的数，每行重复 → 每单取一次（MAX）；
    - 同一 SKU、同一采购成本的重复行：订单行数量 > 1 时是同一行被拆开重复列出，只算一次；
      订单行数量为 1 时是买家拍了几次同一个商品（各自一行），逐行相加。
    """
    rows = _query(
        f"SELECT platform_order_no,inventory_sku,platform_sku_quantity,purchase_cost_cny,first_mile_shipping_cny "
        f"FROM `{ORDER_COST_TABLE}` WHERE stat_month=%s AND platform_order_no IS NOT NULL", (month,))
    groups: dict[str, dict[tuple, list]] = {}
    first_leg: dict[str, Any] = {}
    for row in rows:
        order = str(row["platform_order_no"]).strip()
        key = (row.get("inventory_sku"), row.get("purchase_cost_cny"))
        groups.setdefault(order, {}).setdefault(key, []).append(row)
        value = row.get("first_mile_shipping_cny") or 0
        first_leg[order] = max(first_leg.get(order, value), value)
    out = {}
    for order, items in groups.items():
        purchase = 0
        for (_sku, cost), lines in items.items():
            quantity = lines[0].get("platform_sku_quantity") or 1
            purchase += (cost or 0) * (1 if quantity > 1 else len(lines))
        out[order] = (purchase, first_leg.get(order, 0))
    return out


def order_cost_month_rows(month: str) -> int:
    return int(_query(f"SELECT COUNT(*) n FROM `{ORDER_COST_TABLE}` WHERE stat_month=%s", (month,))[0]["n"])


def storage_rows(month: str) -> list[dict[str, Any]]:
    """当月谷仓仓租明细（按计费日期落在该月）：SKU、仓库、币种、金额（不含税总额）。"""
    year, number = (int(part) for part in month.split("-"))
    start = date(year, number, 1)
    end = date(year + number // 12, number % 12 + 1, 1)
    return _query(
        f"SELECT product_sku,warehouse_code,bill_currency_code currency,SUM(bill_amount) amount "
        f"FROM `{STORAGE_TABLE}` WHERE charge_date>=%s AND charge_date<%s "
        f"GROUP BY product_sku,warehouse_code,bill_currency_code", (start, end))


# ------------------------------------------------------------ 中行汇率
def rates(month: str) -> dict[str, Any]:
    return {row["currency_code"]: row["rate"] for row in
            _query(f"SELECT currency_code,rate FROM `{RATE_TABLE}` WHERE stat_month=%s", (month,))}


def rate_rows(month: str) -> list[dict[str, Any]]:
    return _query(f"SELECT stat_month,currency_code,rate,updated_by,updated_at FROM `{RATE_TABLE}` "
                  f"WHERE stat_month=%s ORDER BY currency_code", (month,))


def upsert_rates(month: str, values: dict[str, Any], operator: str | None) -> int:
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                for currency, rate in values.items():
                    cursor.execute(
                        f"INSERT INTO `{RATE_TABLE}` (stat_month,currency_code,rate,updated_by) VALUES (%s,%s,%s,%s) "
                        f"ON DUPLICATE KEY UPDATE rate=VALUES(rate),updated_by=VALUES(updated_by)",
                        (month, currency, rate, operator))
            connection.commit()
            return len(values)
        except Exception:
            connection.rollback()
            raise


# ------------------------------------------------------------ 补充费用
def adjustments(month: str) -> list[dict[str, Any]]:
    return _query(f"SELECT id,stat_month,row_code,fee_item,amount,remark,created_by,updated_by,created_at,updated_at "
                  f"FROM `{ADJUSTMENT_TABLE}` WHERE stat_month=%s ORDER BY id", (month,))


def adjustment(adjustment_id: int) -> dict[str, Any] | None:
    rows = _query(f"SELECT * FROM `{ADJUSTMENT_TABLE}` WHERE id=%s", (adjustment_id,))
    return rows[0] if rows else None


def insert_adjustment(row: dict[str, Any]) -> int:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO `{ADJUSTMENT_TABLE}` (stat_month,row_code,fee_item,amount,remark,created_by,updated_by) "
            f"VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (row["stat_month"], row["row_code"], row["fee_item"], row["amount"], row["remark"],
             row["operator"], row["operator"]))
        connection.commit()
        return int(cursor.lastrowid)


def update_adjustment(adjustment_id: int, row: dict[str, Any]) -> None:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE `{ADJUSTMENT_TABLE}` SET row_code=%s,fee_item=%s,amount=%s,remark=%s,updated_by=%s WHERE id=%s",
            (row["row_code"], row["fee_item"], row["amount"], row["remark"], row["operator"], adjustment_id))
        connection.commit()


def delete_adjustment(adjustment_id: int) -> bool:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM `{ADJUSTMENT_TABLE}` WHERE id=%s", (adjustment_id,))
        connection.commit()
        return bool(cursor.rowcount)
