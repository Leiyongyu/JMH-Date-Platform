-- 任务可靠性字段（api_task 增量迁移）
-- 执行前应备份数据库
USE export_tax_refund;

ALTER TABLE api_task
    ADD COLUMN IF NOT EXISTS idempotency_key CHAR(64) NULL
        COMMENT '幂等键（SHA256(file_sha256 + task_type)）'
        AFTER file_sha256,
    ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0
        COMMENT '已重试次数'
        AFTER error_message,
    ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 3
        COMMENT '最大重试次数'
        AFTER retry_count,
    ADD COLUMN IF NOT EXISTS next_retry_at DATETIME(3) NULL
        COMMENT '下次重试时间'
        AFTER max_retries,
    ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64) NULL
        COMMENT '执行该任务的 worker 标识'
        AFTER next_retry_at,
    ADD COLUMN IF NOT EXISTS heartbeat_at DATETIME(3) NULL
        COMMENT 'Worker 最后心跳时间'
        AFTER worker_id,
    ADD COLUMN IF NOT EXISTS lease_expires_at DATETIME(3) NULL
        COMMENT '任务租约过期时间'
        AFTER heartbeat_at;

-- 幂等键索引（用于重复提交检测）
CREATE INDEX IF NOT EXISTS idx_api_task_idempotency
    ON api_task (idempotency_key);

-- 恢复查询索引
CREATE INDEX IF NOT EXISTS idx_api_task_recovery
    ON api_task (task_status, lease_expires_at);
