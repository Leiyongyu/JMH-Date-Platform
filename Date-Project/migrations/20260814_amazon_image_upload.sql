CREATE TABLE IF NOT EXISTS amazon_image_upload_task (
    task_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    request_id VARCHAR(64) NOT NULL COMMENT '跨服务请求ID',
    status VARCHAR(20) NOT NULL DEFAULT 'queued' COMMENT 'queued/running/completed/failed/stopped/rejected',
    created_by_id BIGINT NULL COMMENT 'ERP用户ID',
    created_by_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'ERP用户名',
    marketplace_code VARCHAR(16) NOT NULL DEFAULT 'DE' COMMENT 'Amazon站点',
    shop_count INT NOT NULL DEFAULT 0,
    total_sku INT NOT NULL DEFAULT 0,
    completed_sku INT NOT NULL DEFAULT 0,
    failed_sku INT NOT NULL DEFAULT 0,
    skipped_sku INT NOT NULL DEFAULT 0,
    current_message VARCHAR(1000) NULL,
    payload_json JSON NULL COMMENT '脱敏后的任务参数',
    executor_slot TINYINT NULL COMMENT '本机紫鸟执行器槽位1-5',
    automation_port INT NULL COMMENT '本次任务使用的紫鸟HTTP端口',
    error_message VARCHAR(2000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    started_at DATETIME(3) NULL,
    finished_at DATETIME(3) NULL,
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (task_id),
    KEY idx_amz_image_task_status_time (status, created_at),
    KEY idx_amz_image_task_request (request_id),
    KEY idx_amz_image_task_user (created_by_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon主图批量上传任务';

CREATE TABLE IF NOT EXISTS amazon_image_upload_task_log (
    log_id BIGINT NOT NULL AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    level VARCHAR(16) NOT NULL DEFAULT 'INFO',
    message VARCHAR(4000) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (log_id),
    KEY idx_amz_image_log_task (task_id, log_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon主图批量上传任务日志';

CREATE TABLE IF NOT EXISTS amazon_image_upload_progress (
    progress_key VARCHAR(500) NOT NULL COMMENT '用户作用域:SKU@站点@紫鸟店铺ID',
    sku VARCHAR(255) NOT NULL,
    marketplace_code VARCHAR(16) NOT NULL,
    ziniao_shop_id VARCHAR(128) NOT NULL DEFAULT '',
    last_task_id BIGINT NULL,
    completed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (progress_key),
    KEY idx_amz_image_progress_sku (sku, marketplace_code),
    KEY idx_amz_image_progress_task (last_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon主图批量上传断点记录';

CREATE TABLE IF NOT EXISTS amazon_image_upload_executor (
    executor_id TINYINT NOT NULL,
    active_task_id BIGINT NULL,
    claimed_at DATETIME(3) NULL,
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (executor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon主图上传单机五端口执行器状态';

INSERT INTO amazon_image_upload_executor (executor_id, active_task_id, claimed_at)
VALUES (1, NULL, NULL), (2, NULL, NULL), (3, NULL, NULL),
       (4, NULL, NULL), (5, NULL, NULL)
ON DUPLICATE KEY UPDATE executor_id=VALUES(executor_id);

CREATE TABLE IF NOT EXISTS amazon_image_upload_file_batch (
    batch_id VARCHAR(64) NOT NULL COMMENT '批次ID',
    request_id VARCHAR(64) NOT NULL COMMENT '跨服务请求ID',
    status VARCHAR(20) NOT NULL DEFAULT 'running'
        COMMENT 'running/completed/partial/failed',
    created_by_id BIGINT NULL COMMENT 'ERP用户ID',
    created_by_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'ERP用户名',
    ziniao_shop_id VARCHAR(128) NOT NULL,
    ziniao_shop_name VARCHAR(255) NOT NULL DEFAULT '',
    shop_folder VARCHAR(1000) NOT NULL COMMENT '执行主机本地店铺目录',
    requested_files INT NOT NULL DEFAULT 0,
    saved_files INT NOT NULL DEFAULT 0,
    skipped_files INT NOT NULL DEFAULT 0,
    total_bytes BIGINT NOT NULL DEFAULT 0,
    error_message VARCHAR(2000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    finished_at DATETIME(3) NULL,
    PRIMARY KEY (batch_id),
    KEY idx_amz_image_file_batch_user (created_by_id, created_at),
    KEY idx_amz_image_file_batch_shop (ziniao_shop_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon主图本地文件批量上传审计';
