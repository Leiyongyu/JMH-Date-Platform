"""任务可靠性字段。

revision: 002_task_reliability
Create Date: 2026-07-16
"""
revision = "002_task_reliability"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    # 如果字段还不存在则添加
    op.execute("""
        ALTER TABLE api_task
            ADD COLUMN IF NOT EXISTS idempotency_key CHAR(64) NULL
                COMMENT '幂等键' AFTER file_sha256,
            ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0
                COMMENT '已重试次数' AFTER error_message,
            ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 3
                COMMENT '最大重试次数' AFTER retry_count,
            ADD COLUMN IF NOT EXISTS next_retry_at DATETIME(3) NULL
                COMMENT '下次重试时间' AFTER max_retries,
            ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64) NULL
                COMMENT 'Worker标识' AFTER next_retry_at,
            ADD COLUMN IF NOT EXISTS heartbeat_at DATETIME(3) NULL
                COMMENT '心跳时间' AFTER worker_id,
            ADD COLUMN IF NOT EXISTS lease_expires_at DATETIME(3) NULL
                COMMENT '租约过期时间' AFTER heartbeat_at
    """)
    try:
        op.create_index("idx_api_task_idempotency", "api_task", ["idempotency_key"])
    except Exception:
        pass
    try:
        op.create_index("idx_api_task_recovery", "api_task", ["task_status", "lease_expires_at"])
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index("idx_api_task_recovery", table_name="api_task")
    except Exception:
        pass
    try:
        op.drop_index("idx_api_task_idempotency", table_name="api_task")
    except Exception:
        pass
