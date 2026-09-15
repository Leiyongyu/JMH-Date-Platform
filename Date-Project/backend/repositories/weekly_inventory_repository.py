"""Keep one complete weekly snapshot; replace all four ODS tables atomically."""
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


def replace_snapshot_and_finish_export(
    groups: dict[str, list[dict[str, Any]]], *, file_name: str,
    row_count: int, column_count: int, file_size: int,
) -> dict[str, int]:
    """Publish one ready snapshot and prune older batches in one transaction.

    Caller holds inventory:weekly-export and has already generated the complete
    Excel. A failed extraction/export/transaction must leave the previous usable
    snapshot intact. Export records and physical Excel archives are never pruned.
    """
    if set(groups) != set(TABLES) or not groups['inventory'] or not groups['products']:
        raise ValueError('新周报快照不完整，拒绝替换旧快照')
    batch = groups['inventory'][0].get('sync_batch_id')
    day = groups['inventory'][0].get('snapshot_date')
    if not isinstance(batch, str) or not batch.strip() or day is None:
        raise ValueError('新周报快照缺少批次或日期，拒绝替换旧快照')
    if any(row.get('sync_batch_id') != batch or row.get('snapshot_date') != day
           for rows in groups.values() for row in rows):
        raise ValueError('新周报快照混入其他批次或日期，拒绝替换旧快照')
    product_ids = {row.get('product_id') for row in groups['products']}
    if None in product_ids or not {row.get('product_id') for row in groups['inventory']}.issubset(product_ids):
        raise ValueError('新周报产品详情不完整，拒绝替换旧快照')
    if not file_name or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
                            for value in (row_count, column_count, file_size)):
        raise ValueError('周报文件尚未完整生成，拒绝替换旧快照')
    count = 0
    deleted = 0
    with db_connection() as connection:
        try:
            # DBUtils only disables transparent reconnect/replay after begin();
            # autocommit=False alone does not mark its wrapper as transactional.
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT status,snapshot_date FROM ops_weekly_export_file '
                    'WHERE export_code=%s AND sync_batch_id=%s AND file_name=%s FOR UPDATE',
                    (EXPORT_CODE, batch, file_name),
                )
                record = cursor.fetchone()
                if not record or record['status'] != 'RUNNING' or record['snapshot_date'] != day:
                    raise ValueError('周报生成记录不存在或状态已变化，拒绝替换旧快照')
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
                # Insert first; never commit a deletion before the replacement.
                # Static table allowlist only, no TRUNCATE/DDL or filesystem work.
                for table in TABLES.values():
                    cursor.execute(f'DELETE FROM `{table}` WHERE sync_batch_id<>%s', (batch,))
                    deleted += cursor.rowcount
                cursor.execute(
                    "UPDATE ops_weekly_export_file SET status='SUCCESS',error_message=NULL,"
                    'row_count=%s,column_count=%s,file_size=%s,generated_at=NOW() '
                    "WHERE export_code=%s AND sync_batch_id=%s AND file_name=%s AND status='RUNNING'",
                    (row_count, column_count, file_size, EXPORT_CODE, batch, file_name),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError('周报文件登记缺失或状态已变化，旧快照保留')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {'ods_rows': count, 'deleted_rows': deleted}


def snapshot(batch: str) -> dict[str, list[dict]]:
    with db_connection() as connection, connection.cursor() as cursor:
        result = {}
        for group, table in TABLES.items():
            cursor.execute(f"SELECT * FROM `{table}` WHERE sync_batch_id=%s ORDER BY id", (batch,))
            result[group] = list(cursor.fetchall())
        return result


def latest_completed_snapshot():
    """Reuse a committed batch that has had a successful export, even if deleted.

    Re-export time must not make older inventory appear to be a newer snapshot.
    Empty bin/age tables can be legitimate, so inventory is the batch anchor.
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT i.sync_batch_id,i.snapshot_date,MAX(i.pulled_at) AS pulled_at "
            "FROM ods_lingxing_inventory_detail_weekly i "
            "WHERE EXISTS (SELECT 1 FROM ops_weekly_export_file f "
            "WHERE f.export_code=%s AND f.sync_batch_id=i.sync_batch_id "
            "AND f.snapshot_date=i.snapshot_date AND f.status IN ('SUCCESS','DELETE_PENDING','DELETED')) "
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
        # A lost COMMIT response can make a successful atomic replacement look
        # failed to the caller. Never downgrade that only usable snapshot.
        guard = " AND status='RUNNING'" if error else ''
        cursor.execute("UPDATE ops_weekly_export_file SET status=%s,error_message=%s,"
                       "row_count=%s,column_count=%s,file_size=%s,generated_at=NOW() "
                       "WHERE export_code=%s AND sync_batch_id=%s AND file_name=%s" + guard,
                       ("FAILED" if error else "SUCCESS", error, row_count, column_count,
                        file_size, EXPORT_CODE, batch, file_name))
        if cursor.rowcount != 1:
            cursor.execute('SELECT status FROM ops_weekly_export_file '
                           'WHERE export_code=%s AND sync_batch_id=%s AND file_name=%s',
                           (EXPORT_CODE, batch, file_name))
            record = cursor.fetchone()
            if not error or not record or record['status'] != 'SUCCESS':
                raise RuntimeError("周报文件登记缺失或批次重复")
        connection.commit()


def list_files(page: int, limit: int):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) total FROM ops_weekly_export_file WHERE export_code=%s AND status<>'DELETED'", (EXPORT_CODE,))
        total = cursor.fetchone()["total"]
        cursor.execute("SELECT id,snapshot_date,sync_batch_id,file_name,file_size,row_count,column_count,"
                       "status,error_message,trigger_type,generated_at FROM ops_weekly_export_file "
                       "WHERE export_code=%s AND status<>'DELETED' ORDER BY id DESC LIMIT %s OFFSET %s",
                       (EXPORT_CODE, limit, (page - 1) * limit))
        return {"items": list(cursor.fetchall()), "total": total}


def file_record(file_id: int):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM ops_weekly_export_file WHERE export_code=%s AND id=%s", (EXPORT_CODE, file_id))
        return cursor.fetchone()


def mark_file_delete_pending(file_id: int):
    """Durably record intent before touching a file; never remove the audit row."""
    _change_file_delete_status(file_id, 'SUCCESS', 'DELETE_PENDING', '永久删除请求已登记；等待文件清理完成')


def mark_file_deleted(file_id: int):
    _change_file_delete_status(file_id, 'DELETE_PENDING', 'DELETED', 'Excel文件已永久删除；库存快照保留')


def _change_file_delete_status(file_id, previous, status, message):
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ops_weekly_export_file SET status=%s,error_message=%s "
                    "WHERE export_code=%s AND id=%s AND status=%s",
                    (status, message, EXPORT_CODE, file_id, previous),
                )
                if cursor.rowcount != 1:
                    raise ValueError('文件状态已变化，请刷新列表后重试')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
