"""后台任务队列 — 幂等、重试、心跳、恢复。

当前实现：FastAPI 进程内 ThreadPoolExecutor。
切换方式：改配置中的 task_queue_backend 或在 app.py 中替换实例。
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

import logging

from core.config import get_settings
from infrastructure.database import get_conn

logger = logging.getLogger(__name__)

# ── 可靠性字段的 SQL（Alembic 迁移执行后生效） ──
RELIABILITY_COLUMNS_EXIST = False  # 迁移后置为 True

TASK_HANDLERS: dict[str, Callable[[int, dict], tuple[dict, str]]] = {}
"""全局任务处理器注册表: {task_type: handler(task_id, task_payload) -> (result, status)}"""


class TaskQueue(ABC):
    @abstractmethod
    def enqueue(self, task_id: int) -> None: ...
    @abstractmethod
    def cancel(self, task_id: int) -> bool: ...
    @abstractmethod
    def recover(self) -> list[int]: ...


class ThreadPoolTaskQueue(TaskQueue):
    """进程内线程池实现。"""

    def __init__(self, max_workers: int | None = None):
        settings = get_settings()
        workers = max_workers or settings.task_max_workers
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="task-")
        self._futures: dict[int, Future] = {}

    def enqueue(self, task_id: int) -> None:
        task = _load_task(task_id)
        if not task:
            return

        task_type = task["task_type"]
        handler = TASK_HANDLERS.get(task_type)
        if not handler:
            _fail_task(task_id, f"未找到任务处理器: {task_type}")
            return

        # 数据库条件更新充当任务租约；重复提交同一任务时只有一个执行者能获得租约。
        if not _mark_running(task_id):
            logger.info("task_enqueue_skipped task_id=%d status=%s", task_id, task.get("task_status"))
            return
        future = self._executor.submit(_run_handler, task_id, handler)
        self._futures[task_id] = future
        def cleanup(done: Future) -> None:
            # 旧尝试结束时不能误删同一 task_id 的重试 Future。
            if self._futures.get(task_id) is done:
                self._futures.pop(task_id, None)
        future.add_done_callback(cleanup)

    def cancel(self, task_id: int) -> bool:
        future = self._futures.get(task_id)
        if future and not future.done():
            cancelled = future.cancel()
            if cancelled:
                _mark_cancelled(task_id)
            return cancelled
        return False

    def recover(self) -> list[int]:
        """重启后恢复 PENDING 和超时 RUNNING 任务。"""
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            # 重置超时租约的 RUNNING 任务
            cursor.execute("""
                UPDATE api_task
                SET task_status = 'PENDING',
                    worker_id = NULL,
                    heartbeat_at = NULL,
                    lease_expires_at = NULL
                WHERE task_status = 'RUNNING'
                  AND (lease_expires_at IS NULL OR lease_expires_at < NOW(3))
            """)
            reset_count = cursor.rowcount

            # 获取所有 PENDING 任务
            cursor.execute("""
                SELECT id FROM api_task
                WHERE task_status = 'PENDING'
                ORDER BY created_at
            """)
            pending_ids = [row["id"] for row in cursor.fetchall()]
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        if reset_count:
            logger.info("task_recovery_reset reset_running=%d", reset_count)
        if pending_ids:
            logger.info("task_recovery_pending pending=%d", len(pending_ids))
            for tid in pending_ids:
                try:
                    self.enqueue(tid)
                except Exception:
                    logger.exception("task_recovery_enqueue_failed task_id=%d", tid)

        return pending_ids


# ── 全局单例 ──
_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = ThreadPoolTaskQueue()
    return _queue


def register_handler(task_type: str):
    """装饰器：注册任务处理器"""
    def decorator(func: Callable[[int, dict], tuple[dict, str]]):
        TASK_HANDLERS[task_type] = func
        return func
    return decorator


# ── 内部函数 ──

def _load_task(task_id: int) -> dict | None:
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM api_task WHERE id = %s", (task_id,))
        task = cursor.fetchone()
        if task:
            for field in ("request_payload", "result_payload"):
                value = task.get(field)
                if isinstance(value, (str, bytes, bytearray)):
                    try:
                        task[field] = json.loads(value)
                    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                        # 保留原值，让具体处理器给出可定位的业务错误。
                        pass
        return task
    finally:
        cursor.close()
        conn.close()


def _mark_running(task_id: int) -> bool:
    import os
    worker_id = f"{os.uname().nodename}:{os.getpid()}" if hasattr(os, "uname") else f"win:{os.getpid()}"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE api_task
            SET task_status = 'RUNNING',
                started_at = NOW(3),
                worker_id = %s,
                heartbeat_at = NOW(3),
                lease_expires_at = DATE_ADD(NOW(3), INTERVAL 30 MINUTE),
                error_message = NULL
            WHERE id = %s AND task_status = 'PENDING'
        """, (worker_id, task_id))
        acquired = cursor.rowcount == 1
        conn.commit()
        return acquired
    finally:
        cursor.close()
        conn.close()


def _mark_cancelled(task_id: int) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE api_task SET task_status='CANCELLED', completed_at=NOW(3) WHERE id=%s",
            (task_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _fail_task(task_id: int, message: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE api_task
            SET task_status='FAILED', error_message=%s, completed_at=NOW(3),
                worker_id=NULL, heartbeat_at=NULL, lease_expires_at=NULL
            WHERE id=%s
            """,
            (message[:10000], task_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _run_handler(task_id: int, handler: Callable) -> None:
    try:
        task = _load_task(task_id)
        if not task:
            return
        result, status = handler(task_id, task)
        _complete_task(task_id, result, status)
    except Exception as exc:
        logger.exception("task_handler_failed task_id=%d", task_id)
        task = _load_task(task_id)
        if task:
            retry_count = int(task.get("retry_count") or 0)
            max_retries = int(task.get("max_retries") or 3)
            if retry_count < max_retries:
                conn = get_conn()
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        UPDATE api_task SET task_status='PENDING',
                            retry_count = retry_count + 1,
                            error_message = %s,
                            worker_id = NULL,
                            heartbeat_at = NULL,
                            lease_expires_at = NULL
                        WHERE id = %s
                    """, (str(exc)[:10000], task_id))
                    conn.commit()
                finally:
                    cursor.close()
                    conn.close()
                logger.info("task_retry task_id=%d retry=%d", task_id, retry_count + 1)
                get_task_queue().enqueue(task_id)
            else:
                _fail_task(task_id, f"重试 {max_retries} 次后仍然失败: {exc}")


def _complete_task(task_id: int, result: dict, status: str) -> None:
    import json
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE api_task
            SET task_status = %s,
                result_payload = %s,
                progress_current = progress_total,
                completed_at = NOW(3),
                worker_id = NULL,
                heartbeat_at = NULL,
                lease_expires_at = NULL
            WHERE id = %s
        """, (status, json.dumps(result, ensure_ascii=False, default=str), task_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
