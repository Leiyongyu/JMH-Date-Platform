-- eBay SOP 售后：数字酋长销量/售后上传、历史标准售后、清洗明细及区间汇总。

CREATE TABLE IF NOT EXISTS etl_ebay_sop_import_batch (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    batch_id VARCHAR(64) NOT NULL COMMENT '导入批次号',
    import_type VARCHAR(32) NOT NULL COMMENT '导入类型：SALES/HISTORY/AFTER_SALES',
    file_name VARCHAR(255) NOT NULL COMMENT '源文件名',
    file_sha256 CHAR(64) NOT NULL COMMENT '文件SHA256',
    operator VARCHAR(64) NULL COMMENT '上传人',
    status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING' COMMENT '状态：PROCESSING/SUCCESS/FAILED',
    total_rows INT NOT NULL DEFAULT 0 COMMENT 'Excel数据行数',
    raw_rows INT NOT NULL DEFAULT 0 COMMENT 'ODS有效行数',
    dwd_rows INT NOT NULL DEFAULT 0 COMMENT 'DWD生成行数',
    skipped_rows INT NOT NULL DEFAULT 0 COMMENT '跳过行数',
    error_message TEXT NULL COMMENT '错误信息',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    completed_at DATETIME NULL COMMENT '完成时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_import_batch (batch_id),
    KEY idx_ebay_sop_import_file (import_type,file_sha256),
    KEY idx_ebay_sop_import_time (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ETL-eBay SOP文件导入批次';

CREATE TABLE IF NOT EXISTS ods_ebay_sop_order_raw (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    source_key CHAR(64) NOT NULL COMMENT '数据类型+源文件+工作表+行号生成的原始行键',
    data_kind VARCHAR(20) NOT NULL COMMENT '数据用途：SALES/AFTER_SALES',
    source_file VARCHAR(255) NOT NULL COMMENT '源文件名',
    source_sheet VARCHAR(128) NOT NULL COMMENT '源工作表',
    source_row_no INT NOT NULL COMMENT 'Excel源行号',
    platform_order_no VARCHAR(128) NULL COMMENT '平台订单号',
    shipping_status VARCHAR(100) NULL COMMENT '发货状态原值',
    package_status VARCHAR(100) NULL COMMENT '包裹状态原值',
    exception_status VARCHAR(255) NULL COMMENT '异常状态原值',
    logistics_channel VARCHAR(255) NULL COMMENT '物流渠道原值',
    tracking_no VARCHAR(255) NULL COMMENT '货运单号原值',
    payment_time DATETIME NULL COMMENT '付款时间原值',
    marked_ship_time DATETIME NULL COMMENT '标发时间原值',
    platform_name VARCHAR(50) NULL COMMENT '平台原值',
    currency_code VARCHAR(20) NULL COMMENT '币种原值',
    receivable_goods DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '应收货款订单级原值',
    receivable_shipping DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '应收运费原值',
    platform_fee DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '平台费用原值',
    insurance_amount DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '保险金额原值',
    transfer_fee DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '转账费原值',
    paypal_receipt VARCHAR(255) NULL COMMENT '收款Paypal原值',
    customer_id VARCHAR(255) NULL COMMENT '客户ID原值',
    recipient VARCHAR(255) NULL COMMENT '收件人原值',
    customer_email VARCHAR(255) NULL COMMENT '客户邮箱原值',
    recipient_phone1 VARCHAR(100) NULL COMMENT '收件人电话1原值',
    recipient_phone2 VARCHAR(100) NULL COMMENT '收件人电话2原值',
    recipient_country VARCHAR(255) NULL COMMENT '收件人国家原值',
    recipient_state VARCHAR(255) NULL COMMENT '收件人省州原值',
    recipient_city VARCHAR(255) NULL COMMENT '收件人城市原值',
    recipient_postal_code VARCHAR(100) NULL COMMENT '收件人邮编原值',
    recipient_address1 TEXT NULL COMMENT '收件地址原值',
    recipient_address2 TEXT NULL COMMENT '收件地址2原值',
    recipient_address3 TEXT NULL COMMENT '收件地址3原值',
    recipient_alt_address TEXT NULL COMMENT '收件人备用地址原值',
    recipient_house_no VARCHAR(100) NULL COMMENT '收件人门牌号原值',
    inventory_sku VARCHAR(255) NULL COMMENT '库存SKU原值',
    sku_status VARCHAR(100) NULL COMMENT 'SKU状态原值',
    purchase_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '购买数量原值',
    allocated_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '申请库存数量原值',
    paypal_transaction_no VARCHAR(500) NULL COMMENT 'PayPal交易号原值',
    salesperson VARCHAR(255) NULL COMMENT '销售员原值',
    exchange_rate DECIMAL(24,8) NOT NULL DEFAULT 0 COMMENT '汇率原值',
    original_currency_income DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '原币收入原值',
    country_cn VARCHAR(255) NULL COMMENT '国家中文原值',
    country_en VARCHAR(255) NULL COMMENT '国家英文原值',
    import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次写入时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_order_source (source_key),
    KEY idx_ebay_sop_order_kind_time (data_kind,payment_time),
    KEY idx_ebay_sop_order_no (platform_order_no),
    KEY idx_ebay_sop_order_sku (inventory_sku),
    KEY idx_ebay_sop_order_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-eBay数字酋长订单原始字段';

CREATE TABLE IF NOT EXISTS ods_ebay_sop_after_sales_history (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    source_key CHAR(64) NOT NULL COMMENT '源文件+工作表+行号生成的原始行键',
    order_no VARCHAR(128) NULL COMMENT '订单号原值',
    payment_time DATETIME NULL COMMENT '付款时间原值',
    refund_time DATETIME NULL COMMENT '退款时间原值',
    product_title TEXT NULL COMMENT '仓库商品标题原值',
    after_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '售后数量原值',
    product_sku VARCHAR(255) NULL COMMENT '产品SKU原值',
    small_category VARCHAR(100) NULL COMMENT '历史售后小类原值',
    big_category VARCHAR(50) NULL COMMENT '历史售后大类原值',
    data_source VARCHAR(50) NULL COMMENT '数据来源原值',
    platform_name VARCHAR(100) NULL COMMENT '平台原值',
    after_sales_note TEXT NULL COMMENT '售后备注原值',
    source_file VARCHAR(255) NOT NULL COMMENT '源文件名',
    source_sheet VARCHAR(128) NOT NULL COMMENT '源工作表',
    source_row_no INT NOT NULL COMMENT 'Excel源行号',
    import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次写入时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_history_source (source_key),
    KEY idx_ebay_sop_history_refund (refund_time),
    KEY idx_ebay_sop_history_sku (product_sku),
    KEY idx_ebay_sop_history_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-eBay一次性历史标准售后数据';

CREATE TABLE IF NOT EXISTS ods_ebay_sop_sales_history (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    source_key CHAR(64) NOT NULL COMMENT '源文件+工作表+行号生成的原始行键',
    sale_month CHAR(7) NULL COMMENT '原始销量月份YYYY-MM',
    data_source VARCHAR(50) NULL COMMENT '数据来源原值',
    product_sku VARCHAR(255) NULL COMMENT '产品SKU原值',
    sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '销量原值',
    source_file VARCHAR(255) NOT NULL COMMENT '源文件名',
    source_sheet VARCHAR(128) NOT NULL COMMENT '源工作表',
    source_row_no INT NOT NULL COMMENT 'Excel源行号',
    import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次写入时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_sales_history_source (source_key),
    KEY idx_ebay_sop_sales_history_month (sale_month,data_source),
    KEY idx_ebay_sop_sales_history_sku (product_sku),
    KEY idx_ebay_sop_sales_history_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-eBay一次性历史月销量原始数据';

CREATE TABLE IF NOT EXISTS dwd_ebay_sop_sales_daily (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    sale_date DATE NOT NULL COMMENT '付款日期',
    data_source VARCHAR(50) NOT NULL COMMENT 'eBay-US/eBay-UK/eBay-DE/eBay-OTHER',
    business_sku VARCHAR(255) NOT NULL COMMENT '清洗后的业务SKU',
    currency_code VARCHAR(20) NOT NULL COMMENT '订单币种',
    sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '同日同SKU同来源销量合计',
    unit_price_total DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '同日同SKU同来源单价合计',
    sales_amount DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '应收货款合计',
    order_count INT NOT NULL DEFAULT 0 COMMENT '订单数',
    import_batch_id VARCHAR(64) NOT NULL COMMENT '最近重建批次号',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_sales_daily (sale_date,data_source,business_sku,currency_code),
    KEY idx_ebay_sop_sales_range (sale_date,business_sku),
    KEY idx_ebay_sop_sales_source (data_source,sale_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-eBay按日SKU来源清洗销量';

CREATE TABLE IF NOT EXISTS dwd_ebay_sop_sales_monthly (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    month_start DATE NOT NULL COMMENT '自然月开始日期',
    month_end DATE NOT NULL COMMENT '自然月结束日期',
    data_source VARCHAR(50) NOT NULL COMMENT 'eBay-US/eBay-UK/eBay-DE/eBay-OTHER',
    business_sku VARCHAR(255) NOT NULL COMMENT '清洗后的业务SKU',
    sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '同月同SKU同来源销量合计',
    import_batch_id VARCHAR(64) NOT NULL COMMENT '最近历史导入批次号',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_sales_monthly (month_start,data_source,business_sku),
    KEY idx_ebay_sop_sales_monthly_range (month_start,month_end,business_sku),
    KEY idx_ebay_sop_sales_monthly_source (data_source,month_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-eBay一次性历史月销量';

CREATE TABLE IF NOT EXISTS dwd_ebay_sop_after_sales (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    source_key CHAR(64) NOT NULL COMMENT '售后明细业务唯一键',
    source_kind VARCHAR(20) NOT NULL COMMENT '来源：HISTORY/AFTER_SALES',
    order_no VARCHAR(128) NOT NULL COMMENT '平台订单号',
    payment_time DATETIME NULL COMMENT '付款时间',
    after_time DATETIME NOT NULL COMMENT '退款/售后统计时间',
    product_title TEXT NULL COMMENT '商品标题',
    after_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '售后数量',
    business_sku VARCHAR(255) NOT NULL COMMENT '清洗后的业务SKU',
    after_type VARCHAR(20) NOT NULL COMMENT '退款/退货',
    big_category VARCHAR(50) NOT NULL COMMENT '售后原因大类',
    small_category VARCHAR(100) NOT NULL COMMENT '售后原因小类',
    data_source VARCHAR(50) NOT NULL COMMENT 'eBay-US/eBay-UK/eBay-DE/eBay-OTHER',
    platform_name VARCHAR(100) NULL COMMENT '数据平台',
    after_sales_note TEXT NULL COMMENT '分类使用及展示的售后备注',
    classify_method VARCHAR(30) NOT NULL DEFAULT 'history' COMMENT 'history/rule/deepseek/fallback',
    confidence DECIMAL(8,6) NOT NULL DEFAULT 0 COMMENT '分类置信度',
    import_batch_id VARCHAR(64) NOT NULL COMMENT '最近导入批次号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次写入时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_after_source (source_key),
    KEY idx_ebay_sop_after_range (after_time,business_sku),
    KEY idx_ebay_sop_after_category (big_category,small_category),
    KEY idx_ebay_sop_after_order (order_no),
    KEY idx_ebay_sop_after_source_date (data_source,after_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-eBay已清洗分类售后明细';

CREATE TABLE IF NOT EXISTS dws_ebay_sop_after_sales_summary (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    period_start DATE NOT NULL COMMENT '统计开始日期',
    period_end DATE NOT NULL COMMENT '统计结束日期',
    big_category VARCHAR(50) NOT NULL COMMENT '售后原因大类',
    small_category VARCHAR(100) NOT NULL COMMENT '售后原因小类',
    business_sku VARCHAR(255) NOT NULL COMMENT '业务SKU',
    order_count INT NOT NULL DEFAULT 0 COMMENT '售后订单数',
    order_numbers LONGTEXT NULL COMMENT '去重订单号列表',
    source_after_quantity_text TEXT NULL COMMENT '各eBay站点售后数量',
    source_sales_volume_text TEXT NULL COMMENT '各eBay站点销量',
    after_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '售后数量',
    sales_volume DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '销量',
    after_sales_rate DECIMAL(16,8) NOT NULL DEFAULT 0 COMMENT '售后率=售后数量/销量',
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_sop_summary (period_start,period_end,big_category,small_category,business_sku),
    KEY idx_ebay_sop_summary_period (period_start,period_end),
    KEY idx_ebay_sop_summary_sku (business_sku,period_start,period_end),
    KEY idx_ebay_sop_summary_quantity (period_start,period_end,after_quantity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWS-eBay SOP售后率区间汇总';

-- 兼容已经按早期测试结构建过的原始表：缺失业务键的源行也必须保留在ODS，
-- 只在进入DWD时跳过，因此两个原始字段允许NULL。该变更不会删除或改写数据。
ALTER TABLE ods_ebay_sop_after_sales_history
    MODIFY COLUMN order_no VARCHAR(128) NULL COMMENT '订单号原值',
    MODIFY COLUMN product_sku VARCHAR(255) NULL COMMENT '产品SKU原值';
