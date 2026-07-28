-- AMZ + eBay 综合绩效排名汇总表。
-- 可重复执行；需先执行 AMZ 与 eBay 绩效排名建表脚本。

CREATE TABLE IF NOT EXISTS `combined_performance_ranking` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM',
  `principal_name` varchar(200) NOT NULL COMMENT '负责人',
  `gross_profit` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT 'AMZ与eBay毛利润合计',
  `net_sales_amount` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT 'AMZ与eBay净销售额合计',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_combined_perf_month_owner` (`stat_month`,`principal_name`),
  KEY `idx_combined_perf_month_gross` (`stat_month`,`gross_profit`),
  KEY `idx_combined_perf_month_net` (`stat_month`,`net_sales_amount`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AMZ与eBay综合负责人月度绩效排名';

SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'combined_performance_ranking';
