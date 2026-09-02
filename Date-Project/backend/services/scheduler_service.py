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
    resolve_fba_inventory_pull_month,
    sync_fba_inventory,
)
from backend.services.amz_sop_after_sales_service import (
    TASK_CODE as AMZ_SOP_TASK_CODE,
    TASK_NAME as AMZ_SOP_TASK_NAME,
    AmzSopEtlError,
    run_amz_sop_chain,
)
from backend.services.inventory_report_source_sync_service import (
    SALES_VOLUME_TASK_CODE,
    SALES_VOLUME_TASK_NAME,
    TASK_CODE as INVENTORY_REPORT_TASK_CODE,
    TASK_NAME as INVENTORY_REPORT_TASK_NAME,
    InventoryReportSourceSyncError,
    sync_monthly_inventory_sales_volume,
    sync_monthly_inventory_report_sources,
)
from backend.services.inventory_report_etl_service import (
    fill_next_month_opening_inventory,
)


AMZ_TASK_CODE = "amz_monthly_order_profit_sync"
OPENING_INVENTORY_TASK_CODE = (
    "monthly_inventory_report_opening_inventory_fill"
)
OPENING_INVENTORY_TASK_NAME = "月度库存次月月初库存填充"
TASK_CODES = {
    AMZ_TASK_CODE,
    CLEARANCE_TASK_CODE,
    AMZ_SOP_TASK_CODE,
    INVENTORY_REPORT_TASK_CODE,
    SALES_VOLUME_TASK_CODE,
    OPENING_INVENTORY_TASK_CODE,
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
    # Keep this before run_id/log creation: rejected month labels must have no side effects.
    if task_code == CLEARANCE_TASK_CODE:
        stat_month = resolve_fba_inventory_pull_month(stat_month)
    month = stat_month or (
        previous_natural_month()
        if task_code in {
            AMZ_TASK_CODE,
            INVENTORY_REPORT_TASK_CODE,
            SALES_VOLUME_TASK_CODE,
            OPENING_INVENTORY_TASK_CODE,
        }
        else (end_date or datetime.now().date()).strftime("%Y-%m")
    )
    amz_months = [month] if task_code == AMZ_TASK_CODE else []
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
            result = _run_amazon_profit_months(
                amz_months,
                request_id=request_id,
                trigger_type=trigger_type,
            )
        else:
            if task_code == AMZ_SOP_TASK_CODE:
                lock_name = "sop:amz-after-sales-chain"
            elif task_code == INVENTORY_REPORT_TASK_CODE:
                lock_name = f"inventory:monthly-report-source:{month}"
            elif task_code == SALES_VOLUME_TASK_CODE:
                lock_name = f"inventory:monthly-sales-volume:{month}"
            elif task_code == OPENING_INVENTORY_TASK_CODE:
                lock_name = f"inventory:next-month-opening:{month}"
            else:
                lock_name = f"warehouse:amz-ebay-inventory-age:{month}"
            with repo.named_lock(lock_name) as acquired:
                if not acquired:
                    task_name = (
                        AMZ_SOP_TASK_NAME
                        if task_code == AMZ_SOP_TASK_CODE
                        else INVENTORY_REPORT_TASK_NAME
                        if task_code == INVENTORY_REPORT_TASK_CODE
                        else SALES_VOLUME_TASK_NAME
                        if task_code == SALES_VOLUME_TASK_CODE
                        else OPENING_INVENTORY_TASK_NAME
                        if task_code == OPENING_INVENTORY_TASK_CODE
                        else "AMZ FBA与eBay海外仓库存库龄同步"
                    )
                    raise SchedulerTaskAlreadyRunning(
                        f"{task_name}正在执行"
                    )
                if task_code == CLEARANCE_TASK_CODE:
                    result = sync_fba_inventory(month)
                elif task_code == INVENTORY_REPORT_TASK_CODE:
                    result = sync_monthly_inventory_report_sources(month)
                elif task_code == SALES_VOLUME_TASK_CODE:
                    result = sync_monthly_inventory_sales_volume(month)
                elif task_code == OPENING_INVENTORY_TASK_CODE:
                    result = fill_next_month_opening_inventory(month)
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
                (
                    AmazonProfitEtlError,
                    AmzSopEtlError,
                    InventoryReportSourceSyncError,
                ),
            )
            else "LOCK" if isinstance(exc, SchedulerTaskAlreadyRunning)
            else "UNKNOWN"
        )
        metrics = (
            exc.metrics
            if isinstance(
                exc,
                (
                    AmazonProfitEtlError,
                    AmzSopEtlError,
                    InventoryReportSourceSyncError,
                ),
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


def _run_amazon_profit_months(
    months: list[str],
    request_id: str,
    trigger_type: str,
) -> dict:
    """Refresh explicit months with one lock and transaction per month."""
    month_results: list[dict] = []
    trigger_source = (
        "scheduler_manual" if trigger_type == "manual" else "scheduler"
    )
    for target_month in months:
        lock_name = f"performance:amz-profit:{target_month}"
        with repo.named_lock(lock_name) as acquired:
            if not acquired:
                raise SchedulerTaskAlreadyRunning(
                    f"{target_month} AMZ月利润任务正在执行"
                )
            month_results.append(
                sync_amazon_monthly_profit(
                    stat_month=target_month,
                    request_id=request_id,
                    trigger_source=trigger_source,
                )
            )
    if len(month_results) == 1:
        return month_results[0]

    latest = month_results[-1]
    total_fields = (
        "extract_rows",
        "remote_rows",
        "ods_rows",
        "dwd_rows",
        "inserted_rows",
        "updated_rows",
        "deleted_rows",
        "skipped_rows",
        "invalid_rows",
        "duplicate_rows",
    )
    refresh = dict(latest.get("refresh", {}))
    refresh.update(
        {
            "status": "completed",
            "stat_months": months,
            "month_count": len(months),
            "amz_ranking_rows": sum(
                item.get("refresh", {}).get("amz_ranking_rows", 0)
                for item in month_results
            ),
            "combined_ranking_rows": sum(
                item.get("refresh", {}).get("combined_ranking_rows", 0)
                for item in month_results
            ),
        }
    )
    return {
        **latest,
        "stat_months": months,
        "month_count": len(months),
        "start_date": month_results[0]["start_date"],
        "end_date": latest["end_date"],
        "month_results": month_results,
        **{
            field: sum(item.get(field, 0) for item in month_results)
            for field in total_fields
        },
        "refresh": refresh,
    }


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
