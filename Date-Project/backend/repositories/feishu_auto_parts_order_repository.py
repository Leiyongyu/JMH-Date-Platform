"""飞书「汽配订单」本地副本：整表替换写入；按站点 + SKU 读未完成的采购单。"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from pymysql.err import ProgrammingError

from backend.database import db_connection

TABLE = "ods_feishu_auto_parts_order"
MIGRATION_MESSAGE = "飞书汽配订单表未部署，请执行 migrations/20261113_feishu_auto_parts_order.sql"
COLUMNS = (
    "record_id", "po", "sku", "warehouse", "platform", "site", "order_status", "quantity",
    "order_amount", "order_date", "expected_ship_date", "apply_date", "purchaser", "product_name",
    "not_purchased_reason", "feishu_updated_at", "sync_batch_id", "synced_at",
)
# 走完采购流程、不再「在路上」的状态；其余（含状态没填）都算未完成。
CLOSED_STATUSES = ("已完成", "已取消")


def missing_table(error: Exception) -> bool:
    return isinstance(error, ProgrammingError) and error.args[0] == 1146 and TABLE in str(error).lower()


def replace_all(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    """同一事务整表替换：任何一步失败回滚，库里保持上一次成功的数据。"""
    columns = ",".join(f"`{column}`" for column in COLUMNS)
    placeholders = ",".join(["%s"] * len(COLUMNS))
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{TABLE}`")
                deleted = cursor.rowcount
                values = [tuple(row.get(column) for column in COLUMNS) for row in rows]
                for offset in range(0, len(values), 500):
                    cursor.executemany(f"INSERT INTO `{TABLE}` ({columns}) VALUES ({placeholders})",
                                       values[offset:offset + 500])
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{TABLE}`")
                stored = int((cursor.fetchone() or {}).get("n") or 0)
                if stored != len(rows):
                    raise ValueError(f"飞书汽配订单写入行数校验失败：本次{len(rows)}行，库里{stored}行，已回滚")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"inserted_rows": len(rows), "deleted_rows": max(deleted, 0)}


def open_orders(cursor, keys: Iterable[tuple[str, str]]) -> tuple[list[dict[str, Any]], Any]:
    """指定 (站点, SKU) 的未完成采购单，以及整表最近一次同步时间。

    用调用方的游标，和补货结果在同一个一致性读里；SKU 已在入库时统一成大写。
    """
    pairs = sorted({(str(site or "").strip(), str(sku or "").strip().upper()) for site, sku in keys
                    if str(site or "").strip() and str(sku or "").strip()})
    cursor.execute(f"SELECT MAX(synced_at) synced_at FROM `{TABLE}`")
    synced_at = (cursor.fetchone() or {}).get("synced_at")
    if not pairs:
        return [], synced_at
    rows: list[dict[str, Any]] = []
    status_marks = ",".join(["%s"] * len(CLOSED_STATUSES))
    for offset in range(0, len(pairs), 500):
        chunk = pairs[offset:offset + 500]
        cursor.execute(
            f"""SELECT site,sku,po,order_status,quantity,order_date,expected_ship_date,purchaser,warehouse
                FROM `{TABLE}`
                WHERE (site,sku) IN ({','.join(['(%s,%s)'] * len(chunk))})
                  AND COALESCE(order_status,'') NOT IN ({status_marks})
                ORDER BY site,sku,expected_ship_date IS NULL,expected_ship_date,order_date,po""",
            [value for pair in chunk for value in pair] + list(CLOSED_STATUSES),
        )
        rows.extend(cursor.fetchall())
    return rows, synced_at
