USE export_tax_refund;

CREATE TABLE IF NOT EXISTS api_task (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '统一API任务主键',
    task_type VARCHAR(50) NOT NULL COMMENT '任务类型',
    task_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/PARTIAL/FAILED',
    progress_current INT NOT NULL DEFAULT 0,
    progress_total INT NOT NULL DEFAULT 0,
    request_payload JSON NULL COMMENT '任务请求参数',
    result_payload JSON NULL COMMENT '任务执行结果',
    error_message TEXT NULL,
    original_file_name VARCHAR(255) NULL,
    stored_file_path VARCHAR(1000) NULL,
    file_sha256 CHAR(64) NULL,
    created_by VARCHAR(64) NOT NULL DEFAULT 'ERP',
    started_at DATETIME(3) NULL,
    completed_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_api_task_type_status (task_type, task_status),
    KEY idx_api_task_created_at (created_at),
    KEY idx_api_task_file_hash (file_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='ERP调用Python服务的统一任务资源';
