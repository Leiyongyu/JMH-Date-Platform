"""全量同步 dim_shop 维度表。

从 ERP 业务库 jmh_data_platform.shop_list 读取店铺数据，
全量覆盖写入 jmh_report.dim_shop。
"""

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from app.db.report import report_engine


SQL_DIR = Path(__file__).resolve().parent.parent.parent / "sql" / "dim"


def sync_dim_shop():
    batch_id = f"dim_shop_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    sql_path = SQL_DIR / "sync_dim_shop.sql"
    sql = sql_path.read_text(encoding="utf-8")

    start_time = datetime.now()
    status = "success"
    error_message = None

    # 写入 etl_batch
    with report_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO etl_batch (batch_id, batch_type, status, start_time) "
                "VALUES (:batch_id, 'sync_dim', 'running', :start_time)"
            ),
            {"batch_id": batch_id, "start_time": start_time},
        )

    # 写入 etl_job_log
    with report_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO etl_job_log (job_code, batch_id, status, start_time) "
                "VALUES (:job_code, :batch_id, 'running', :start_time)"
            ),
            {"job_code": "sync_dim_shop", "batch_id": batch_id, "start_time": start_time},
        )

    try:
        # 执行同步 SQL
        with report_engine.begin() as conn:
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            for statement in statements:
                conn.execute(text(statement))

        # 统计写入行数
        with report_engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) AS cnt FROM jmh_report.dim_shop")
            ).fetchone()
            insert_count = row.cnt

        end_time = datetime.now()

        # 更新 etl_batch 成功
        with report_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE etl_batch SET status = 'success', end_time = :end_time "
                    "WHERE batch_id = :batch_id"
                ),
                {"batch_id": batch_id, "end_time": end_time},
            )

        # 更新 etl_job_log 成功
        with report_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE etl_job_log SET status = 'success', end_time = :end_time, "
                    "insert_count = :insert_count "
                    "WHERE batch_id = :batch_id AND job_code = :job_code"
                ),
                {
                    "batch_id": batch_id,
                    "job_code": "sync_dim_shop",
                    "end_time": end_time,
                    "insert_count": insert_count,
                },
            )

    except Exception as e:
        status = "failed"
        error_message = str(e)
        end_time = datetime.now()

        # 更新失败日志
        with report_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE etl_job_log SET status = 'failed', end_time = :end_time, "
                    "error_message = :error_message "
                    "WHERE batch_id = :batch_id AND job_code = :job_code"
                ),
                {
                    "batch_id": batch_id,
                    "job_code": "sync_dim_shop",
                    "end_time": end_time,
                    "error_message": error_message,
                },
            )

        raise

    return {
        "job_code": "sync_dim_shop",
        "batch_id": batch_id,
        "status": status,
        "insert_count": insert_count,
    }


if __name__ == "__main__":
    result = sync_dim_shop()
    print(result)
