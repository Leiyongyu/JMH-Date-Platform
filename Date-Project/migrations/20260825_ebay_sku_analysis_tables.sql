CREATE TABLE IF NOT EXISTS ebay_sku_analysis_import_batch (
  import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID', source_file_name VARCHAR(255) NOT NULL COMMENT '来源文件名',
  imported_months VARCHAR(255) NOT NULL COMMENT '本次覆盖月份列表', total_rows INT NOT NULL DEFAULT 0 COMMENT 'Excel总行数',
  valid_rows INT NOT NULL DEFAULT 0 COMMENT '有效入库行数', skipped_rows INT NOT NULL DEFAULT 0 COMMENT '跳过行数',
  operator_name VARCHAR(128) DEFAULT NULL COMMENT '上传操作人', status VARCHAR(32) NOT NULL COMMENT '导入状态',
  error_message VARCHAR(1000) DEFAULT NULL COMMENT '失败原因', create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  complete_time DATETIME DEFAULT NULL COMMENT '完成时间', PRIMARY KEY (import_batch_id), KEY idx_esa_batch_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay SKU分析文件导入批次';
CREATE TABLE IF NOT EXISTS ods_ebay_sku_analysis_order_raw (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID', stat_month CHAR(7) NOT NULL COMMENT '统计月份，格式YYYY-MM',
  source_file_name VARCHAR(255) NOT NULL COMMENT '来源文件名', source_sheet VARCHAR(128) NOT NULL COMMENT '来源工作表', source_row INT NOT NULL COMMENT '来源Excel行号',
  platform_order_no VARCHAR(128) NOT NULL COMMENT '平台订单号', payment_time DATETIME NOT NULL COMMENT '付款时间', inventory_sku VARCHAR(128) NOT NULL COMMENT '库存SKU',
  purchase_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '购买数量', paid_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '分摊后已支付金额人民币',
  shipping_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '分摊后运费人民币', platform_fee_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '分摊后平台费用人民币',
  currency_code VARCHAR(16) DEFAULT NULL COMMENT '币种', exchange_rate DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '汇率', customer_id VARCHAR(255) DEFAULT NULL COMMENT '客户ID',
  site_code VARCHAR(32) NOT NULL COMMENT '标准站点代码', site_name VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称', country_name VARCHAR(128) DEFAULT NULL COMMENT '国家名称', seller_account VARCHAR(128) NOT NULL COMMENT '销售员原始字段',
  shipping_status VARCHAR(64) DEFAULT NULL COMMENT '发货状态', paid_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额原币', shipping_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币', refund_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '已退款购买数量', refund_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币',
  raw_json JSON NOT NULL COMMENT 'Excel整行原始数据JSON', create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间', PRIMARY KEY (id),
  KEY idx_esa_raw_month (stat_month), KEY idx_esa_raw_sku (inventory_sku), KEY idx_esa_raw_order_date (platform_order_no,payment_time), KEY idx_esa_raw_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ODS-eBay SKU分析订单上传原始数据';
CREATE TABLE IF NOT EXISTS dwd_ebay_sku_analysis_order (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', stat_month CHAR(7) NOT NULL COMMENT '统计月份，格式YYYY-MM', payment_time DATETIME NOT NULL COMMENT '付款时间',
  platform_order_no VARCHAR(128) NOT NULL COMMENT '平台订单号', inventory_sku VARCHAR(128) NOT NULL COMMENT '标准库存SKU', purchase_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '购买数量',
  paid_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额人民币', shipping_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '运费人民币',
  platform_fee_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台费用人民币', paid_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额原币', shipping_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币', refund_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '已退款购买数量', refund_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币', shipping_status VARCHAR(64) DEFAULT NULL COMMENT '发货状态', currency_code VARCHAR(16) DEFAULT NULL COMMENT '币种', customer_id VARCHAR(255) DEFAULT NULL COMMENT '客户ID', site_code VARCHAR(32) NOT NULL COMMENT '标准站点代码', site_name VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称',
  country_name VARCHAR(128) DEFAULT NULL COMMENT '国家名称', seller_account VARCHAR(128) NOT NULL COMMENT '销售账号', import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID',
  source_row INT NOT NULL COMMENT '来源Excel行号', create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间', PRIMARY KEY (id),
  UNIQUE KEY uk_esa_dwd_month_row (stat_month, import_batch_id, source_row), KEY idx_esa_dwd_order_date (platform_order_no,payment_time), KEY idx_esa_dwd_time (payment_time), KEY idx_esa_dwd_sku (inventory_sku), KEY idx_esa_dwd_site (site_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DWD-eBay SKU分析订单清洗明细';
