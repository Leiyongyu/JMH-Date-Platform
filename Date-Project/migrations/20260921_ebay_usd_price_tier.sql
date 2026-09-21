-- 在Python业务库date-project执行。仅新建美元统计表，不修改旧人民币报表及ODS。
CREATE TABLE IF NOT EXISTS dws_ebay_usd_price_report (
  platform VARCHAR(8) NOT NULL COMMENT '平台，固定ebay',
  report_id CHAR(36) NOT NULL COMMENT '计算批次UUID',
  generated_at DATETIME NOT NULL COMMENT '生成时间，北京时间',
  source_context_json JSON NOT NULL COMMENT '源批次与计算当月rate_org汇率快照；不含凭证',
  summary_json JSON NOT NULL COMMENT '美元统计汇总、口径版本、币种和汇率字段',
  PRIMARY KEY(platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='eBay美元五档价格结构发布状态';
CREATE TABLE IF NOT EXISTS dws_ebay_usd_price_tier (
  platform VARCHAR(8) NOT NULL COMMENT '平台，固定ebay',
  node_id CHAR(64) NOT NULL COMMENT '店铺或站点分组标识SHA256',
  scope VARCHAR(8) NOT NULL COMMENT 'SHOP店铺汇总或SITE站点明细，不能混合加总',
  store_key VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID',
  store_name VARCHAR(255) NOT NULL COMMENT '店铺显示名称',
  site VARCHAR(64) NOT NULL COMMENT '站点，店铺汇总为空',
  tier_no TINYINT UNSIGNED NOT NULL COMMENT '美元五档1至5，界限50/100/150/250，250归第四档',
  sku_count BIGINT UNSIGNED NOT NULL COMMENT '该档有效SKU数；店铺数量为站点之和',
  sku_percent DECIMAL(7,2) NOT NULL COMMENT '占本节点有效SKU总数百分比，保留两位',
  group_sku_count BIGINT UNSIGNED NOT NULL COMMENT '当前节点有效SKU总数',
  node_json JSON NOT NULL COMMENT '原币种、异常及分组元数据',
  report_id CHAR(36) NOT NULL COMMENT '对应已发布报表批次',
  PRIMARY KEY(platform,node_id,tier_no),
  KEY idx_platform_scope(platform,scope)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='eBay美元五档SKU统计；原价USD直用，其他币种按当月rate_org交叉换算';
