-- 在 Python 数据库 date-project 执行。仅新建报表表，不修改刊登、补货、绩效源表。
-- AMZ：MONTHLY按年月覆盖同月，跨月保留；eBay：LIVE当前月缓存、FROZEN月末冻结。
CREATE TABLE IF NOT EXISTS dws_home_product_nature_monthly (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  stat_month CHAR(7) NOT NULL COMMENT '统计月份，北京时间',
  platform VARCHAR(8) NOT NULL COMMENT 'amz或ebay',
  period_kind VARCHAR(8) NOT NULL COMMENT 'AMZ为MONTHLY月覆盖；eBay为LIVE实时或FROZEN冻结',
  scope VARCHAR(16) NOT NULL COMMENT 'PLATFORM平台、GROUP组别、OWNER组内负责人',
  group_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '业务组；平台汇总为空串',
  owner_key CHAR(64) NOT NULL DEFAULT '' COMMENT '规范化负责人名称SHA256；无人员ID时的稳定代理键',
  rule_version VARCHAR(64) NOT NULL COMMENT '统计口径版本',
  rule_month CHAR(7) NOT NULL COMMENT '负责人规则月份',
  sku_count BIGINT UNSIGNED NOT NULL COMMENT '本统计级别去重SKU数',
  new_count BIGINT UNSIGNED NOT NULL COMMENT '新品数',
  old_count BIGINT UNSIGNED NOT NULL COMMENT '老品数',
  unknown_count BIGINT UNSIGNED NOT NULL COMMENT '未知数',
  conflict_count BIGINT UNSIGNED NOT NULL COMMENT '冲突数',
  sync_batch_id CHAR(36) NOT NULL COMMENT '同次汇总和明细发布批次',
  source_fingerprint CHAR(64) NOT NULL COMMENT '源数据、规则及日期指纹',
  captured_at DATETIME NOT NULL COMMENT '实际统计时间（北京时间）',
  payload_json JSON NOT NULL COMMENT '指标、归属来源、源状态及对账结果；不含凭证',
  PRIMARY KEY (id),
  UNIQUE KEY uk_scope (stat_month,platform,period_kind,scope,group_code,owner_key),
  KEY idx_history (platform,period_kind,stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='首页商品新老品结构AMZ月覆盖及eBay实时冻结汇总';

CREATE TABLE IF NOT EXISTS dwd_home_product_nature_sku_monthly (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  stat_month CHAR(7) NOT NULL COMMENT '统计月份，北京时间',
  platform VARCHAR(8) NOT NULL COMMENT 'amz或ebay',
  period_kind VARCHAR(8) NOT NULL COMMENT 'AMZ为MONTHLY月覆盖；eBay为LIVE实时或FROZEN冻结',
  fact_key CHAR(64) NOT NULL COMMENT '平台组别负责人店铺站点完整SKU的SHA256',
  group_code VARCHAR(64) NOT NULL COMMENT '业务组，无法识别为UNKNOWN_GROUP',
  owner_key CHAR(64) NOT NULL COMMENT '规范化负责人名称SHA256',
  principal_name VARCHAR(128) NOT NULL COMMENT '当时绩效归属负责人',
  store_id VARCHAR(128) NOT NULL COMMENT 'AMZ的sid或eBay的store_id；缺失为空串',
  site VARCHAR(128) NOT NULL COMMENT '原始站点，缺失为空串',
  sku TEXT NOT NULL COMMENT '完整销售SKU，不截断、不取中间码',
  nature VARCHAR(8) NOT NULL COMMENT '店铺站点粒度NEW、OLD、UNKNOWN、CONFLICT',
  platform_nature VARCHAR(8) NOT NULL COMMENT '负责人加SKU跨店铺组别判定',
  group_nature VARCHAR(8) NOT NULL COMMENT '组别负责人加SKU的判定',
  rule_version VARCHAR(64) NOT NULL COMMENT '统计口径版本',
  sync_batch_id CHAR(36) NOT NULL COMMENT '汇总明细同批发布标识',
  payload_json JSON NOT NULL COMMENT '日期、阈值、匹配键、原始判定等可追溯明细',
  PRIMARY KEY (id),
  UNIQUE KEY uk_fact (stat_month,platform,period_kind,fact_key),
  KEY idx_detail (stat_month,platform,period_kind,group_code,owner_key,group_nature),
  KEY idx_platform_nature (stat_month,platform,period_kind,platform_nature)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='首页商品性质AMZ月覆盖及eBay实时冻结明细';
