-- 店铺分析与采购中心完整部署脚本
-- 生成日期：2026-09-02
-- 适用数据库：date-project、jmh_data_platform
-- 说明：
-- 1. 本脚本可重复执行，不清空现有店铺分析、补货、采购业务数据。
-- 2. 同时创建/补齐数据表、索引、菜单、按钮权限及 leiyongyu 的角色授权。
-- 3. 执行前仍建议按部署规范备份两个数据库。

SET NAMES utf8mb4;

USE `date-project`;

CREATE TABLE IF NOT EXISTS dim_amz_sop_after_sales_category (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '分类主键',
  big_category VARCHAR(50) NOT NULL COMMENT '售后大类',
  small_category VARCHAR(100) NOT NULL COMMENT '售后小类',
  responsible_party VARCHAR(100) DEFAULT NULL COMMENT '责任方',
  classification_description TEXT DEFAULT NULL COMMENT '分类说明',
  priority INT NOT NULL DEFAULT 100 COMMENT '排序优先级',
  rule_version VARCHAR(32) NOT NULL DEFAULT '2026-08-07' COMMENT '规则版本',
  enabled TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_after_sales_category (big_category,small_category),
  KEY idx_after_sales_category_enabled (enabled,priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='售后原因分类维表（AMZ/eBay共用）';

CREATE TABLE IF NOT EXISTS ebay_sku_analysis_import_batch (
  import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID', source_file_name VARCHAR(255) NOT NULL COMMENT '来源文件名',
  imported_months VARCHAR(255) NOT NULL COMMENT '本次覆盖月份列表', total_rows INT NOT NULL DEFAULT 0 COMMENT 'Excel总行数',
  valid_rows INT NOT NULL DEFAULT 0 COMMENT '有效入库行数', skipped_rows INT NOT NULL DEFAULT 0 COMMENT '跳过行数',
  operator_name VARCHAR(128) DEFAULT NULL COMMENT '上传操作人', status VARCHAR(32) NOT NULL COMMENT '导入状态',
  error_message VARCHAR(1000) DEFAULT NULL COMMENT '失败原因', create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  complete_time DATETIME DEFAULT NULL COMMENT '完成时间', PRIMARY KEY (import_batch_id), KEY idx_esa_batch_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay SKU分析文件导入批次';
CREATE TABLE IF NOT EXISTS ods_ebay_sku_analysis_order_raw (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID',
  stat_month CHAR(7) NOT NULL COMMENT '统计月份，格式YYYY-MM',
  source_file_name VARCHAR(255) NOT NULL COMMENT '来源文件名',
  source_sheet VARCHAR(128) NOT NULL COMMENT '来源工作表',
  source_row INT NOT NULL COMMENT '来源Excel行号',
  source_site_name VARCHAR(100) DEFAULT NULL COMMENT 'Excel第一列原始站点',
  platform_order_no VARCHAR(128) NOT NULL COMMENT '平台订单号',
  shipping_status VARCHAR(64) DEFAULT NULL COMMENT '发货状态',
  order_time DATETIME DEFAULT NULL COMMENT '下单时间',
  payment_time DATETIME NOT NULL COMMENT '付款时间',
  refund_time DATETIME DEFAULT NULL COMMENT '退款时间',
  currency_code VARCHAR(16) DEFAULT NULL COMMENT '币种',
  goods_receivable_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收货款（订单级别，原币）',
  goods_receivable_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收货款（订单级别，人民币）',
  shipping_receivable_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费（原币）',
  shipping_receivable_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费（人民币）',
  tax_usd DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '税费（美元）',
  tax_usd_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '税费（美元字段换算人民币）',
  platform_fee_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台费用（原币）',
  platform_product_unit_price DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台产品单价',
  platform_product_unit_price_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台产品单价（人民币）',
  product_unit_price DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '产品单价',
  product_unit_price_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '产品单价（人民币）',
  source_refund_amount DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT 'Excel退款金额原始值',
  source_refund_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额（人民币）',
  tax_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '税费（人民币）',
  advertising_fee_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '广告费（人民币）',
  last_mile_shipping_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '实际尾程运费（人民币）',
  platform_fee_detail TEXT DEFAULT NULL COMMENT '平台费用明细',
  first_mile_shipping_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '头程运费（人民币）',
  purchase_cost_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '采购成本（人民币）',
  exchange_rate DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '汇率',
  customer_id VARCHAR(255) DEFAULT NULL COMMENT '客户ID',
  picture_url TEXT DEFAULT NULL COMMENT '图片链接',
  product_name_cn VARCHAR(500) DEFAULT NULL COMMENT '产品名称（中文）',
  platform_sku VARCHAR(128) DEFAULT NULL COMMENT '平台SKU',
  inventory_sku VARCHAR(128) NOT NULL COMMENT '库存SKU',
  sku_status VARCHAR(64) DEFAULT NULL COMMENT 'SKU状态',
  listing_url TEXT DEFAULT NULL COMMENT 'Listing链接',
  available_inventory DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '可用库存',
  order_profit_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '订单利润（人民币）',
  order_total_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '订单总金额（原币）',
  purchase_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '购买数量',
  platform_sku_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '平台SKU数量',
  order_remark TEXT DEFAULT NULL COMMENT '订单备注',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_esa_raw_month (stat_month), KEY idx_esa_raw_sku (inventory_sku), KEY idx_esa_raw_order_date (platform_order_no,payment_time), KEY idx_esa_raw_batch (import_batch_id), KEY idx_esa_raw_batch_row (import_batch_id,source_row)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ODS-eBay SKU分析订单上传结构化源数据';
CREATE TABLE IF NOT EXISTS dwd_ebay_sku_analysis_order (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', stat_month CHAR(7) NOT NULL COMMENT '统计月份，格式YYYY-MM', payment_time DATETIME NOT NULL COMMENT '付款时间', refund_time DATETIME DEFAULT NULL COMMENT '退款时间',
  platform_order_no VARCHAR(128) NOT NULL COMMENT '平台订单号', inventory_sku VARCHAR(128) NOT NULL COMMENT '标准库存SKU', purchase_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '购买数量',
  paid_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额人民币', shipping_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '运费人民币',
  platform_fee_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台费用人民币', order_profit_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '订单利润（人民币，来自订单上传文件）', paid_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收货款加应收运费原币（按订单SKU分摊）', shipping_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币', refund_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '退货数量，状态包含已退款或已作废', refund_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币（按退款行分摊）', refund_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额人民币', shipping_status VARCHAR(64) DEFAULT NULL COMMENT '发货状态', currency_code VARCHAR(16) DEFAULT NULL COMMENT '币种', customer_id VARCHAR(255) DEFAULT NULL COMMENT '客户ID', site_code VARCHAR(32) NOT NULL COMMENT '标准站点代码', site_name VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称',
  country_name VARCHAR(128) DEFAULT NULL COMMENT '国家名称',
  picture_url TEXT DEFAULT NULL COMMENT '图片链接，取上传源数据',
  product_name_cn VARCHAR(500) DEFAULT NULL COMMENT '产品名称（中文），取上传源数据',
  listing_url TEXT DEFAULT NULL COMMENT 'Listing链接，取上传源数据',
  order_remark TEXT DEFAULT NULL COMMENT '原始订单备注，作为退款原因展示',
  import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID',
  source_row INT NOT NULL COMMENT '来源Excel行号', create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间', PRIMARY KEY (id),
  UNIQUE KEY uk_esa_dwd_month_row (stat_month, import_batch_id, source_row), KEY idx_esa_dwd_order_date (platform_order_no,payment_time), KEY idx_esa_dwd_time (payment_time), KEY idx_esa_dwd_sku (inventory_sku), KEY idx_esa_dwd_site (site_code), KEY idx_esa_dwd_site_sku_time (site_name,inventory_sku,payment_time), KEY idx_esa_dwd_return_time (refund_time,site_name,inventory_sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DWD-eBay SKU分析订单清洗明细';

CREATE TABLE IF NOT EXISTS ebay_sku_analysis_return_classification (
  platform_order_no VARCHAR(128) NOT NULL COMMENT 'eBay平台订单号，分类持久化唯一键',
  category_id BIGINT UNSIGNED NOT NULL COMMENT '售后分类维表ID',
  responsible_party VARCHAR(100) DEFAULT NULL COMMENT '负责方快照',
  big_category VARCHAR(50) NOT NULL COMMENT '售后大类快照',
  small_category VARCHAR(100) NOT NULL COMMENT '售后小类快照',
  classification_description TEXT DEFAULT NULL COMMENT '分类说明快照',
  classified_by VARCHAR(128) DEFAULT NULL COMMENT '最后分类操作人',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次分类时间',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后修改时间',
  PRIMARY KEY (platform_order_no),
  KEY idx_esa_return_category (category_id,big_category,small_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay退货订单人工售后分类映射';

-- SKU分析利润已改为直接使用订单文件中的“订单利润(￥)”，清理旧独立利润上传链路表。

-- 对已存在的旧版表仅补齐缺失字段和索引，不覆盖或删除业务数据。
DROP PROCEDURE IF EXISTS deploy_add_column_if_missing;
DELIMITER $$
CREATE PROCEDURE deploy_add_column_if_missing(
  IN p_schema_name VARCHAR(64),
  IN p_table_name VARCHAR(64),
  IN p_column_name VARCHAR(64),
  IN p_definition TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=p_schema_name
      AND TABLE_NAME=p_table_name
      AND COLUMN_NAME=p_column_name
  ) THEN
    SET @deploy_ddl = CONCAT(
      'ALTER TABLE `', REPLACE(p_schema_name,'`','``'),
      '`.`', REPLACE(p_table_name,'`','``'),
      '` ADD COLUMN `', REPLACE(p_column_name,'`','``'),
      '` ', p_definition
    );
    PREPARE deploy_stmt FROM @deploy_ddl;
    EXECUTE deploy_stmt;
    DEALLOCATE PREPARE deploy_stmt;
  END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS deploy_add_index_if_missing;
DELIMITER $$
CREATE PROCEDURE deploy_add_index_if_missing(
  IN p_schema_name VARCHAR(64),
  IN p_table_name VARCHAR(64),
  IN p_index_name VARCHAR(64),
  IN p_columns TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=p_schema_name
      AND TABLE_NAME=p_table_name
      AND INDEX_NAME=p_index_name
  ) THEN
    SET @deploy_ddl = CONCAT(
      'ALTER TABLE `', REPLACE(p_schema_name,'`','``'),
      '`.`', REPLACE(p_table_name,'`','``'),
      '` ADD INDEX `', REPLACE(p_index_name,'`','``'),
      '` (', p_columns, ')'
    );
    PREPARE deploy_stmt FROM @deploy_ddl;
    EXECUTE deploy_stmt;
    DEALLOCATE PREPARE deploy_stmt;
  END IF;
END$$
DELIMITER ;

CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','source_site_name',
  'VARCHAR(100) NULL COMMENT ''Excel第一列原始站点'' AFTER source_row');
CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','goods_receivable_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''应收货款人民币'' AFTER goods_receivable_original');
CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','shipping_receivable_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''应收运费人民币'' AFTER shipping_receivable_original');
CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','tax_usd_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''税费美元字段换算人民币'' AFTER tax_usd');
CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','platform_product_unit_price_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''平台产品单价人民币'' AFTER platform_product_unit_price');
CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','product_unit_price_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''产品单价人民币'' AFTER product_unit_price');
CALL deploy_add_column_if_missing('date-project','ods_ebay_sku_analysis_order_raw','source_refund_amount_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''退款金额人民币'' AFTER source_refund_amount');

CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','refund_time',
  'DATETIME NULL COMMENT ''退款时间'' AFTER payment_time');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','order_profit_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''订单利润人民币'' AFTER platform_fee_cny');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','paid_amount_original',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''应收货款加应收运费原币'' AFTER order_profit_cny');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','shipping_amount_original',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''应收运费原币'' AFTER paid_amount_original');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','refund_quantity',
  'DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT ''退货数量'' AFTER shipping_amount_original');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','refund_amount_original',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''退款金额原币'' AFTER refund_quantity');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','refund_amount_cny',
  'DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''退款金额人民币'' AFTER refund_amount_original');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','shipping_status',
  'VARCHAR(64) NULL COMMENT ''发货状态'' AFTER refund_amount_cny');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','currency_code',
  'VARCHAR(16) NULL COMMENT ''币种'' AFTER shipping_status');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','site_name',
  'VARCHAR(100) NOT NULL DEFAULT ''其他'' COMMENT ''中文站点名称'' AFTER site_code');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','country_name',
  'VARCHAR(128) NULL COMMENT ''国家名称'' AFTER site_name');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','picture_url',
  'TEXT NULL COMMENT ''图片链接'' AFTER country_name');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','product_name_cn',
  'VARCHAR(500) NULL COMMENT ''产品中文名称'' AFTER picture_url');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','listing_url',
  'TEXT NULL COMMENT ''Listing链接'' AFTER product_name_cn');
CALL deploy_add_column_if_missing('date-project','dwd_ebay_sku_analysis_order','order_remark',
  'TEXT NULL COMMENT ''原始订单备注'' AFTER listing_url');

CALL deploy_add_index_if_missing('date-project','ods_ebay_sku_analysis_order_raw','idx_esa_raw_batch_row',
  '`import_batch_id`,`source_row`');
CALL deploy_add_index_if_missing('date-project','dwd_ebay_sku_analysis_order','idx_esa_dwd_site_sku_time',
  '`site_name`,`inventory_sku`,`payment_time`');
CALL deploy_add_index_if_missing('date-project','dwd_ebay_sku_analysis_order','idx_esa_dwd_return_time',
  '`refund_time`,`site_name`,`inventory_sku`');

DROP PROCEDURE IF EXISTS deploy_add_index_if_missing;
DROP PROCEDURE IF EXISTS deploy_add_column_if_missing;

USE `jmh_data_platform`;

CREATE TABLE IF NOT EXISTS sys_user_column_config (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  user_name VARCHAR(64) DEFAULT NULL COMMENT '用户名快照',
  page_key VARCHAR(100) NOT NULL COMMENT '页面配置键',
  config_json TEXT NOT NULL COMMENT '列显示、排序配置JSON',
  create_by VARCHAR(64) NOT NULL DEFAULT '',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_by VARCHAR(64) NOT NULL DEFAULT '',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_page_key (user_id,page_key),
  KEY idx_column_config_page_key (page_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户页面列显示和排列配置';

-- 在 jmh_data_platform 执行：运营中心 / eBay / 店铺分析三级菜单。
-- 可重复执行；保留原 SKU 分析菜单 ID 和功能权限，仅调整其父菜单。

SET @operations_id := (SELECT menu_id FROM sys_menu WHERE menu_type='M' AND (path='operations' OR menu_name='运营中心') ORDER BY menu_id LIMIT 1);
SET @ebay_dir_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(menu_name)='ebay' ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'eBay',@operations_id,2,'ebay',NULL,'',1,0,'M','0','0','','shopping','SYSTEM',NOW(),'运营中心eBay业务目录'
WHERE @operations_id IS NOT NULL AND @ebay_dir_id IS NULL;

SET @ebay_dir_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(menu_name)='ebay' ORDER BY menu_id LIMIT 1);
SET @store_analysis_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND (path='store-analysis' OR menu_name='店铺分析') ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '店铺分析',@ebay_dir_id,20,'store-analysis',NULL,'',1,0,'M','0','0','','shop','SYSTEM',NOW(),'eBay店铺分析业务目录'
WHERE @ebay_dir_id IS NOT NULL AND @store_analysis_id IS NULL;

SET @store_analysis_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND (path='store-analysis' OR menu_name='店铺分析') ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@ebay_dir_id,menu_name='店铺分析',order_num=20,path='store-analysis',component=NULL,route_name='',menu_type='M',visible='0',status='0',perms='',icon='shop',update_by='SYSTEM',update_time=NOW(),remark='eBay店铺分析业务目录' WHERE menu_id=@store_analysis_id;

SET @sku_menu_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'SKU分析',@store_analysis_id,1,'sku-analysis','operations/ebay/skuAnalysis/index','EbaySkuAnalysis',1,0,'C','0','0','operations:ebaySkuAnalysis:list','chart','SYSTEM',NOW(),'上传数字酋长订单并按SKU分析'
WHERE @store_analysis_id IS NOT NULL AND @sku_menu_id IS NULL;
SET @sku_menu_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@store_analysis_id,menu_name='SKU分析',order_num=1,path='sku-analysis',component='operations/ebay/skuAnalysis/index',route_name='EbaySkuAnalysis',menu_type='C',visible='0',status='0',perms='operations:ebaySkuAnalysis:list',icon='chart',update_by='SYSTEM',update_time=NOW(),remark='上传数字酋长订单并按SKU分析' WHERE menu_id=@sku_menu_id;

SET @return_overview_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnOverview:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '退货概览',@store_analysis_id,2,'return-overview','operations/ebay/returnOverview/index','EbayReturnOverview',1,0,'C','0','0','operations:ebayReturnOverview:list','chart','SYSTEM',NOW(),'eBay退货概览演示页面'
WHERE @store_analysis_id IS NOT NULL AND @return_overview_id IS NULL;
SET @return_overview_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnOverview:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@store_analysis_id,menu_name='退货概览',order_num=2,path='return-overview',component='operations/ebay/returnOverview/index',route_name='EbayReturnOverview',menu_type='C',visible='0',status='0',icon='chart',update_by='SYSTEM',update_time=NOW(),remark='eBay退货概览演示页面' WHERE menu_id=@return_overview_id;

SET @return_detail_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnDetail:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '退货明细',@store_analysis_id,3,'return-detail','operations/ebay/returnDetail/index','EbayReturnDetail',1,0,'C','0','0','operations:ebayReturnDetail:list','list','SYSTEM',NOW(),'eBay退货明细演示页面'
WHERE @store_analysis_id IS NOT NULL AND @return_detail_id IS NULL;
SET @return_detail_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnDetail:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@store_analysis_id,menu_name='退货明细',order_num=3,path='return-detail',component='operations/ebay/returnDetail/index',route_name='EbayReturnDetail',menu_type='C',visible='0',status='0',icon='list',update_by='SYSTEM',update_time=NOW(),remark='eBay退货明细演示页面' WHERE menu_id=@return_detail_id;

SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay补货2.0',@store_analysis_id,4,'replenishment-v2',
       'operations/ebay/replenishmentV2/index',NULL,'EbayReplenishmentV2',
       1,0,'C','0','0','operations:ebayReplenishmentV2:list','shopping',
       'SYSTEM',NOW(),'eBay补货2.0近三个月销量、毛利与退货分析'
WHERE @store_analysis_id IS NOT NULL AND @ebay_replenishment_v2_id IS NULL;
SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@store_analysis_id,menu_name='eBay补货2.0',order_num=4,
    path='replenishment-v2',component='operations/ebay/replenishmentV2/index',
    query=NULL,route_name='EbayReplenishmentV2',is_frame=1,is_cache=0,
    menu_type='C',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:list',icon='shopping',
    update_by='SYSTEM',update_time=NOW(),
    remark='eBay补货2.0近三个月销量、毛利与退货分析'
WHERE menu_id=@ebay_replenishment_v2_id AND @store_analysis_id IS NOT NULL;

SET @import_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:import' ORDER BY menu_id LIMIT 1);

DELETE role_menu
FROM sys_role_menu role_menu
INNER JOIN sys_menu menu ON menu.menu_id=role_menu.menu_id
WHERE menu.perms='operations:ebaySkuAnalysis:profitImport';
DELETE FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:profitImport';
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '上传eBay订单',@sku_menu_id,1,'',NULL,'',1,0,'F','0','0','operations:ebaySkuAnalysis:import','#','SYSTEM',NOW(),'上传数字酋长订单Excel'
WHERE @sku_menu_id IS NOT NULL AND @import_id IS NULL;
SET @import_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:import' ORDER BY menu_id LIMIT 1);

-- 仅为原本拥有 SKU 分析页面权限的角色补齐新的父目录，避免菜单移动后不可见。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT role_id,@store_analysis_id FROM sys_role_menu
WHERE menu_id=@sku_menu_id AND @store_analysis_id IS NOT NULL;

-- leiyongyu 当前拥有的全部角色获得店铺分析整棵菜单权限。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @operations_id,@ebay_dir_id,@store_analysis_id,@sku_menu_id,@import_id,
  @return_overview_id,@return_detail_id,@ebay_replenishment_v2_id
)
WHERE u.user_name='leiyongyu' AND m.menu_id IS NOT NULL;

SELECT menu_id,parent_id,menu_name,order_num,menu_type,perms,component
FROM sys_menu
WHERE menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@sku_menu_id,@import_id,@return_overview_id,@return_detail_id,@ebay_replenishment_v2_id)
ORDER BY parent_id,order_num,menu_id;

-- 目标库：jmh_data_platform（Java ERP 数据库）。
-- 新增“运营中心 / eBay / 店铺分析 / eBay补货2.0”菜单。
-- 创建人工时效表、按“站点+完整SKU”汇总的仓租表，并给 leiyongyu 的有效角色补齐完整祖先链和功能权限。
USE jmh_data_platform;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_lead_time (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '人工时效配置主键',
  site VARCHAR(100) NOT NULL COMMENT '站点',
  sku VARCHAR(255) NOT NULL COMMENT '完整库存SKU',
  chengdu_warehouse_to_warehouse_days INT UNSIGNED NULL COMMENT '成都仓到仓时间，单位：天',
  chengdu_qc_outbound_days INT UNSIGNED NULL COMMENT '成都质检出仓时间，单位：天',
  overseas_transit_to_listing_days INT UNSIGNED NULL COMMENT '海外在途到上架时间，单位：天',
  create_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '创建人',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '更新人',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_replenishment_v2_lead_time_site_sku (site,sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0站点SKU人工时效配置表';

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_warehouse_rent (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '仓租汇总记录主键',
  site VARCHAR(100) NOT NULL COMMENT '由仓库代码映射得到的站点',
  sku VARCHAR(255) NOT NULL COMMENT '去除JMH-前缀后的完整库存SKU',
  warehouse_codes VARCHAR(255) NOT NULL DEFAULT '' COMMENT '参与汇总的仓库代码，多个代码以英文逗号分隔',
  source_row_count INT UNSIGNED NOT NULL COMMENT '该站点SKU对应的源文件明细行数',
  warehouse_rent_amount_cny DECIMAL(18,4) NOT NULL COMMENT '按固定汇率换算并汇总的总金额人民币值，不含税且包含附加费',
  import_batch_id CHAR(32) NOT NULL COMMENT '本次整表导入批次编号',
  source_file_name VARCHAR(255) NOT NULL COMMENT '本次导入的Excel源文件名',
  imported_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '导入操作人',
  import_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导入时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_replenishment_v2_warehouse_rent_site_sku (site,sku),
  KEY idx_ebay_replenishment_v2_warehouse_rent_batch (import_batch_id),
  KEY idx_ebay_replenishment_v2_warehouse_rent_time (import_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0站点SKU仓租明细总费用人民币聚合表';

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_warehouse_rent_import_lock (
  id TINYINT UNSIGNED NOT NULL COMMENT '固定控制行ID',
  lock_key VARCHAR(64) NOT NULL COMMENT '仓租增量导入锁标识',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '最后锁定时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_replenishment_v2_rent_lock_key (lock_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0仓租按单号增量覆盖并发控制表';

INSERT INTO ebay_replenishment_v2_warehouse_rent_import_lock(id,lock_key)
VALUES (1,'warehouse_rent_import')
ON DUPLICATE KEY UPDATE lock_key=VALUES(lock_key);

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_warehouse_rent_detail (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '仓租源明细主键',
  order_no VARCHAR(128) NOT NULL COMMENT '仓租单号，作为增量覆盖键',
  warehouse_code VARCHAR(64) NOT NULL COMMENT '仓库代码',
  product_code VARCHAR(255) NOT NULL COMMENT '商品编码',
  goods_barcode VARCHAR(255) NULL COMMENT '商品条码',
  product_name VARCHAR(500) NULL COMMENT '商品名称',
  reference_no VARCHAR(255) NULL COMMENT '参考号',
  billing_time_text VARCHAR(100) NULL COMMENT '计费时间原始文本',
  listing_time_text VARCHAR(100) NULL COMMENT '上架时间原始文本',
  dimensions_text VARCHAR(255) NULL COMMENT '尺寸原始文本',
  quantity_text VARCHAR(100) NULL COMMENT '数量原始文本',
  volume_m3_text VARCHAR(100) NULL COMMENT '体积原始文本',
  product_weight_kg_text VARCHAR(100) NULL COMMENT '重量原始文本',
  warehouse_rent_excl_tax_text VARCHAR(100) NULL COMMENT '仓租不含税原始文本',
  billing_currency VARCHAR(32) NULL COMMENT '计费币种',
  inventory_age_days_text VARCHAR(100) NULL COMMENT '库龄天数原始文本',
  goods_type VARCHAR(100) NULL COMMENT '货物类型',
  billing_type VARCHAR(100) NULL COMMENT '计费类型',
  storage_physical_form VARCHAR(100) NULL COMMENT '存储物理形态',
  peak_season_surcharge_excl_tax_text VARCHAR(100) NULL COMMENT '旺季附加费不含税原始文本',
  over_age_surcharge_excl_tax_text VARCHAR(100) NULL COMMENT '超龄附加费不含税原始文本',
  oversized_surcharge_excl_tax_text VARCHAR(100) NULL COMMENT '超尺寸附加费不含税原始文本',
  total_amount_excl_tax_text VARCHAR(100) NULL COMMENT '总金额不含税原始文本',
  site VARCHAR(100) NOT NULL COMMENT '仓库代码映射后的站点',
  sku VARCHAR(255) NOT NULL COMMENT '去除JMH-前缀后的完整库存SKU',
  exchange_rate DECIMAL(18,6) NOT NULL COMMENT '导入时使用的人民币汇率',
  warehouse_rent_amount_cny DECIMAL(18,4) NOT NULL COMMENT '该明细人民币仓租费用',
  import_batch_id CHAR(32) NOT NULL COMMENT '导入批次编号',
  source_file_name VARCHAR(255) NOT NULL COMMENT 'Excel源文件名',
  source_sheet_name VARCHAR(128) NOT NULL COMMENT '固定仓租明细Sheet名',
  source_row_num INT UNSIGNED NOT NULL COMMENT 'Excel源行号',
  imported_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '导入操作人',
  import_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导入时间',
  PRIMARY KEY (id),
  KEY idx_ebay_replenishment_v2_rent_detail_order (order_no),
  KEY idx_ebay_replenishment_v2_rent_detail_site_sku (site,sku),
  KEY idx_ebay_replenishment_v2_rent_detail_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0仓租明细Sheet结构化源数据，按单号增量覆盖';

SET @operations_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M'
    AND (path='operations' OR menu_name='运营中心')
  ORDER BY CASE WHEN path='operations' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay',@operations_id,2,'ebay',NULL,NULL,'',
       1,0,'M','0','0','','shopping','SYSTEM',NOW(),'运营中心eBay业务目录'
WHERE @operations_id IS NOT NULL AND @ebay_dir_id IS NULL;
SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '店铺分析',@ebay_dir_id,20,'store-analysis',NULL,NULL,'',
       1,0,'M','0','0','','shop','SYSTEM',NOW(),'eBay店铺分析业务目录'
WHERE @ebay_dir_id IS NOT NULL AND @store_analysis_id IS NULL;
SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_dir_id,menu_name='店铺分析',order_num=20,
    path='store-analysis',component=NULL,query=NULL,route_name='',
    is_frame=1,is_cache=0,menu_type='M',visible='0',status='0',
    perms='',icon='shop',update_by='SYSTEM',update_time=NOW(),
    remark='eBay店铺分析业务目录'
WHERE menu_id=@store_analysis_id;

SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay补货2.0',@store_analysis_id,4,'replenishment-v2',
       'operations/ebay/replenishmentV2/index',NULL,'EbayReplenishmentV2',
       1,0,'C','0','0','operations:ebayReplenishmentV2:list','shopping',
       'SYSTEM',NOW(),'eBay补货2.0近三个月销量、毛利与退货分析'
WHERE @store_analysis_id IS NOT NULL AND @ebay_replenishment_v2_id IS NULL;
SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@store_analysis_id,menu_name='eBay补货2.0',order_num=4,
    path='replenishment-v2',component='operations/ebay/replenishmentV2/index',
    query=NULL,route_name='EbayReplenishmentV2',is_frame=1,is_cache=0,
    menu_type='C',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:list',icon='shopping',
    update_by='SYSTEM',update_time=NOW(),
    remark='eBay补货2.0近三个月销量、毛利与退货分析'
WHERE menu_id=@ebay_replenishment_v2_id AND @store_analysis_id IS NOT NULL;

SET @lead_time_edit_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:editLeadTime'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='维护补货时效')
  )
  ORDER BY CASE WHEN perms='operations:ebayReplenishmentV2:editLeadTime' THEN 0 ELSE 1 END,
           menu_id
  LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '维护补货时效',@ebay_replenishment_v2_id,1,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:editLeadTime','',
       'SYSTEM',NOW(),'按站点和完整SKU维护三个补货时效天数'
WHERE @ebay_replenishment_v2_id IS NOT NULL AND @lead_time_edit_id IS NULL;
SET @lead_time_edit_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:editLeadTime'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='维护补货时效')
  )
  ORDER BY CASE WHEN perms='operations:ebayReplenishmentV2:editLeadTime' THEN 0 ELSE 1 END,
           menu_id
  LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_replenishment_v2_id,menu_name='维护补货时效',order_num=1,
    path='',component=NULL,query=NULL,route_name='',is_frame=1,is_cache=0,
    menu_type='F',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:editLeadTime',icon='',
    update_by='SYSTEM',update_time=NOW(),
    remark='按站点和完整SKU维护三个补货时效天数'
WHERE menu_id=@lead_time_edit_id AND @ebay_replenishment_v2_id IS NOT NULL;

SET @warehouse_rent_import_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:importWarehouseRent'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='上传仓租明细')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:importWarehouseRent' THEN 0 ELSE 1
  END,menu_id
  LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '上传仓租明细',@ebay_replenishment_v2_id,2,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:importWarehouseRent','',
       'SYSTEM',NOW(),'上传仓租明细Excel，按单号增量覆盖明细并重建站点SKU汇总'
WHERE @ebay_replenishment_v2_id IS NOT NULL
  AND @warehouse_rent_import_id IS NULL;
SET @warehouse_rent_import_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:importWarehouseRent'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='上传仓租明细')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:importWarehouseRent' THEN 0 ELSE 1
  END,menu_id
  LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_replenishment_v2_id,menu_name='上传仓租明细',order_num=2,
    path='',component=NULL,query=NULL,route_name='',is_frame=1,is_cache=0,
    menu_type='F',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:importWarehouseRent',icon='',
    update_by='SYSTEM',update_time=NOW(),
    remark='上传仓租明细Excel，按单号增量覆盖明细并重建站点SKU汇总'
WHERE menu_id=@warehouse_rent_import_id
  AND @ebay_replenishment_v2_id IS NOT NULL;

-- 非管理员动态路由从根节点递归构建，四级菜单必须全部授权。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,target.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN (
  SELECT @operations_id AS menu_id
  UNION ALL SELECT @ebay_dir_id
  UNION ALL SELECT @store_analysis_id
  UNION ALL SELECT @ebay_replenishment_v2_id
  UNION ALL SELECT @lead_time_edit_id
  UNION ALL SELECT @warehouse_rent_import_id
) target ON target.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,route_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@ebay_replenishment_v2_id,@lead_time_edit_id,@warehouse_rent_import_id)
ORDER BY parent_id,order_num,menu_id;

SELECT u.user_name,r.role_id,r.role_name,m.menu_id,m.parent_id,m.menu_name,m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu'
  AND m.menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@ebay_replenishment_v2_id,@lead_time_edit_id,@warehouse_rent_import_id)
ORDER BY r.role_id,m.parent_id,m.order_num,m.menu_id;

-- 目标库：jmh_data_platform（Java ERP 数据库）。
-- 新增顶级“采购中心 / 待采购”菜单、待采购业务表及接口权限。
-- 可重复执行；采购中心与运营中心同级，给admin和leiyongyu的有效角色补齐权限。
USE jmh_data_platform;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS procurement_pending_purchase (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '待采购记录主键',
  site VARCHAR(100) NOT NULL COMMENT '站点',
  sku VARCHAR(255) NOT NULL COMMENT '库存SKU',
  purchase_quantity INT UNSIGNED NOT NULL COMMENT '最终采购量',
  purchase_time DATETIME NOT NULL COMMENT '采购确认时间',
  status CHAR(1) NOT NULL DEFAULT '0' COMMENT '采购状态：0待采购，1已采购',
  pending_flag TINYINT NULL DEFAULT 1 COMMENT '待采购唯一标记：待采购为1，已采购为空',
  export_time DATETIME NULL COMMENT '导出并转为已采购的时间',
  create_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '创建人',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '更新人',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_pending_site_sku (site, sku, pending_flag),
  KEY idx_status_purchase_time (status, purchase_time),
  KEY idx_site_sku (site, sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采购中心待采购清单';

-- 采购中心必须与运营中心同级；若部署库尚无运营中心，则回退为顶级目录。
SET @procurement_peer_parent_id := COALESCE((
  SELECT parent_id FROM sys_menu
  WHERE menu_type='M' AND (path='operations' OR menu_name='运营中心')
  ORDER BY CASE WHEN path='operations' THEN 0 ELSE 1 END,menu_id LIMIT 1
),0);

SET @procurement_center_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='M'
    AND (path='procurement'
         OR (parent_id=@procurement_peer_parent_id AND menu_name='采购中心'))
  ORDER BY CASE WHEN path='procurement' THEN 0 ELSE 1 END,
           CASE WHEN parent_id=@procurement_peer_parent_id THEN 0 ELSE 1 END,
           menu_id LIMIT 1
);
SET @procurement_order := (
  SELECT COALESCE(MAX(order_num),0) + 1 FROM sys_menu
  WHERE parent_id=@procurement_peer_parent_id
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '采购中心',@procurement_peer_parent_id,@procurement_order,'procurement',NULL,NULL,'',
       1,0,'M','0','0','','shopping','SYSTEM',NOW(),'采购业务顶级目录'
WHERE @procurement_center_id IS NULL;
SET @procurement_center_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='M'
    AND (path='procurement'
         OR (parent_id=@procurement_peer_parent_id AND menu_name='采购中心'))
  ORDER BY CASE WHEN path='procurement' THEN 0 ELSE 1 END,
           CASE WHEN parent_id=@procurement_peer_parent_id THEN 0 ELSE 1 END,
           menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@procurement_peer_parent_id,menu_name='采购中心',path='procurement',component=NULL,query=NULL,
    route_name='',is_frame=1,is_cache=0,menu_type='M',visible='0',status='0',
    perms='',icon='shopping',update_by='SYSTEM',update_time=NOW(),remark='采购业务顶级目录'
WHERE menu_id=@procurement_center_id;

SET @pending_purchase_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C'
    AND (component='procurement/pending/index'
         OR perms='procurement:pendingPurchase:list'
         OR (parent_id=@procurement_center_id AND (path='pending-purchase' OR menu_name='待采购')))
  ORDER BY CASE
    WHEN path='pending-purchase' THEN 0
    WHEN component='procurement/pending/index' THEN 1
    WHEN perms='procurement:pendingPurchase:list' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '待采购',@procurement_center_id,1,'pending-purchase','procurement/pending/index',NULL,
       'PendingPurchase',1,0,'C','0','0','procurement:pendingPurchase:list','list',
       'SYSTEM',NOW(),'待采购记录查询及导出'
WHERE @procurement_center_id IS NOT NULL AND @pending_purchase_id IS NULL;
SET @pending_purchase_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C'
    AND (component='procurement/pending/index'
         OR perms='procurement:pendingPurchase:list'
         OR (parent_id=@procurement_center_id AND (path='pending-purchase' OR menu_name='待采购')))
  ORDER BY CASE
    WHEN path='pending-purchase' THEN 0
    WHEN component='procurement/pending/index' THEN 1
    WHEN perms='procurement:pendingPurchase:list' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@procurement_center_id,menu_name='待采购',order_num=1,path='pending-purchase',
    component='procurement/pending/index',query=NULL,route_name='PendingPurchase',
    is_frame=1,is_cache=0,menu_type='C',visible='0',status='0',
    perms='procurement:pendingPurchase:list',icon='list',update_by='SYSTEM',update_time=NOW(),
    remark='待采购记录查询及导出'
WHERE menu_id=@pending_purchase_id AND @procurement_center_id IS NOT NULL;

SET @pending_add_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:add'
  ORDER BY menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '采购确认',@pending_purchase_id,1,'',NULL,NULL,'',
       1,0,'F','0','0','procurement:pendingPurchase:add','#',
       'SYSTEM',NOW(),'从补货页面确认最终采购量'
WHERE @pending_purchase_id IS NOT NULL AND @pending_add_id IS NULL;
SET @pending_add_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:add'
  ORDER BY menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@pending_purchase_id,menu_name='采购确认',order_num=1,path='',component=NULL,
    query=NULL,route_name='',is_frame=1,is_cache=0,menu_type='F',visible='0',status='0',
    perms='procurement:pendingPurchase:add',icon='#',update_by='SYSTEM',update_time=NOW(),
    remark='从补货页面确认最终采购量'
WHERE menu_id=@pending_add_id AND @pending_purchase_id IS NOT NULL;

SET @pending_export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:export'
  ORDER BY menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导出待采购',@pending_purchase_id,2,'',NULL,NULL,'',
       1,0,'F','0','0','procurement:pendingPurchase:export','#',
       'SYSTEM',NOW(),'导出选中记录并转为已采购'
WHERE @pending_purchase_id IS NOT NULL AND @pending_export_id IS NULL;
SET @pending_export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:export'
  ORDER BY menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@pending_purchase_id,menu_name='导出待采购',order_num=2,path='',component=NULL,
    query=NULL,route_name='',is_frame=1,is_cache=0,menu_type='F',visible='0',status='0',
    perms='procurement:pendingPurchase:export',icon='#',update_by='SYSTEM',update_time=NOW(),
    remark='导出选中记录并转为已采购'
WHERE menu_id=@pending_export_id AND @pending_purchase_id IS NOT NULL;

-- 显式给有效admin角色授权。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,target.menu_id
FROM sys_role r
JOIN (
  SELECT @procurement_center_id AS menu_id
  UNION ALL SELECT @pending_purchase_id
  UNION ALL SELECT @pending_add_id
  UNION ALL SELECT @pending_export_id
) target ON target.menu_id IS NOT NULL
WHERE r.role_key='admin' AND r.status='0' AND r.del_flag='0';

-- leiyongyu当前拥有的全部有效角色获得采购中心完整权限。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,target.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN (
  SELECT @procurement_center_id AS menu_id
  UNION ALL SELECT @pending_purchase_id
  UNION ALL SELECT @pending_add_id
  UNION ALL SELECT @pending_export_id
) target ON target.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,route_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@procurement_center_id,@pending_purchase_id,@pending_add_id,@pending_export_id)
ORDER BY parent_id,order_num,menu_id;

SELECT u.user_name,r.role_id,r.role_name,m.menu_id,m.parent_id,m.menu_name,m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu'
  AND m.menu_id IN (@procurement_center_id,@pending_purchase_id,@pending_add_id,@pending_export_id)
ORDER BY r.role_id,m.parent_id,m.order_num,m.menu_id;

-- =========================
-- 部署结果核对（只读）
-- =========================
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  CASE WHEN TABLE_NAME IS NULL THEN 'MISSING' ELSE 'OK' END AS deploy_status
FROM information_schema.TABLES
WHERE (TABLE_SCHEMA='date-project' AND TABLE_NAME IN (
  'dim_amz_sop_after_sales_category',
  'ebay_sku_analysis_import_batch',
  'ods_ebay_sku_analysis_order_raw',
  'dwd_ebay_sku_analysis_order',
  'ebay_sku_analysis_return_classification'
))
OR (TABLE_SCHEMA='jmh_data_platform' AND TABLE_NAME IN (
  'sys_user_column_config',
  'ebay_replenishment_v2_lead_time',
  'ebay_replenishment_v2_warehouse_rent',
  'ebay_replenishment_v2_warehouse_rent_import_lock',
  'ebay_replenishment_v2_warehouse_rent_detail',
  'procurement_pending_purchase'
))
ORDER BY TABLE_SCHEMA,TABLE_NAME;

-- 原 eBay 补货库存来源表是既有公共依赖，本脚本不重建，结果应为1。
SELECT COUNT(*) AS warehouse_inventory_detail_exists
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='jmh_data_platform'
  AND TABLE_NAME='warehouse_inventory_detail';

USE `jmh_data_platform`;

SELECT menu_id,parent_id,menu_name,order_num,path,component,menu_type,perms,status
FROM sys_menu
WHERE path IN ('store-analysis','sku-analysis','return-overview','return-detail','replenishment-v2',
               'procurement','pending-purchase')
   OR perms IN (
     'operations:ebaySkuAnalysis:list',
     'operations:ebaySkuAnalysis:import',
     'operations:ebayReturnOverview:list',
     'operations:ebayReturnDetail:list',
     'operations:ebayReplenishmentV2:list',
     'operations:ebayReplenishmentV2:editLeadTime',
     'operations:ebayReplenishmentV2:importWarehouseRent',
     'procurement:pendingPurchase:list',
     'procurement:pendingPurchase:add',
     'procurement:pendingPurchase:export'
   )
ORDER BY parent_id,order_num,menu_id;

SELECT DISTINCT
  u.user_name,
  r.role_id,
  r.role_name,
  m.menu_id,
  m.menu_name,
  m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu'
  AND (
    m.path IN ('store-analysis','sku-analysis','return-overview','return-detail','replenishment-v2',
               'procurement','pending-purchase')
    OR m.perms LIKE 'operations:ebaySkuAnalysis:%'
    OR m.perms LIKE 'operations:ebayReturn%'
    OR m.perms LIKE 'operations:ebayReplenishmentV2:%'
    OR m.perms LIKE 'procurement:pendingPurchase:%'
  )
ORDER BY r.role_id,m.menu_id;

-- 执行结束。
