from __future__ import annotations

import json
from typing import Any

from backend.database import db_connection


def recover_interrupted_tasks() -> None:
    """Release a stale executor left by a previous process termination."""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE amazon_image_upload_task
                SET status='failed', finished_at=NOW(3),
                    error_message='Python服务重启，原执行任务已中断'
                WHERE status IN ('queued', 'running')
                """
            )
            cursor.execute(
                """
                UPDATE amazon_image_upload_executor
                SET active_task_id=NULL, claimed_at=NULL
                """
            )
        connection.commit()


def create_task(
    *,
    request_id: str,
    user_id: int | None,
    username: str,
    marketplace_code: str,
    shop_count: int,
    total_sku: int,
    payload: dict[str, Any],
) -> int:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO amazon_image_upload_task (
                    request_id, status, created_by_id, created_by_name,
                    marketplace_code, shop_count, total_sku, payload_json
                ) VALUES (%s, 'queued', %s, %s, %s, %s, %s, %s)
                """,
                (
                    request_id,
                    user_id,
                    username,
                    marketplace_code,
                    shop_count,
                    total_sku,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            task_id = int(cursor.lastrowid)
        connection.commit()
    return task_id


def claim_executor(
    task_id: int, base_port: int, max_slots: int = 5
) -> int | None:
    """Atomically claim the first free local Ziniao port slot."""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT executor_id
                FROM amazon_image_upload_executor
                WHERE executor_id <= %s AND active_task_id IS NULL
                ORDER BY executor_id
                LIMIT 1 FOR UPDATE
                """,
                (max(1, min(max_slots, 5)),),
            )
            row = cursor.fetchone()
            if not row:
                connection.commit()
                return None
            executor_id = int(row["executor_id"])
            automation_port = int(base_port) + executor_id - 1
            cursor.execute(
                """
                UPDATE amazon_image_upload_executor
                SET active_task_id=%s, claimed_at=NOW(3)
                WHERE executor_id=%s AND active_task_id IS NULL
                """,
                (task_id, executor_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return None
            if task_id > 0:
                cursor.execute(
                    """
                    UPDATE amazon_image_upload_task
                    SET executor_slot=%s, automation_port=%s,
                        current_message=%s
                    WHERE task_id=%s
                    """,
                    (
                        executor_id,
                        automation_port,
                        f"已分配紫鸟端口 {automation_port}，准备启动",
                        task_id,
                    ),
                )
        connection.commit()
    return executor_id


def release_executor(task_id: int) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE amazon_image_upload_executor
                SET active_task_id=NULL, claimed_at=NULL
                WHERE active_task_id=%s
                """,
                (task_id,),
            )
        connection.commit()


def queue_position(task_id: int) -> int:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS waiting
                FROM amazon_image_upload_task
                WHERE status='queued' AND task_id <= %s
                """,
                (task_id,),
            )
            row = cursor.fetchone() or {"waiting": 0}
            return int(row["waiting"] or 0)


def stop_queued_task(task_id: int, user_id: int | None) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            if user_id is None:
                cursor.execute(
                    """
                    UPDATE amazon_image_upload_task
                    SET status='stopped', finished_at=NOW(3),
                        current_message='排队任务已取消'
                    WHERE task_id=%s AND status='queued'
                    """,
                    (task_id,),
                )
            else:
                cursor.execute(
                    """
                    UPDATE amazon_image_upload_task
                    SET status='stopped', finished_at=NOW(3),
                        current_message='排队任务已取消'
                    WHERE task_id=%s AND created_by_id=%s AND status='queued'
                    """,
                    (task_id, user_id),
                )
            stopped = cursor.rowcount == 1
        connection.commit()
    return stopped


def mark_started(task_id: int) -> None:
    _update_task(
        task_id,
        "status='running', started_at=NOW(3), current_message='任务已启动'",
        (),
    )


def update_progress(task_id: int, done: int, total: int, message: str) -> None:
    failed_delta = 1 if "FAIL" in message else 0
    skipped_delta = 1 if ("跳过" in message or "无图片" in message) else 0
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE amazon_image_upload_task
                SET completed_sku=GREATEST(completed_sku, %s),
                    total_sku=GREATEST(total_sku, %s),
                    failed_sku=failed_sku+%s,
                    skipped_sku=skipped_sku+%s,
                    current_message=%s
                WHERE task_id=%s
                """,
                (
                    max(0, done),
                    max(0, total),
                    failed_delta,
                    skipped_delta,
                    message[:1000],
                    task_id,
                ),
            )
        connection.commit()


def finish_task(task_id: int, status: str, error: str | None = None) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE amazon_image_upload_task
                SET status=%s, finished_at=NOW(3),
                    current_message=%s, error_message=%s
                WHERE task_id=%s
                """,
                (
                    status,
                    "任务已停止" if status == "stopped" else "任务执行完成",
                    error[:2000] if error else None,
                    task_id,
                ),
            )
        connection.commit()


def append_log(task_id: int, level: str, message: str) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO amazon_image_upload_task_log (task_id, level, message)
                VALUES (%s, %s, %s)
                """,
                (task_id, level[:16], message[:4000]),
            )
        connection.commit()


def create_file_batch(
    *,
    batch_id: str,
    request_id: str,
    user_id: int | None,
    username: str,
    shop_id: str,
    shop_name: str,
    shop_folder: str,
    requested_files: int,
) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO amazon_image_upload_file_batch (
                    batch_id, request_id, status, created_by_id, created_by_name,
                    ziniao_shop_id, ziniao_shop_name, shop_folder,
                    requested_files
                ) VALUES (%s, %s, 'running', %s, %s, %s, %s, %s, %s)
                """,
                (
                    batch_id,
                    request_id,
                    user_id,
                    username,
                    shop_id[:128],
                    shop_name[:255],
                    shop_folder[:1000],
                    requested_files,
                ),
            )
        connection.commit()


def finish_file_batch(
    batch_id: str,
    *,
    status: str,
    saved_files: int,
    skipped_files: int,
    total_bytes: int,
    error_message: str | None = None,
) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE amazon_image_upload_file_batch
                SET status=%s, saved_files=%s, skipped_files=%s,
                    total_bytes=%s, error_message=%s, finished_at=NOW(3)
                WHERE batch_id=%s
                """,
                (
                    status[:20],
                    max(0, saved_files),
                    max(0, skipped_files),
                    max(0, total_bytes),
                    error_message[:2000] if error_message else None,
                    batch_id,
                ),
            )
        connection.commit()


def _progress_prefix(user_id: int | None) -> str:
    return f"erp:{user_id}:" if user_id is not None else "local:"


def mark_completed(
    progress_key: str, task_id: int | None = None, user_id: int | None = None
) -> None:
    parts = progress_key.split("@", 2)
    sku = parts[0] if parts else progress_key
    marketplace = parts[1] if len(parts) > 1 else "DE"
    shop_id = parts[2] if len(parts) > 2 else ""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO amazon_image_upload_progress (
                    progress_key, sku, marketplace_code, ziniao_shop_id,
                    last_task_id, completed_at
                ) VALUES (%s, %s, %s, %s, %s, NOW(3))
                ON DUPLICATE KEY UPDATE
                    last_task_id=VALUES(last_task_id), completed_at=NOW(3)
                """,
                (_progress_prefix(user_id) + progress_key, sku, marketplace, shop_id, task_id),
            )
        connection.commit()


def completed_keys(user_id: int | None = None) -> set[str]:
    prefix = _progress_prefix(user_id)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT progress_key FROM amazon_image_upload_progress WHERE progress_key LIKE %s",
                (prefix + "%",),
            )
            return {
                str(row["progress_key"])[len(prefix):] for row in cursor.fetchall()
            }


def clear_progress(user_id: int | None = None) -> int:
    prefix = _progress_prefix(user_id)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM amazon_image_upload_progress WHERE progress_key LIKE %s",
                (prefix + "%",),
            )
            deleted = cursor.rowcount
        connection.commit()
    return int(deleted)


def latest_task(user_id: int | None = None) -> dict[str, Any] | None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            if user_id is None:
                cursor.execute(
                    """SELECT t.* FROM amazon_image_upload_task t
                       ORDER BY t.task_id DESC LIMIT 1"""
                )
            else:
                cursor.execute(
                    """SELECT t.* FROM amazon_image_upload_task t
                       WHERE t.created_by_id=%s
                       ORDER BY t.task_id DESC LIMIT 1""",
                    (user_id,),
                )
            return cursor.fetchone()


def list_tasks(limit: int = 30, user_id: int | None = None) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            safe_limit = max(1, min(limit, 100))
            if user_id is None:
                cursor.execute(
                    """
                    SELECT task_id, request_id, status, created_by_id, created_by_name,
                           marketplace_code, shop_count, total_sku, completed_sku,
                           failed_sku, skipped_sku, current_message, error_message,
                           executor_slot, automation_port,
                           created_at, started_at, finished_at
                    FROM amazon_image_upload_task
                    ORDER BY task_id DESC LIMIT %s
                    """,
                    (safe_limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT task_id, request_id, status, created_by_id, created_by_name,
                           marketplace_code, shop_count, total_sku, completed_sku,
                           failed_sku, skipped_sku, current_message, error_message,
                           executor_slot, automation_port,
                           created_at, started_at, finished_at
                    FROM amazon_image_upload_task
                    WHERE created_by_id=%s
                    ORDER BY task_id DESC LIMIT %s
                    """,
                    (user_id, safe_limit),
                )
            return list(cursor.fetchall())


def task_logs(
    task_id: int, limit: int = 500, user_id: int | None = None
) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            safe_limit = max(1, min(limit, 1000))
            if user_id is None:
                cursor.execute(
                    """
                    SELECT log_id, task_id, level, message, created_at
                    FROM amazon_image_upload_task_log
                    WHERE task_id=%s
                    ORDER BY log_id DESC LIMIT %s
                    """,
                    (task_id, safe_limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT l.log_id, l.task_id, l.level, l.message, l.created_at
                    FROM amazon_image_upload_task_log l
                    INNER JOIN amazon_image_upload_task t ON t.task_id=l.task_id
                    WHERE l.task_id=%s AND t.created_by_id=%s
                    ORDER BY l.log_id DESC LIMIT %s
                    """,
                    (task_id, user_id, safe_limit),
                )
            rows = list(cursor.fetchall())
    rows.reverse()
    return rows


def _update_task(task_id: int, assignments: str, params: tuple[Any, ...]) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE amazon_image_upload_task SET {assignments} WHERE task_id=%s",
                (*params, task_id),
            )
        connection.commit()
