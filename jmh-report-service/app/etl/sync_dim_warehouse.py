"""全量同步 dim_warehouse 维度表。

从 ERP 业务库 jmh_data_platform.warehouse 读取仓库数据，
将 type/sub_type 编码映射后全量覆盖写入 jmh_report.dim_warehouse。

映射规则：
  type=1 → LOCAL 本地仓
  type=3 → OVERSEAS 海外仓
  type=4 → FBA 亚马逊平台仓
  type=6 → AWD AWD仓
"""

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from app.db.report import report_engine


SQL_DIR = Path(__file__).resolve().parent.parent.parent / "sql" / "dim"


def sync_dim_warehouse():
    batch_id = f"dim_warehouse_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    sql_path = SQL_DIR / "sync_dim_warehouse.sql"
    sql = sql_path.read_text(encoding="utf-8")

    start_time = datetime.now()
    job_code = "sync_dim_warehouse"

    # etl_batch
    with report_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO etl_batch (batch_id, batch_type, status, start_time) "
                "VALUES (:batch_id, 'sync_dim', 'running', :start_time)"
            ),
            {"batch_id": batch_id, "start_time": start_time},
        )

    # etl_job_log
    with report_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO etl_job_log (job_code, batch_id, status, start_time) "
                "VALUES (:job_code, :batch_id, 'running', :start_time)"
            ),
            {"job_code": job_code, "batch_id": batch_id, "start_time": start_time},
        )

    try:
        with report_engine.begin() as conn:
            for statement in [s.strip() for s in sql.split(";") if s.strip()]:
                conn.execute(text(statement))

        with report_engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) AS cnt FROM dim_warehouse")
            ).fetchone()
            insert_count = row.cnt

        end_time = datetime.now()

        with report_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE etl_batch SET status = 'success', end_time = :end_time "
                    "WHERE batch_id = :batch_id"
                ),
                {"batch_id": batch_id, "end_time": end_time},
            )

        with report_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE etl_job_log SET status = 'success', end_time = :end_time, "
                    "insert_count = :insert_count "
                    "WHERE batch_id = :batch_id AND job_code = :job_code"
                ),
                {
                    "batch_id": batch_id,
                    "job_code": job_code,
                    "end_time": end_time,
                    "insert_count": insert_count,
                },
            )

    except Exception as e:
        end_time = datetime.now()
        error_message = str(e)

        with report_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE etl_job_log SET status = 'failed', end_time = :end_time, "
                    "error_message = :error_message "
                    "WHERE batch_id = :batch_id AND job_code = :job_code"
                ),
                {
                    "batch_id": batch_id,
                    "job_code": job_code,
                    "end_time": end_time,
                    "error_message": error_message,
                },
            )
        raise

    return {
        "job_code": job_code,
        "batch_id": batch_id,
        "status": "success",
        "insert_count": insert_count,
    }


if __name__ == "__main__":
    result = sync_dim_warehouse()
    print(result)
