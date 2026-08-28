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
DROP TABLE IF EXISTS dws_ebay_sku_analysis_profit_daily;
DROP TABLE IF EXISTS dwd_ebay_sku_analysis_profit;
DROP TABLE IF EXISTS ods_ebay_sku_analysis_profit_raw;
DROP TABLE IF EXISTS ebay_sku_analysis_profit_import_batch;
