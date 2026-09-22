from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import uuid4

from backend.repositories import performance_repository as repo
from backend.services.ebay_token_health_service import (
    TASK_CODE as EBAY_HEALTH_TASK_CODE, check_ebay_token_health,
)
from backend.services.ebay_store_listing_sync_service import (
    TASK_CODE as EBAY_STORE_LISTING_TASK_CODE,
    TASK_NAME as EBAY_STORE_LISTING_TASK_NAME,
    EbayStoreListingSyncError,
    sync_ebay_store_listings,
)
from backend.services.amz_listing_raw_sync_service import (
    TASK_CODE as AMZ_LISTING_RAW_TASK_CODE,
    TASK_NAME as AMZ_LISTING_RAW_TASK_NAME,
    AmzListingRawSyncError,
    sync_amz_listing_raw,
)
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
from backend.services.currency_sync_service import (
    TASK_CODE as CURRENCY_TASK_CODE,
    sync_currency_month,
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


from backend.services.weekly_inventory_sync_service import (
    TASK_CODE as WEEKLY_INVENTORY_TASK_CODE,
    sync_weekly_inventory,
)
from backend.services.weekly_inventory_regenerate_service import regenerate_weekly_inventory
from backend.services.goodcang_storage_sync_service import (
    TASK_CODE as GOODCANG_STORAGE_TASK_CODE,
    TASK_NAME as GOODCANG_STORAGE_TASK_NAME,
    GoodcangStorageSyncError,
    sync_goodcang_storage,
)

AMZ_TASK_CODE = "amz_monthly_order_profit_sync"
OPENING_INVENTORY_TASK_CODE = (
    "monthly_inventory_report_opening_inventory_fill"
)
OPENING_INVENTORY_TASK_NAME = "月度库存次月月初库存填充"


class SchedulerTaskAlreadyRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskContext:
    """一次调度执行的入参上下文；spec 的各个钩子只读它，不再读全局 task_code。"""

    task_code: str
    month: str
    start_date: object = None
    end_date: object = None
    request_id: str = ""
    trigger_type: str = "manual"
    weekly_snapshot_only: bool = False


@dataclass(frozen=True)
class TaskSpec:
    """单个任务的全部差异点。公共调度流程只读这里，不再按 task_code 分支。

    execute / lock_name 一律写成 lambda，目的是把模块级函数名推迟到调用时
    才解析；测试大量使用 monkeypatch.setattr(scheduler_service, "xxx", ...)
    替换执行函数，提前绑定会让这些替换全部失效。
    """

    code: str
    name: str
    execute: Callable[[TaskContext], dict]
    # 非空表示该任务拒绝历史月份/日期入参，值即拒绝提示文案。
    period_args_error: str | None = None
    # 覆盖 stat_month 的解析方式；目前只有 FBA 库龄任务需要。
    resolve_month: Callable[[str | None], str] | None = None
    # True 缺省取上一个自然月；False 取 end_date 或当天所在月。
    default_previous_month: bool = False
    # None 表示任务自管锁（AMZ 月利润按月各加各的锁），调度器不套外层锁。
    lock_name: Callable[[TaskContext], str] | None = None


TASK_SPECS: dict[str, TaskSpec] = {
    spec.code: spec
    for spec in (
        TaskSpec(
            code=EBAY_HEALTH_TASK_CODE,
            name="eBay密钥健康检查",
            period_args_error="密钥健康检查只检查当前状态，不接受历史日期",
            lock_name=lambda ctx: "ebay:token-health:check",
            execute=lambda ctx: check_ebay_token_health(),
        ),
        TaskSpec(
            code=EBAY_STORE_LISTING_TASK_CODE,
            name=EBAY_STORE_LISTING_TASK_NAME,
            period_args_error="eBay店铺商品仅拉取当前在售列表，不接受历史月份或日期",
            lock_name=lambda ctx: "ebay:store-listing:replace",
            execute=lambda ctx: sync_ebay_store_listings(),
        ),
        TaskSpec(
            code=AMZ_LISTING_RAW_TASK_CODE,
            name=AMZ_LISTING_RAW_TASK_NAME,
            period_args_error="AMZ原始刊登只拉取当前完整数据，不接受历史月份或日期筛选",
            lock_name=lambda ctx: "lingxing:amz-listing-raw:replace",
            execute=lambda ctx: sync_amz_listing_raw(),
        ),
        TaskSpec(
            code=WEEKLY_INVENTORY_TASK_CODE,
            name="仓位库存明细周报",
            period_args_error="仓位库存周报仅拉取当前实时快照，不接受历史月份或日期",
            # 「重新拉取」与「只用已有快照生成」共用同一把锁，不能各用各的。
            lock_name=lambda ctx: "inventory:weekly-export",
            execute=lambda ctx: (
                regenerate_weekly_inventory()
                if ctx.weekly_snapshot_only
                else sync_weekly_inventory(ctx.trigger_type)
            ),
        ),
        TaskSpec(
            code=GOODCANG_STORAGE_TASK_CODE,
            name=GOODCANG_STORAGE_TASK_NAME,
            period_args_error="谷仓仓租概要固定同步包含当天的最近30天，不接受自定义月份或日期",
            # 整表覆盖：按月锁不足以互斥，必须全局锁。
            lock_name=lambda ctx: "goodcang:warehouse-storage:replace",
            execute=lambda ctx: sync_goodcang_storage(),
        ),
        TaskSpec(
            code=AMZ_TASK_CODE,
            name="AMZ月度订单利润同步",
            default_previous_month=True,
            # 自管锁：_run_amazon_profit_months 按月逐个加锁并各自成事务，
            # 外层再套一把同名锁会变成重复加锁。
            lock_name=None,
            execute=lambda ctx: _run_amazon_profit_months(
                [ctx.month],
                request_id=ctx.request_id,
                trigger_type=ctx.trigger_type,
            ),
        ),
        TaskSpec(
            code=CLEARANCE_TASK_CODE,
            name="AMZ FBA与eBay海外仓库存库龄同步",
            resolve_month=lambda value: resolve_fba_inventory_pull_month(value),
            lock_name=lambda ctx: f"warehouse:amz-ebay-inventory-age:{ctx.month}",
            execute=lambda ctx: sync_fba_inventory(ctx.month),
        ),
        TaskSpec(
            code=AMZ_SOP_TASK_CODE,
            name=AMZ_SOP_TASK_NAME,
            lock_name=lambda ctx: "sop:amz-after-sales-chain",
            execute=lambda ctx: run_amz_sop_chain(
                start_date=ctx.start_date,
                end_date=ctx.end_date,
                request_id=ctx.request_id,
            ),
        ),
        TaskSpec(
            code=INVENTORY_REPORT_TASK_CODE,
            name=INVENTORY_REPORT_TASK_NAME,
            default_previous_month=True,
            lock_name=lambda ctx: f"inventory:monthly-report-source:{ctx.month}",
            execute=lambda ctx: sync_monthly_inventory_report_sources(ctx.month),
        ),
        TaskSpec(
            code=SALES_VOLUME_TASK_CODE,
            name=SALES_VOLUME_TASK_NAME,
            default_previous_month=True,
            lock_name=lambda ctx: f"inventory:monthly-sales-volume:{ctx.month}",
            execute=lambda ctx: sync_monthly_inventory_sales_volume(ctx.month),
        ),
        TaskSpec(
            code=OPENING_INVENTORY_TASK_CODE,
            name=OPENING_INVENTORY_TASK_NAME,
            default_previous_month=True,
            lock_name=lambda ctx: f"inventory:next-month-opening:{ctx.month}",
            execute=lambda ctx: fill_next_month_opening_inventory(ctx.month),
        ),
        TaskSpec(
            code=CURRENCY_TASK_CODE,
            name="领星月度汇率同步",
            lock_name=lambda ctx: f"currency:lingxing-month:{ctx.month}",
            execute=lambda ctx: sync_currency_month(ctx.month),
        ),
    )
}

TASK_CODES = frozenset(TASK_SPECS)

# 这些异常自带 stage/metrics，失败运行记录据此还原阶段和已处理行数。
_STAGED_ERRORS = (
    EbayStoreListingSyncError,
    AmzListingRawSyncError,
    AmazonProfitEtlError,
    AmzSopEtlError,
    InventoryReportSourceSyncError,
    GoodcangStorageSyncError,
)


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
    weekly_snapshot_only: bool = False,
) -> dict:
    spec = TASK_SPECS.get(task_code)
    if spec is None:
        raise ValueError("未知任务编码")
    if weekly_snapshot_only and task_code != WEEKLY_INVENTORY_TASK_CODE:
        raise ValueError("仅周报任务支持已有快照生成")
    # Keep this before run_id/log creation: rejected month labels must have no side effects.
    if spec.period_args_error and any(
        value is not None for value in (stat_month, start_date, end_date)
    ):
        raise ValueError(spec.period_args_error)
    if spec.resolve_month is not None:
        stat_month = spec.resolve_month(stat_month)
    month = stat_month or (
        previous_natural_month()
        if spec.default_previous_month
        else (end_date or datetime.now().date()).strftime("%Y-%m")
    )
    context = TaskContext(
        task_code=task_code,
        month=month,
        start_date=start_date,
        end_date=end_date,
        request_id=request_id,
        trigger_type=trigger_type,
        weekly_snapshot_only=weekly_snapshot_only,
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
        if spec.lock_name is None:
            result = spec.execute(context)
        else:
            with repo.named_lock(spec.lock_name(context)) as acquired:
                if not acquired:
                    raise SchedulerTaskAlreadyRunning(f"{spec.name}正在执行")
                result = spec.execute(context)
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
        staged = isinstance(exc, _STAGED_ERRORS)
        etl_stage = (
            exc.stage
            if staged
            else "LOCK" if isinstance(exc, SchedulerTaskAlreadyRunning)
            else "UNKNOWN"
        )
        metrics = exc.metrics if staged else {}
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
