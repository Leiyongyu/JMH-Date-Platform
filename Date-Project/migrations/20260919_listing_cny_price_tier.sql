-- Python数据库date-project。新人民币报表专用，不删除原六档表，不修改ODS或汇率。
CREATE TABLE IF NOT EXISTS dws_listing_cny_price_report (
  platform VARCHAR(8) NOT NULL COMMENT '平台：amz或ebay，每个平台独立保存最新报表',
  report_id CHAR(36) NOT NULL COMMENT '计算批次UUID',
  generated_at DATETIME NOT NULL COMMENT '统计生成时间，北京时间',
  source_context_json JSON NOT NULL COMMENT '原始批次、当月汇率及店铺映射快照，用于检测过期；不含密钥',
  summary_json JSON NOT NULL COMMENT '汇总指标、口径版本及汇率月份',
  PRIMARY KEY(platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='AMZ/eBay人民币价格五档报表发布状态';
CREATE TABLE IF NOT EXISTS dws_listing_cny_price_tier (
  platform VARCHAR(8) NOT NULL COMMENT '平台：amz或ebay',
  node_id CHAR(64) NOT NULL COMMENT '店铺或站点节点标识，分组键SHA256',
  scope VARCHAR(8) NOT NULL COMMENT '统计粒度：SHOP店铺汇总，SITE站点明细；查询加总时不可混用',
  store_key VARCHAR(128) NOT NULL COMMENT '店铺分组标识：eBay稳定账号ID或AMZ店铺名称散列',
  store_name VARCHAR(255) NOT NULL COMMENT '店铺显示名称',
  site VARCHAR(64) NOT NULL COMMENT '站点；店铺汇总为空字符串',
  tier_no TINYINT UNSIGNED NOT NULL COMMENT '人民币五档序号1至5；界限340、680、1020、1690，1690归第四档',
  sku_count BIGINT UNSIGNED NOT NULL COMMENT '该档去重SKU数；店铺合计按站点明细相加',
  sku_percent DECIMAL(7,2) NOT NULL COMMENT '该档占当前节点有效SKU总量的百分数，保留两位小数',
  group_sku_count BIGINT UNSIGNED NOT NULL COMMENT '当前店铺或站点节点有效SKU总量',
  node_json JSON NOT NULL COMMENT '节点元数据：原币种、缺汇率及异常数等，不包含原始凭证',
  report_id CHAR(36) NOT NULL COMMENT '对应平台已发布报表批次',
  PRIMARY KEY(platform,node_id,tier_no),
  KEY idx_platform_scope(platform,scope)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='AMZ/eBay人民币五档SKU统计仓库；原始数据只读，按平台事务覆盖';
