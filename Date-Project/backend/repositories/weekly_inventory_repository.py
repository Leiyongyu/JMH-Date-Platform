"""Immutable, batch-scoped weekly snapshots. No day-level delete/replace."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.config import settings
from backend.database import db_connection

EXPORT_CODE = "weekly_inventory_bin"
TABLES = {
    "inventory": "ods_lingxing_inventory_detail_weekly",
    "age": "ods_lingxing_inventory_age_bucket_weekly",
    "bins": "ods_lingxing_inventory_bin_detail_weekly",
    "products": "ods_lingxing_product_info_weekly",
}
JSON_FIELDS = {"raw_json", "stock_age_list", "third_inventory"}


def insert_snapshot(groups: dict[str, list[dict[str, Any]]]) -> int:
    count = 0
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for group, table in TABLES.items():
                    rows = groups[group]
                    if not rows:
                        continue
                    columns = tuple(rows[0])
                    if any(tuple(row) != columns for row in rows):
                        raise ValueError("周报快照字段不一致")
                    query = (f"INSERT INTO `{table}` (" + ",".join(f"`{c}`" for c in columns)
                             + ") VALUES (" + ",".join(["%s"] * len(columns)) + ")")
                    for start in range(0, len(rows), 500):
                        values = [tuple(json.dumps(row[c], ensure_ascii=False, default=str)
                                        if c in JSON_FIELDS and row[c] is not None else row[c]
                                        for c in columns) for row in rows[start:start + 500]]
                        cursor.executemany(query, values)
                    count += len(rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return count


def snapshot(batch: str) -> dict[str, list[dict]]:
    with db_connection() as connection, connection.cursor() as cursor:
        result = {}
        for group, table in TABLES.items():
            cursor.execute(f"SELECT * FROM `{table}` WHERE sync_batch_id=%s ORDER BY id", (batch,))
            result[group] = list(cursor.fetchall())
        return result


def warehouse_names() -> dict[int, str]:
    database = settings.shop_source_database
    if not re.fullmatch(r"[A-Za-z0-9_-]+", database):
        raise ValueError("仓库数据源库名非法")
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT wid,name FROM `{database}`.warehouse")
        return {int(row["wid"]): row["name"] for row in cursor.fetchall()}


def begin_export(batch, day, filename, path, trigger):
    with db_connection() as connection, connection.cursor() as cursor:
        # Called only while holding the global task lock: older RUNNING records
        # cannot still have a live writer holding that lock.
        cursor.execute("UPDATE ops_weekly_export_file SET status='INTERRUPTED',"
                       "error_message='上次进程中断；旧快照和文件保留，请检查后重新生成' "
                       "WHERE export_code=%s AND status='RUNNING'", (EXPORT_CODE,))
        cursor.execute("INSERT INTO ops_weekly_export_file "
                       "(export_code,snapshot_date,sync_batch_id,file_name,file_path,status,trigger_type,generated_at) "
                       "VALUES (%s,%s,%s,%s,%s,'RUNNING',%s,NOW())",
                       (EXPORT_CODE, day, batch, filename, str(path), trigger))
        connection.commit()


def finish_export(batch, *, error=None, row_count=None, column_count=None, file_size=None):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE ops_weekly_export_file SET status=%s,error_message=%s,"
                       "row_count=%s,column_count=%s,file_size=%s,generated_at=NOW() "
                       "WHERE export_code=%s AND sync_batch_id=%s",
                       ("FAILED" if error else "SUCCESS", error, row_count, column_count,
                        file_size, EXPORT_CODE, batch))
        if cursor.rowcount != 1:
            raise RuntimeError("周报文件登记缺失或批次重复")
        connection.commit()


def list_files(page: int, limit: int):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) total FROM ops_weekly_export_file WHERE export_code=%s", (EXPORT_CODE,))
        total = cursor.fetchone()["total"]
        cursor.execute("SELECT id,snapshot_date,sync_batch_id,file_name,file_size,row_count,column_count,"
                       "status,error_message,trigger_type,generated_at FROM ops_weekly_export_file "
                       "WHERE export_code=%s ORDER BY id DESC LIMIT %s OFFSET %s",
                       (EXPORT_CODE, limit, (page - 1) * limit))
        return {"items": list(cursor.fetchall()), "total": total}


def file_record(file_id: int):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM ops_weekly_export_file WHERE export_code=%s AND id=%s", (EXPORT_CODE, file_id))
        return cursor.fetchone()
