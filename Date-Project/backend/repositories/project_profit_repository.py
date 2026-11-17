"""财务中心「项目利润总表」读写。

本模块的表（见 migrations/20261116_project_profit.sql、20261116_project_profit_amz_upload.sql）：
    fin_project_profit_item         每月 × 组别 × 项目一个值：eBay 列（上传财务 eBay 利润明细表读出）与各组手工项
    fin_project_profit_ebay_upload  每月最后一次上传的 eBay 利润明细表（文件名、上传人、核对数）
    fin_project_profit_amz_msku     AMZ 各列的数据：上传的领星「利润报表-MSKU」手动导出（人民币），按月整月替换
    fin_project_profit_amz_upload   每月最后一次上传的领星利润报表（文件名、上传人、核对数）
领星接口拉取的 ods_lingxing_profit_report_msku_month 仍归 AMZ 月度利润表使用，本模块不再读、也不写。
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

from itertools import islice

from backend.database import db_connection

ITEM_TABLE = "fin_project_profit_item"
UPLOAD_TABLE = "fin_project_profit_ebay_upload"
MSKU_TABLE = "fin_project_profit_amz_msku"
AMZ_UPLOAD_TABLE = "fin_project_profit_amz_upload"
MIGRATION_MESSAGE = ("项目利润总表数据表不存在，请先执行 Date-Project/migrations/20261116_project_profit.sql 与 "
                     "20261116_project_profit_amz_upload.sql")
QTY_COLUMNS = ("sales_qty", "refunds_qty", "returns_qty")
MONEY_COLUMNS = (
    "sales_amount", "shipping_credits", "promotional_rebates", "fba_inventory_credit", "cash_on_delivery",
    "other_in_amount", "sales_refunds", "fee_refunds", "platform_fee", "fba_delivery_fee", "other_transaction_fees",
    "ads_cost", "promotion_fee", "storage_fee", "inbound_convenience_fee", "international_inbound_fee",
    "adjustment_fee", "platform_other_fee", "custom_order_fee", "sales_tax", "sales_tax_refund", "market_tax",
    "market_tax_refund", "purchase_cost", "first_leg_cost", "other_cost", "gross_profit", "removal_cost",
    "transit_loss", "platform_expense",
)
MSKU_COLUMNS = ("stat_month", "store_name", "msku", "local_sku", "local_name", "currency_code",
                *QTY_COLUMNS, *MONEY_COLUMNS, "other_fees_json", "uploaded_at")
_BATCH = 500


def _query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return list(cursor.fetchall())


def msku_rows(month: str) -> list[dict[str, Any]]:
    columns = ",".join(f"`{column}`" for column in MSKU_COLUMNS)
    rows = _query(f"SELECT {columns} FROM `{MSKU_TABLE}` WHERE stat_month=%s", (month,))
    for row in rows:
        raw = row.get("other_fees_json")
        row["other_fees"] = json.loads(raw) if isinstance(raw, (str, bytes)) and raw else (raw or {})
    return rows


def amz_upload(month: str) -> dict[str, Any] | None:
    rows = _query(f"SELECT u.stat_month,u.file_name,u.uploaded_by,u.uploaded_at,u.check_json,"
                  f"(SELECT COUNT(*) FROM `{MSKU_TABLE}` m WHERE m.stat_month=u.stat_month) n "
                  f"FROM `{AMZ_UPLOAD_TABLE}` u WHERE u.stat_month=%s", (month,))
    if not rows:
        return None
    row = rows[0]
    raw = row.get("check_json")
    row["check"] = json.loads(raw) if isinstance(raw, (str, bytes)) and raw else (raw or {})
    return row


def months(limit: int = 36) -> list[str]:
    rows = _query(
        f"SELECT stat_month FROM (SELECT stat_month FROM `{AMZ_UPLOAD_TABLE}` "
        f"UNION SELECT DISTINCT stat_month FROM `{ITEM_TABLE}`) m ORDER BY stat_month DESC LIMIT %s", (int(limit),))
    return [str(row["stat_month"]) for row in rows]


def items(month: str) -> list[dict[str, Any]]:
    return _query(f"SELECT group_code,item_code,amount,source,updated_by,updated_at FROM `{ITEM_TABLE}` "
                  "WHERE stat_month=%s", (month,))


def upload(month: str) -> dict[str, Any] | None:
    rows = _query(f"SELECT stat_month,file_name,uploaded_by,uploaded_at,check_json FROM `{UPLOAD_TABLE}` "
                  "WHERE stat_month=%s", (month,))
    if not rows:
        return None
    row = rows[0]
    raw = row.get("check_json")
    row["check"] = json.loads(raw) if isinstance(raw, (str, bytes)) and raw else (raw or {})
    return row


def save_items(month: str, values: Sequence[tuple[str, str, Any]], operator: str | None, source: str) -> int:
    """values: (group_code, item_code, amount)；amount 为 None 表示清空该项。单事务。"""
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                changed = 0
                for group, item, amount in values:
                    if amount is None:
                        changed += cursor.execute(
                            f"DELETE FROM `{ITEM_TABLE}` WHERE stat_month=%s AND group_code=%s AND item_code=%s",
                            (month, group, item))
                    else:
                        cursor.execute(
                            f"INSERT INTO `{ITEM_TABLE}` (stat_month,group_code,item_code,amount,source,updated_by) "
                            "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE amount=VALUES(amount),"
                            "source=VALUES(source),updated_by=VALUES(updated_by)",
                            (month, group, item, amount, source, operator))
                        changed += 1
            connection.commit()
            return changed
        except Exception:
            connection.rollback()
            raise


def save_upload(month: str, values: Sequence[tuple[str, str, Any]], file_name: str, operator: str | None,
                uploaded_at, check: dict[str, Any]) -> None:
    """eBay 上传：先清掉该月 eBay 列上传类项目，再写新值和上传记录，单事务。"""
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                codes = sorted({item for _group, item, _amount in values})
                if codes:
                    cursor.execute(
                        f"DELETE FROM `{ITEM_TABLE}` WHERE stat_month=%s AND group_code='EBAY' AND item_code IN "
                        f"({','.join(['%s'] * len(codes))})", (month, *codes))
                for group, item, amount in values:
                    if amount is None:
                        continue
                    cursor.execute(
                        f"INSERT INTO `{ITEM_TABLE}` (stat_month,group_code,item_code,amount,source,updated_by) "
                        "VALUES (%s,%s,%s,%s,'UPLOAD',%s)", (month, group, item, amount, operator))
                cursor.execute(
                    f"REPLACE INTO `{UPLOAD_TABLE}` (stat_month,file_name,uploaded_by,uploaded_at,check_json) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (month, str(file_name or "eBay利润明细表.xlsx")[:255], operator, uploaded_at,
                     json.dumps(check, ensure_ascii=False, default=str)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def save_amz_upload(month: str, rows: Sequence[dict[str, Any]], file_name: str, operator: str | None,
                    uploaded_at, check: dict[str, Any]) -> dict[str, int]:
    """领星利润报表上传：整月替换 MSKU 行并写上传记录，单事务；写入行数校验不过则回滚，原数据不变。"""
    names = ",".join(f"`{column}`" for column in MSKU_COLUMNS)
    marks = ",".join(f"%({column})s" for column in MSKU_COLUMNS)
    payload = ({**{column: row.get(column) for column in MSKU_COLUMNS}, "stat_month": month,
                "uploaded_at": uploaded_at,
                "other_fees_json": json.dumps(row.get("other_fees") or {}, ensure_ascii=False, default=str)}
               for row in rows)
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{MSKU_TABLE}` WHERE stat_month=%s", (month,))
                deleted = cursor.rowcount
                inserted = 0
                while batch := list(islice(payload, _BATCH)):
                    cursor.executemany(f"INSERT INTO `{MSKU_TABLE}` ({names}) VALUES ({marks})", batch)
                    inserted += len(batch)
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{MSKU_TABLE}` WHERE stat_month=%s", (month,))
                stored = int((cursor.fetchone() or {}).get("n") or 0)
                if stored != len(rows):
                    raise ValueError(f"领星利润报表写入行数校验失败：文件{len(rows)}行，库里{stored}行，已回滚")
                cursor.execute(
                    f"REPLACE INTO `{AMZ_UPLOAD_TABLE}` (stat_month,file_name,uploaded_by,uploaded_at,check_json) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (month, str(file_name or "利润报表-MSKU.xlsx")[:255], operator, uploaded_at,
                     json.dumps(check, ensure_ascii=False, default=str)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted_rows": deleted, "inserted_rows": inserted}
