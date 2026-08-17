from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from backend.repositories import performance_repository as repo
from backend.services.amazon_profit_sync_service import (
    AmazonProfitEtlError,
    previous_natural_month,
    sync_amazon_monthly_profit,
)
from backend.services.clearance_service import (
    TASK_CODE as CLEARANCE_TASK_CODE,
    sync_fba_inventory,
)
from backend.services.amz_sop_after_sales_service import (
    TASK_CODE as AMZ_SOP_TASK_CODE,
    TASK_NAME as AMZ_SOP_TASK_NAME,
    AmzSopEtlError,
    run_amz_sop_chain,
)
from backend.services.inventory_report_source_sync_service import (
    TASK_CODE as INVENTORY_REPORT_TASK_CODE,
    TASK_NAME as INVENTORY_REPORT_TASK_NAME,
    InventoryReportSourceSyncError,
    sync_monthly_inventory_report_sources,
)


AMZ_TASK_CODE = "amz_monthly_order_profit_sync"
TASK_CODES = {
    AMZ_TASK_CODE,
    CLEARANCE_TASK_CODE,
    AMZ_SOP_TASK_CODE,
    INVENTORY_REPORT_TASK_CODE,
}


class SchedulerTaskAlreadyRunning(RuntimeError):
    pass


def list_scheduler_tasks() -> list[dict]:
    return repo.scheduler_tasks()


def list_scheduler_runs(task_code: str, limit: int = 50) -> list[dict]:
    return repo.scheduler_runs(task_code, limit)


def set_scheduler_task_enabled(task_code: str, enabled: bool) -> dict:
    if task_code not in TASK_CODES:
        raise ValueError("未知任务编码")
    repo.update_scheduler_task_enabled(task_code, enabled)
    return {"task_code": task_code, "enabled": enabled}


def run_scheduler_task(
    task_code: str,
    stat_month: str | None = None,
    start_date=None,
    end_date=None,
    request_id: str = "",
    trigger_type: str = "manual",
) -> dict:
    if task_code not in TASK_CODES:
        raise ValueError("未知任务编码")
    month = stat_month or (
        previous_natural_month()
        if task_code in {AMZ_TASK_CODE, INVENTORY_REPORT_TASK_CODE}
        else (end_date or datetime.now().date()).strftime("%Y-%m")
    )
    run_id = str(uuid4())
    started_at = datetime.now()
    with repo.performance_connection() as connection:
        repo.insert_scheduler_run(
            connection,
            _run_payload(run_id, task_code, "running", month, trigger_type, request_id, started_at),
        )
        connection.commit()
    try:
        if task_code == AMZ_TASK_CODE:
            lock_name = f"performance:amz-profit:{month}"
        elif task_code == AMZ_SOP_TASK_CODE:
            lock_name = "sop:amz-after-sales-chain"
        elif task_code == INVENTORY_REPORT_TASK_CODE:
            lock_name = f"inventory:monthly-report-source:{month}"
        else:
            lock_name = f"warehouse:amz-fba-inventory:{month}"
        with repo.named_lock(lock_name) as acquired:
            if not acquired:
                task_name = (
                    AMZ_SOP_TASK_NAME
                    if task_code == AMZ_SOP_TASK_CODE
                    else INVENTORY_REPORT_TASK_NAME
                    if task_code == INVENTORY_REPORT_TASK_CODE
                    else month + " AMZ任务"
                )
                raise SchedulerTaskAlreadyRunning(
                    f"{task_name}正在执行"
                )
            if task_code == AMZ_TASK_CODE:
                result = sync_amazon_monthly_profit(
                    stat_month=month,
                    request_id=request_id,
                    trigger_source=(
                        "scheduler_manual"
                        if trigger_type == "manual"
                        else "scheduler"
                    ),
                )
            elif task_code == CLEARANCE_TASK_CODE:
                result = sync_fba_inventory(month)
            elif task_code == INVENTORY_REPORT_TASK_CODE:
                result = sync_monthly_inventory_report_sources(month)
            else:
                result = run_amz_sop_chain(
                    start_date=start_date,
                    end_date=end_date,
                    request_id=request_id,
                )
        with repo.performance_connection() as connection:
            repo.insert_scheduler_run(
                connection,
                {
                    **_run_payload(
                        run_id, task_code, "completed",
                        result.get("stat_month", result.get("pull_month", month)),
                        trigger_type, request_id, started_at
                    ),
                    "source_rows": result["extract_rows"],
                    "sync_batch_id": result["sync_batch_id"],
                    "extract_rows": result["extract_rows"],
                    "ods_rows": result["ods_rows"],
                    "inserted_rows": result.get("inserted_rows", result.get("dwd_rows", 0)),
                    "updated_rows": result.get("updated_rows", 0),
                    "deleted_rows": result.get("deleted_rows", 0),
                    "skipped_rows": result.get("skipped_rows", result.get("unmatched_group_rows", 0)),
                    "amz_ranking_rows": result.get("refresh", {}).get("amz_ranking_rows", 0),
                    "combined_ranking_rows": result.get("refresh", {}).get(
                        "combined_ranking_rows", result.get("group_rows", 0)
                    ),
                    "etl_stage": "COMPLETED",
                    "completed_at": datetime.now(),
                },
            )
            connection.commit()
        return {"run_id": run_id, "task_code": task_code, "status": "completed", "result": result}
    except Exception as exc:
        etl_stage = (
            exc.stage
            if isinstance(
                exc,
                (AmazonProfitEtlError, AmzSopEtlError, InventoryReportSourceSyncError),
            )
            else "LOCK" if isinstance(exc, SchedulerTaskAlreadyRunning)
            else "UNKNOWN"
        )
        metrics = (
            exc.metrics
            if isinstance(
                exc,
                (AmazonProfitEtlError, AmzSopEtlError, InventoryReportSourceSyncError),
            )
            else {}
        )
        with repo.performance_connection() as connection:
            repo.insert_scheduler_run(
                connection,
                {
                    **_run_payload(run_id, task_code, "failed", month, trigger_type, request_id, started_at),
                    "source_rows": metrics.get("extract_rows", 0),
                    "sync_batch_id": metrics.get("sync_batch_id"),
                    "extract_rows": metrics.get("extract_rows", 0),
                    "ods_rows": metrics.get("ods_rows", 0),
                    "inserted_rows": metrics.get("inserted_rows", 0),
                    "updated_rows": metrics.get("updated_rows", 0),
                    "deleted_rows": metrics.get("deleted_rows", 0),
                    "skipped_rows": metrics.get("skipped_rows", 0),
                    "amz_ranking_rows": metrics.get(
                        "amz_ranking_rows", 0
                    ),
                    "combined_ranking_rows": metrics.get(
                        "combined_ranking_rows", 0
                    ),
                    "etl_stage": etl_stage,
                    "error_message": str(exc),
                    "completed_at": datetime.now(),
                },
            )
            connection.commit()
        raise


def _run_payload(run_id, task_code, status, stat_month, trigger_type, request_id, started_at):
    return {
        "run_id": run_id,
        "task_code": task_code,
        "status": status,
        "stat_month": stat_month,
        "trigger_type": trigger_type,
        "source_rows": 0,
        "sync_batch_id": None,
        "extract_rows": 0,
        "ods_rows": 0,
        "inserted_rows": 0,
        "updated_rows": 0,
        "deleted_rows": 0,
        "skipped_rows": 0,
        "amz_ranking_rows": 0,
        "combined_ranking_rows": 0,
        "etl_stage": "STARTING",
        "error_message": None,
        "request_id": request_id,
        "started_at": started_at,
        "completed_at": None,
    }
