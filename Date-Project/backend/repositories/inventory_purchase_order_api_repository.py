"""Independent purchase-order API cache and auditable monthly source snapshots."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from backend.database import db_connection
from backend.config import settings

TASK_CODE = "monthly_inventory_purchase_order_sync"


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


def state():
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM inventory_purchase_order_api_state WHERE id=1")
        return cursor.fetchone()


def cached_orders():
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT order_sn,payload_json FROM ods_inventory_purchase_order_api_latest")
        return {row["order_sn"]: json.loads(row["payload_json"]) for row in cursor.fetchall()}


def shop_map():
    database = (settings.shop_source_database.strip() or "jmh_data_platform").replace("`", "``")
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT CAST(sid AS CHAR) AS sid,store_name FROM `{database}`.shop_list "
                       "WHERE sid IS NOT NULL")
        return {str(row["sid"]): str(row.get("store_name") or "").strip() for row in cursor.fetchall()}


def status(stat_month, request_id=None):
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT sync_batch_id,pulled_at,published_at,result_json "
                       "FROM inventory_purchase_order_api_month WHERE stat_month=%s", (stat_month,))
        snapshot = cursor.fetchone()
        if snapshot:
            snapshot["result"] = json.loads(snapshot.pop("result_json"))
        where = " AND request_id=%s" if request_id else ""
        params = (TASK_CODE, request_id) if request_id else (TASK_CODE,)
        cursor.execute("SELECT request_id,status,started_at,completed_at,error_message,etl_stage "
                       "FROM scheduler_task_run WHERE task_code=%s" + where +
                       " ORDER BY started_at DESC LIMIT 1", params)
        run = cursor.fetchone()
        cursor.execute("SELECT IS_USED_LOCK(%s) AS holder", ("inventory:purchase-order-api",))
        running = cursor.fetchone()["holder"] is not None
        if (run and run["status"] == "running" and not running
                and datetime.now() - run["started_at"] > timedelta(seconds=30)):
            run = {**run, "status": "interrupted", "error_message": "同步已中断，可重新同步；上次成功数据保留"}
        # An Excel import after an API sync must not be described as API-derived data.
        cursor.execute("SELECT DISTINCT import_batch_id FROM ods_inventory_report_purchase_order_transit "
                       "WHERE stat_month=%s", (stat_month,))
        batches = {row["import_batch_id"] for row in cursor.fetchall()}
        api_current = bool(snapshot and (not batches or batches == {snapshot["sync_batch_id"]}))
        return {"stat_month": stat_month, "running": running, "run": run,
                "snapshot": snapshot, "source": "API" if api_current else "EXCEL" if batches else None}


def publish_cache(connection, orders, *, full, pulled_at, batch_id, previous_state,
                  stat_month, result, active_orders):
    """Caller owns the transaction that also publishes ODS/DWS/view snapshots."""
    with connection.cursor() as cursor:
        if full:
            cursor.execute("DELETE FROM ods_inventory_purchase_order_api_latest")
        if orders:
            cursor.executemany(
                "INSERT INTO ods_inventory_purchase_order_api_latest "
                "(order_sn,payload_json,sync_batch_id,pulled_at) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json),"
                "sync_batch_id=VALUES(sync_batch_id),pulled_at=VALUES(pulled_at)",
                [(order["order_sn"], dumps(order), batch_id, pulled_at) for order in orders.values()],
            )
        cursor.execute("INSERT INTO inventory_purchase_order_api_state "
                       "(id,pulled_at,full_pulled_at,sync_batch_id) VALUES (1,%s,%s,%s) "
                       "ON DUPLICATE KEY UPDATE pulled_at=VALUES(pulled_at),"
                       "full_pulled_at=VALUES(full_pulled_at),sync_batch_id=VALUES(sync_batch_id)",
                       (pulled_at, pulled_at if full else previous_state["full_pulled_at"], batch_id))
        cursor.execute("INSERT INTO inventory_purchase_order_api_month "
                       "(stat_month,sync_batch_id,pulled_at,published_at,result_json,source_json) "
                       "VALUES (%s,%s,%s,NOW(),%s,%s) ON DUPLICATE KEY UPDATE "
                       "sync_batch_id=VALUES(sync_batch_id),pulled_at=VALUES(pulled_at),"
                       "published_at=VALUES(published_at),result_json=VALUES(result_json),source_json=VALUES(source_json)",
                       (stat_month, batch_id, pulled_at, dumps(result), dumps(active_orders)))
