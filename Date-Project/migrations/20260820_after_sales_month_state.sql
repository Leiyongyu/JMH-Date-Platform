CREATE TABLE IF NOT EXISTS etl_after_sales_month_state (
    platform VARCHAR(16) NOT NULL COMMENT '平台：AMZ或EBAY',
    stat_month CHAR(7) NOT NULL COMMENT '统计月份，格式YYYY-MM',
    month_start DATE NOT NULL COMMENT '自然月开始日期',
    month_end DATE NOT NULL COMMENT '自然月结束日期',
    sales_row_count BIGINT NOT NULL DEFAULT 0 COMMENT '该月清洗后销量数据行数',
    after_sales_row_count BIGINT NOT NULL DEFAULT 0 COMMENT '该月清洗后售后数据行数，允许为0',
    is_finalized TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已按完整自然月成功拉取或上传',
    source_version BIGINT NOT NULL DEFAULT 1 COMMENT '数据版本；每次成功覆盖自动递增',
    sync_batch_id VARCHAR(128) NULL COMMENT '最近一次成功同步或导入批次ID',
    synced_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近一次成功完成时间',
    PRIMARY KEY (platform, stat_month),
    KEY idx_after_sales_month_state_period (platform, month_start, month_end),
    KEY idx_after_sales_month_state_finalized (platform, is_finalized, stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='售后模块自然月数据完成状态；用于识别零售后月份和跨月首次补拉';

CREATE TABLE IF NOT EXISTS etl_after_sales_range_state (
    platform VARCHAR(16) NOT NULL COMMENT '平台：AMZ或EBAY',
    period_start DATE NOT NULL COMMENT '查询区间开始日期',
    period_end DATE NOT NULL COMMENT '查询区间结束日期',
    calculation_version VARCHAR(32) NOT NULL COMMENT '计算口径版本',
    source_version BIGINT NOT NULL COMMENT '区间内月份数据版本之和',
    summary_row_count BIGINT NOT NULL DEFAULT 0 COMMENT '生成的汇总行数，允许为0',
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '汇总完成时间',
    PRIMARY KEY (platform, period_start, period_end, calculation_version),
    KEY idx_after_sales_range_state_generated (platform, generated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='售后月份区间计算缓存状态；即使汇总为0行也记录为已完成';

INSERT INTO etl_after_sales_month_state (
    platform, stat_month, month_start, month_end, sales_row_count,
    after_sales_row_count, is_finalized, source_version, sync_batch_id, synced_at
)
SELECT 'AMZ', DATE_FORMAT(s.period_start, '%Y-%m'), s.period_start,
       MAX(s.period_end), COUNT(*),
       (SELECT COUNT(*) FROM dwd_amz_sop_after_sales a
        WHERE a.after_time >= s.period_start
          AND a.after_time < DATE_ADD(LAST_DAY(s.period_start), INTERVAL 1 DAY)),
       IF(MAX(s.period_end) = LAST_DAY(s.period_start)
          AND LAST_DAY(s.period_start) < CURRENT_DATE, 1, 0), 1,
       MAX(s.sync_batch_id), CURRENT_TIMESTAMP
FROM dwd_amz_sop_sales_daily s
GROUP BY s.period_start
ON DUPLICATE KEY UPDATE
    month_start=VALUES(month_start), month_end=VALUES(month_end),
    sales_row_count=VALUES(sales_row_count),
    after_sales_row_count=VALUES(after_sales_row_count);

INSERT INTO etl_after_sales_month_state (
    platform, stat_month, month_start, month_end, sales_row_count,
    after_sales_row_count, is_finalized, source_version, sync_batch_id, synced_at
)
SELECT 'EBAY', DATE_FORMAT(s.month_start, '%Y-%m'), s.month_start,
       LAST_DAY(s.month_start), COUNT(*),
       (SELECT COUNT(*) FROM dwd_ebay_sop_after_sales a
        WHERE a.after_time >= s.month_start
          AND a.after_time < DATE_ADD(LAST_DAY(s.month_start), INTERVAL 1 DAY)),
       1, 1, MAX(s.import_batch_id), CURRENT_TIMESTAMP
FROM dwd_ebay_sop_sales_monthly s
GROUP BY s.month_start
ON DUPLICATE KEY UPDATE
    month_start=VALUES(month_start), month_end=VALUES(month_end),
    sales_row_count=VALUES(sales_row_count),
    after_sales_row_count=VALUES(after_sales_row_count), is_finalized=1;
