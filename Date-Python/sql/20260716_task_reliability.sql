-- 任务可靠性字段（api_task 增量迁移）
-- 执行前应备份数据库；兼容不支持 ADD COLUMN IF NOT EXISTS 的 MySQL。
USE export_tax_refund;
SET @schema_name = DATABASE();

SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='idempotency_key')=0,
    'ALTER TABLE api_task ADD COLUMN idempotency_key CHAR(64) NULL COMMENT ''幂等键SHA-256'' AFTER file_sha256', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='retry_count')=0,
    'ALTER TABLE api_task ADD COLUMN retry_count INT NOT NULL DEFAULT 0 COMMENT ''已重试次数'' AFTER error_message', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='max_retries')=0,
    'ALTER TABLE api_task ADD COLUMN max_retries INT NOT NULL DEFAULT 3 COMMENT ''最大重试次数'' AFTER retry_count', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='next_retry_at')=0,
    'ALTER TABLE api_task ADD COLUMN next_retry_at DATETIME(3) NULL COMMENT ''下次重试时间'' AFTER max_retries', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='worker_id')=0,
    'ALTER TABLE api_task ADD COLUMN worker_id VARCHAR(64) NULL COMMENT ''执行任务的worker标识'' AFTER next_retry_at', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='heartbeat_at')=0,
    'ALTER TABLE api_task ADD COLUMN heartbeat_at DATETIME(3) NULL COMMENT ''Worker最后心跳时间'' AFTER worker_id', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='lease_expires_at')=0,
    'ALTER TABLE api_task ADD COLUMN lease_expires_at DATETIME(3) NULL COMMENT ''任务租约过期时间'' AFTER heartbeat_at', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND INDEX_NAME='idx_api_task_idempotency')=0,
    'CREATE INDEX idx_api_task_idempotency ON api_task (idempotency_key)', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND INDEX_NAME='idx_api_task_recovery')=0,
    'CREATE INDEX idx_api_task_recovery ON api_task (task_status, lease_expires_at)', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
