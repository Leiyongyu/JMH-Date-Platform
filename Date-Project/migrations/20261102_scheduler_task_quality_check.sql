-- 定时任务数据质量门禁检查结果。与 scheduler_task_run 按 run_id 一对一。
CREATE TABLE IF NOT EXISTS scheduler_task_quality_check (
    run_id VARCHAR(64) NOT NULL COMMENT '运行ID，对应 scheduler_task_run.run_id',
    task_code VARCHAR(80) NOT NULL COMMENT '任务编码',
    status VARCHAR(16) NOT NULL COMMENT '检查结果：passed 通过 / warning 有告警 / failed 有阻断级问题',
    issues JSON NULL COMMENT '问题明细：规则、级别、说明、实际值、阈值',
    checked_at DATETIME NOT NULL COMMENT '检查时间',
    PRIMARY KEY (run_id),
    KEY idx_quality_task_time (task_code, checked_at),
    KEY idx_quality_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='定时任务数据质量检查结果表';
