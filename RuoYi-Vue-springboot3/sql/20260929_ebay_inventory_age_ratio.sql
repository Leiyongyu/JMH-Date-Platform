-- 在 Python 业务库执行（当前为 date-project），不是 Java jmh_data_platform。
-- 幂等建表，不更新旧清货/月度/库存快照，不触发谷仓或领星接口。
USE `date-project`;
CREATE TABLE IF NOT EXISTS ebay_inventory_age_ratio_snapshot (
  stat_date DATE NOT NULL COMMENT '北京时间统计日期，同日刷新覆盖，跨日保留',
  generated_at DATETIME NOT NULL COMMENT '实际重新计算时间',
  source_batch_id VARCHAR(64) NOT NULL COMMENT '谷仓latest源批次',
  report_json JSON NOT NULL COMMENT '个人与站点货值占比、源时间、规则月份及未计价明细冻结快照',
  PRIMARY KEY (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='海外仓库龄占比日快照：实际数量乘采购及头程单价';
