"""APScheduler 调度器。

管理所有报表 ETL 定时任务。
ERP Quartz 管业务同步，Python APScheduler 管报表 ETL，各管各的。
统一监控通过 ERP 页面读取 jmh_report.etl_job_log。

cron 表达式统一放 .env，不写死在代码里。
"""

import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.etl.build_monthly_opening_inventory_value import build_monthly_opening_inventory_value
from app.etl.sync_dim_shop import sync_dim_shop
from app.etl.sync_dim_warehouse import sync_dim_warehouse
from app.etl.sync_lingxing_local_inventory import sync_lingxing_local_inventory

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=4)},
    job_defaults={
        "coalesce": True,         # 错过不追跑
        "max_instances": 1,       # 同一任务不并发
        "misfire_grace_time": 600,  # 迟到 10 分钟内仍可执行
    },
)


def _wrap(job_code: str, fn):
    """包装任务函数，统一异常捕获和日志。"""

    def wrapper():
        logger.info("[%s] started", job_code)
        try:
            result = fn()
            logger.info("[%s] done: %s", job_code, result)
        except Exception:
            logger.exception("[%s] failed", job_code)

    return wrapper


def start_scheduler():
    """注册所有 ETL 定时任务并启动调度器。"""

    jobs = [
        ("sync_dim_shop", _wrap("sync_dim_shop", sync_dim_shop), settings.sync_dim_shop_cron),
        ("sync_dim_warehouse", _wrap("sync_dim_warehouse", sync_dim_warehouse), settings.sync_dim_warehouse_cron),
        ("sync_lingxing_local_inventory_report",
         _wrap("sync_lingxing_local_inventory_report", sync_lingxing_local_inventory),
         settings.lingxing_local_inventory_daily_cron),
        ("build_monthly_opening_inventory_value",
         _wrap("build_monthly_opening_inventory_value", build_monthly_opening_inventory_value),
         settings.monthly_opening_inventory_cron),
    ]

    for job_code, func, cron_expr in jobs:
        scheduler.add_job(
            func,
            trigger=CronTrigger.from_crontab(cron_expr),
            id=job_code,
            name=job_code,
            replace_existing=True,
        )
        logger.info("registered job: %s  cron=%s", job_code, cron_expr)

    scheduler.start()
    logger.info("scheduler started, %d jobs", len(jobs))

    return scheduler


def shutdown_scheduler():
    """关闭调度器，等待当前任务完成。"""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("scheduler stopped")
