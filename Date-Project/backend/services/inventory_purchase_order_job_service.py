"""Short HTTP submission, persistent task logs, shared manual/Quartz lock."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4

from backend.repositories import inventory_purchase_order_api_repository as repo
from backend.repositories.performance_repository import named_lock
from backend.services.inventory_purchase_order_sync_service import current_source_month

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="purchase-order-sync")
_guard = Lock()
_future = None
_request_id = None


def report_write(month, action, *args, **kwargs):
    with named_lock(f"inventory:monthly-report-source:{month}") as acquired:
        if not acquired:
            raise ValueError("该月份正在同步、计算或导入，请稍后重试")
        return action(*args, **kwargs)


def get_status(stat_month=None, request_id=None):
    result = repo.status(stat_month or current_source_month(), request_id)
    with _guard:
        if _future is not None and not _future.done() and (not request_id or request_id == _request_id):
            result["running"] = True
            if not result["run"] or result["run"]["request_id"] != _request_id:
                result["run"] = {"status": "queued", "request_id": _request_id}
            elif result["run"]["status"] == "interrupted":
                result["run"]["status"] = "running"
        elif (_future is not None and _future.done() and not _future.cancelled()
              and _future.exception() and (not request_id or request_id == _request_id)
              and (not result["run"] or result["run"]["request_id"] != _request_id)):
            result["run"] = {"status": "failed", "request_id": _request_id,
                             "error_message": "任务启动或记录失败，请检查数据库和任务日志后重试"}
    return result


def _run(request_id):
    from backend.services.scheduler_service import run_scheduler_task
    return run_scheduler_task(repo.TASK_CODE, request_id=request_id, trigger_type="manual")


def submit():
    global _future, _request_id
    with _guard:
        if _future is not None and not _future.done():
            return {"request_id": _request_id, "status": "running"}
        current = repo.status(current_source_month())  # Fails early if migration is missing.
        if current["running"]:
            return {"request_id": (current["run"] or {}).get("request_id"), "status": "running"}
        _request_id = "purchase-order-manual-" + str(uuid4())
        _future = _executor.submit(_run, _request_id)
        return {"request_id": _request_id, "status": "queued"}
