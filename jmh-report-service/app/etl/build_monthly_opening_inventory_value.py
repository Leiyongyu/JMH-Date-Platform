"""生成月初期初库存货值检查结果。

业务口径：
- 在领星库存报表选择某个月 1 号，按明细和显示数量检查期初数量/成本。
- 当前先接入本地仓 LOCAL，数据来自 ods_lingxing_local_inventory_report_detail。
- 只使用 is_total_row=1 的父汇总行，避免把可售/待检/不可售子行重复累加。
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text

from app.db.report import report_engine


JOB_CODE = "build_monthly_opening_inventory_value"
SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "ads"


def _first_day_of_current_month() -> date:
    today = date.today()
    return today.replace(day=1)


def _parse_date(value: str | None) -> date:
    if not value:
        return _first_day_of_current_month()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _ensure_ads_table():
    sql_path = SQL_DIR / "create_ads_monthly_opening_inventory_value.sql"
    sql = sql_path.read_text(encoding="utf-8")
    with report_engine.begin() as conn:
        conn.execute(text(sql))


def build_monthly_opening_inventory_value(target_date: date | None = None) -> dict:
    report_date = target_date or _first_day_of_current_month()
    batch_id = f"monthly_opening_inventory_{report_date.strftime('%Y%m%d')}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now()
    status = "success"
    error_message = None
    inserted_rows = 0
    source_rows = 0

    _ensure_ads_table()

    with report_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO etl_batch (batch_id, batch_type, business_date, status, start_time) "
                "VALUES (:batch_id, :batch_type, :business_date, 'running', :start_time)"
            ),
            {
                "batch_id": batch_id,
                "batch_type": JOB_CODE,
                "business_date": report_date,
                "start_time": started_at,
            },
        )
        conn.execute(
            text(
                "INSERT INTO etl_job_log (job_code, batch_id, status, start_time) "
                "VALUES (:job_code, :batch_id, 'running', :start_time)"
            ),
            {"job_code": JOB_CODE, "batch_id": batch_id, "start_time": started_at},
        )

    try:
        with report_engine.begin() as conn:
            source_rows = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM ods_lingxing_local_inventory_report_detail
                    WHERE report_start_date = :report_date
                      AND report_end_date = :report_date
                      AND source_system = 'LINGXING'
                      AND is_total_row = 1
                    """
                ),
                {"report_date": report_date},
            ).scalar() or 0

            conn.execute(
                text(
                    """
                    DELETE FROM ads_monthly_opening_inventory_value
                    WHERE report_date = :report_date
                      AND source_system = 'LINGXING'
                      AND warehouse_type = 'LOCAL'
                    """
                ),
                {"report_date": report_date},
            )

            result = conn.execute(
                text(
                    """
                    INSERT INTO ads_monthly_opening_inventory_value (
                      batch_id, report_date, source_system, platform,
                      warehouse_type, warehouse_type_name, sys_wid, warehouse_name,
                      seller_name, sku, fnsku, spu, product_name, brand,
                      category1, category2, category3,
                      opening_qty, opening_cost, unit_cost,
                      cost_status, anomaly_flag, anomaly_reason, source_ods_id
                    )
                    SELECT
                      :batch_id AS batch_id,
                      :report_date AS report_date,
                      'LINGXING' AS source_system,
                      'LINGXING' AS platform,
                      'LOCAL' AS warehouse_type,
                      COALESCE(w.warehouse_type_name, '本地仓') AS warehouse_type_name,
                      COALESCE(o.sys_wid, 0) AS sys_wid,
                      COALESCE(o.ware_house_name, w.warehouse_name) AS warehouse_name,
                      o.seller_name,
                      COALESCE(o.sku, '') AS sku,
                      COALESCE(o.fnsku, '') AS fnsku,
                      o.spu,
                      o.product_name,
                      o.brand,
                      o.category1,
                      o.category2,
                      o.category3,
                      o.day_early_count AS opening_qty,
                      o.day_early_cost AS opening_cost,
                      CASE
                        WHEN o.day_early_count IS NULL OR o.day_early_count = 0 THEN NULL
                        ELSE ROUND(COALESCE(o.day_early_cost, 0) / o.day_early_count, 6)
                      END AS unit_cost,
                      CASE
                        WHEN o.day_early_count IS NULL OR o.day_early_count = 0 THEN 'ZERO_QTY'
                        WHEN o.day_early_cost IS NULL THEN 'MISSING_COST'
                        WHEN o.day_early_cost = 0 THEN 'ZERO_COST'
                        ELSE 'OK'
                      END AS cost_status,
                      CASE
                        WHEN o.day_early_count IS NULL OR o.day_early_count = 0 THEN 0
                        WHEN o.day_early_cost IS NULL OR o.day_early_cost = 0 THEN 1
                        ELSE 0
                      END AS anomaly_flag,
                      CASE
                        WHEN o.day_early_count IS NULL OR o.day_early_count = 0 THEN '期初数量为0，不参与成本异常'
                        WHEN o.day_early_cost IS NULL THEN '期初数量不为0，但期初成本为空'
                        WHEN o.day_early_cost = 0 THEN '期初数量不为0，但期初成本为0'
                        ELSE NULL
                      END AS anomaly_reason,
                      o.id AS source_ods_id
                    FROM ods_lingxing_local_inventory_report_detail o
                    LEFT JOIN dim_warehouse w
                      ON w.warehouse_id = o.sys_wid
                    WHERE o.report_start_date = :report_date
                      AND o.report_end_date = :report_date
                      AND o.source_system = 'LINGXING'
                      AND o.is_total_row = 1
                    """
                ),
                {"batch_id": batch_id, "report_date": report_date},
            )
            inserted_rows = result.rowcount or 0

        return {
            "batch_id": batch_id,
            "report_date": report_date.isoformat(),
            "source_rows": source_rows,
            "inserted_rows": inserted_rows,
        }
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        ended_at = datetime.now()
        duration = int((ended_at - started_at).total_seconds())
        with report_engine.begin() as conn:
            conn.execute(
                text("UPDATE etl_batch SET status=:status, end_time=:end_time, remark=:remark WHERE batch_id=:batch_id"),
                {
                    "status": status,
                    "end_time": ended_at,
                    "remark": error_message,
                    "batch_id": batch_id,
                },
            )
            conn.execute(
                text(
                    "UPDATE etl_job_log SET status=:status, end_time=:end_time, duration_seconds=:duration_seconds, "
                    "read_count=:read_count, insert_count=:insert_count, update_count=0, "
                    "error_count=:error_count, error_message=:error_message "
                    "WHERE job_code=:job_code AND batch_id=:batch_id"
                ),
                {
                    "status": status,
                    "end_time": ended_at,
                    "duration_seconds": duration,
                    "read_count": source_rows,
                    "insert_count": inserted_rows,
                    "error_count": 1 if status == "failed" else 0,
                    "error_message": error_message,
                    "job_code": JOB_CODE,
                    "batch_id": batch_id,
                },
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="期初库存日期，格式 YYYY-MM-DD；默认当月1日")
    args = parser.parse_args()
    result = build_monthly_opening_inventory_value(_parse_date(args.date))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
