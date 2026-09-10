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

BIN_IDENTITY_COMMENT = "weekly-bin-identity-v1: store_id,msku,fnsku; byte-exact length framing"
BIN_INDEX_COLUMNS = "snapshot_date,sync_batch_id,wid,whb_id,product_id,bin_identity_key"


def require_bin_identity_schema():
    """Fail before external extraction if the schema migration was skipped."""
    message = "周报仓位业务键未升级，请先执行10_周报仓位业务键修复.sql，再执行11只读验证；本次未调用领星"
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_TYPE,EXTRA,COLUMN_COMMENT FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly' "
            "AND COLUMN_NAME='bin_identity_key'"
        )
        column = cursor.fetchone()
        if (not column or str(column.get("COLUMN_TYPE")).lower() != "varbinary(1600)"
                or "STORED GENERATED" not in str(column.get("EXTRA")).upper()
                or column.get("COLUMN_COMMENT") != BIN_IDENTITY_COMMENT):
            raise ValueError(message)
        cursor.execute(
            "SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns, "
            "MAX(NON_UNIQUE) AS non_unique,SUM(SUB_PART IS NOT NULL) AS prefix_parts "
            "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly' AND INDEX_NAME='uk_bin_week'"
        )
        index = cursor.fetchone()
        if (not index or index.get("index_columns") != BIN_INDEX_COLUMNS
                or index.get("non_unique") != 0 or index.get("prefix_parts") != 0):
            raise ValueError(message)


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


def latest_completed_snapshot():
    """Reuse only a committed batch with a successful export, ordered by pull time.

    Re-export time must not make older inventory appear to be a newer snapshot.
    Empty bin/age tables can be legitimate, so inventory is the batch anchor.
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT i.sync_batch_id,i.snapshot_date,MAX(i.pulled_at) AS pulled_at "
            "FROM ods_lingxing_inventory_detail_weekly i "
            "WHERE EXISTS (SELECT 1 FROM ops_weekly_export_file f "
            "WHERE f.export_code=%s AND f.sync_batch_id=i.sync_batch_id "
            "AND f.snapshot_date=i.snapshot_date AND f.status='SUCCESS') "
            "GROUP BY i.sync_batch_id,i.snapshot_date "
            "ORDER BY pulled_at DESC,i.snapshot_date DESC,i.sync_batch_id DESC LIMIT 1",
            (EXPORT_CODE,),
        )
        return cursor.fetchone()


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


def finish_export(batch, *, file_name, error=None, row_count=None, column_count=None, file_size=None):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE ops_weekly_export_file SET status=%s,error_message=%s,"
                       "row_count=%s,column_count=%s,file_size=%s,generated_at=NOW() "
                       "WHERE export_code=%s AND sync_batch_id=%s AND file_name=%s",
                       ("FAILED" if error else "SUCCESS", error, row_count, column_count,
                        file_size, EXPORT_CODE, batch, file_name))
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
