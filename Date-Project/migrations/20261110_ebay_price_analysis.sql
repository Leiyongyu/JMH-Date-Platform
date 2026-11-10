-- eBay 价格分析 BI 的派生表。在 Python 应用库（date-project）执行。
-- 只新增 dws_ebay_price_analysis 一张表，不改 ODS、不改订单/库存/汇率任何既有表。
--
-- 幂等：CREATE TABLE IF NOT EXISTS，重复执行不报错也不丢数据。
-- 明细表的数据由刷表任务整表事务替换（不留历史批次，与
-- ods_ebay_store_listing_latest 的发布方式一致），所以本脚本不插入任何业务行。

CREATE TABLE IF NOT EXISTS dws_ebay_price_analysis (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  stat_date DATE NOT NULL COMMENT '快照日期，取 listing 批次 pulled_at 的日期',
  seller_account VARCHAR(128) NOT NULL COMMENT 'eBay 店铺账号',
  site VARCHAR(16) NULL COMMENT 'listing 站点：DE/UK/US/FR',
  site_name VARCHAR(16) NULL COMMENT '站点中文名：德国/英国/美国；未映射站点为 NULL',
  item_id VARCHAR(64) NOT NULL COMMENT 'eBay ItemID',
  sku VARCHAR(255) NULL COMMENT '完整 SKU，已 TRIM；空 SKU 的刊登保留为 NULL',
  brand_code VARCHAR(64) NULL COMMENT 'SKU 第1段，品牌码',
  mid_code VARCHAR(128) NULL COMMENT 'SKU 前2段，品牌-中间码；仅作聚合与下钻维度',
  title TEXT NULL COMMENT '刊登标题',
  image_url TEXT NULL COMMENT '主图地址',
  view_item_url TEXT NULL COMMENT '刊登链接',
  currency VARCHAR(16) NULL COMMENT '售价币种',
  current_price DECIMAL(20,6) NULL COMMENT '原币售价；接口原值非法时为 NULL，不补 0',
  price_usd DECIMAL(20,6) NULL COMMENT '折算美元价；月度汇率缺失时为 NULL，不补 0',
  ebay_quantity BIGINT NULL COMMENT 'eBay 总数量',
  ebay_quantity_available BIGINT NULL COMMENT 'eBay 可售数量',
  ebay_quantity_sold BIGINT NULL COMMENT 'eBay 已售数量',
  watch_count BIGINT NULL COMMENT '关注数',
  overseas_sellable BIGINT NULL COMMENT '谷仓海外仓可售（wid 18699/18700/18701/18702）；未匹配为 NULL',
  overseas_in_transit BIGINT NULL COMMENT '海外在途；未匹配为 NULL',
  chengdu_sellable BIGINT NULL COMMENT '成都中转仓可售（wid 18674/18675/18676）；未匹配为 NULL',
  pending_outbound BIGINT NULL COMMENT '待出库（锁定）；未匹配为 NULL',
  inventory_matched TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否按站点+完整SKU关联到库存快照',
  sales_qty_7d BIGINT NULL COMMENT '快照日前 7 个完整自然日销量',
  sales_qty_30d BIGINT NULL COMMENT '快照日前 30 个完整自然日销量',
  cover_days DECIMAL(10,2) NULL COMMENT '覆盖天数=海外可售÷近7日日均销量；日均为0时 NULL，不写0或极大值',
  stock_gap BIGINT NULL COMMENT '海外可售−eBay可售；未匹配为 NULL，不计入缺口',
  purchase_cost_cny DECIMAL(20,6) NULL COMMENT '订单文件中的真实单件采购成本；缺失为 NULL',
  status VARCHAR(16) NOT NULL COMMENT '未匹配/超卖风险/断货/待补货/滞销/健康，刷表时算一次',
  sync_batch_id VARCHAR(64) NOT NULL COMMENT '刷表批次ID',
  refreshed_at DATETIME NOT NULL COMMENT '刷表完成时间（北京时间）',
  PRIMARY KEY (id),
  UNIQUE KEY uk_price_analysis_listing (seller_account,item_id),
  KEY idx_price_analysis_site_sku (site,sku),
  KEY idx_price_analysis_mid (mid_code),
  KEY idx_price_analysis_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='DWS-eBay在售刊登售价与谷仓库存对比；整表替换，不留历史批次';
