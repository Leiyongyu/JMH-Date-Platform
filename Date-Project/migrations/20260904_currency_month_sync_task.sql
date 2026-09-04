USE `date-project`;

-- 内部调度执行历史的实际表名为 scheduler_task_run（不是 scheduler_run）。
-- 某些旧部署库只建了任务定义表，这里补齐运行记录表；可重复执行。
CREATE TABLE IF NOT EXISTS scheduler_task_run (
  run_id VARCHAR(64) NOT NULL COMMENT '运行ID',
  task_code VARCHAR(80) NOT NULL COMMENT '任务编码',
  status VARCHAR(20) NOT NULL COMMENT '状态',
  stat_month CHAR(7) NULL COMMENT '统计月份',
  trigger_type VARCHAR(40) NOT NULL COMMENT '触发类型：scheduler/manual',
  source_rows INT NOT NULL DEFAULT 0 COMMENT '源行数',
  sync_batch_id VARCHAR(64) NULL COMMENT 'ODS同步批次ID',
  extract_rows INT NOT NULL DEFAULT 0 COMMENT '抽取行数',
  ods_rows INT NOT NULL DEFAULT 0 COMMENT 'ODS写入行数',
  inserted_rows INT NOT NULL DEFAULT 0 COMMENT '插入行数',
  updated_rows INT NOT NULL DEFAULT 0 COMMENT '更新行数',
  deleted_rows INT NOT NULL DEFAULT 0 COMMENT '删除行数',
  skipped_rows INT NOT NULL DEFAULT 0 COMMENT '跳过行数',
  amz_ranking_rows INT NOT NULL DEFAULT 0 COMMENT 'AMZ排名行数',
  combined_ranking_rows INT NOT NULL DEFAULT 0 COMMENT '综合排名行数',
  etl_stage VARCHAR(32) NULL COMMENT '当前或失败阶段',
  error_message TEXT NULL COMMENT '错误摘要',
  request_id VARCHAR(128) NULL COMMENT '请求ID',
  started_at DATETIME NULL COMMENT '开始时间',
  completed_at DATETIME NULL COMMENT '完成时间',
  PRIMARY KEY (run_id),
  KEY idx_scheduler_run_task (task_code, started_at),
  KEY idx_scheduler_run_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='内部定时任务运行记录表';

-- 独立领星月度汇率任务：默认禁用，仅供快速手动补拉；月度库存链路仍会自动同步。
INSERT INTO scheduler_task (
  task_code, task_name, cron_expression, enabled, description
) VALUES (
  'currency_month_sync',
  '领星月度汇率同步',
  '0 0 6 1 * ?',
  0,
  '拉取领星currencyMonth全部币种的当月汇率。默认禁用，需要时手动触发；月度库存源数据任务内部也会同步汇率，两者互不冲突。'
)
ON DUPLICATE KEY UPDATE
  task_name=VALUES(task_name),
  cron_expression=VALUES(cron_expression),
  description=VALUES(description);
