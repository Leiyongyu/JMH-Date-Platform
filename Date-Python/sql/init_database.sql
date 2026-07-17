-- ============================================================
-- 外汇退税数据平台 — 数据库初始化脚本
-- 目标数据库: MySQL 9.7+
-- 字符集: utf8mb4
-- ============================================================

CREATE DATABASE IF NOT EXISTS export_tax_refund
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci
  COMMENT '出口退税、进货库存、外汇回款及申报管理数据库';

USE export_tax_refund;

DROP TABLE IF EXISTS api_task;

-- -----------------------------------------------------------
-- 1. 文件导入批次表
-- -----------------------------------------------------------
DROP TABLE IF EXISTS import_batch;
CREATE TABLE import_batch (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '导入批次主键',
    import_type VARCHAR(30) NOT NULL COMMENT '导入类型：CUSTOMS_PDF报关单、INVOICE_PDF发票、FOREX_EXCEL外汇回款',
    original_file_name VARCHAR(255) NOT NULL COMMENT '用户上传时的原始文件名',
    stored_file_path VARCHAR(1000) NOT NULL COMMENT '服务器保存的文件路径',
    file_sha256 CHAR(64) NOT NULL COMMENT '文件SHA-256摘要，用于重复上传校验',
    file_size BIGINT NOT NULL COMMENT '文件大小，单位字节',
    parse_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '解析状态：PENDING待解析、PARSING解析中、PREVIEW待确认、SUCCESS成功、FAILED失败、CANCELLED取消',
    total_count INT NOT NULL DEFAULT 0 COMMENT '解析得到的总记录数',
    success_count INT NOT NULL DEFAULT 0 COMMENT '校验通过或成功导入的记录数',
    error_count INT NOT NULL DEFAULT 0 COMMENT '解析或校验失败的记录数',
    error_message TEXT NULL COMMENT '批次级错误信息或失败原因',
    created_by VARCHAR(64) NOT NULL COMMENT '上传或创建批次的用户标识',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_by VARCHAR(64) NULL COMMENT '最后修改用户标识',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_import_batch_hash_type (file_sha256, import_type),
    KEY idx_import_batch_status (parse_status),
    KEY idx_import_batch_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='文件上传、解析、预览确认及错误追踪批次表';

-- -----------------------------------------------------------
-- 1b. ERP统一API任务表
-- -----------------------------------------------------------
CREATE TABLE api_task (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '统一API任务主键',
    task_type VARCHAR(50) NOT NULL COMMENT '任务类型',
    task_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/PARTIAL/FAILED',
    progress_current INT NOT NULL DEFAULT 0,
    progress_total INT NOT NULL DEFAULT 0,
    request_payload JSON NULL,
    result_payload JSON NULL,
    error_message TEXT NULL,
    original_file_name VARCHAR(255) NULL,
    stored_file_path VARCHAR(1000) NULL,
    file_sha256 CHAR(64) NULL,
    created_by VARCHAR(64) NOT NULL DEFAULT 'ERP',
    started_at DATETIME(3) NULL,
    completed_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_api_task_type_status (task_type, task_status),
    KEY idx_api_task_created_at (created_at),
    KEY idx_api_task_file_hash (file_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='ERP调用Python服务的统一任务资源';

-- -----------------------------------------------------------
-- 2. 出口明细表（报关单商品）
-- -----------------------------------------------------------
DROP TABLE IF EXISTS export_detail;
CREATE TABLE export_detail (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '出口商品明细主键',
    customs_excel_item_id BIGINT NULL COMMENT '匹配的报关资料Excel商品主键',
    customs_declaration_no VARCHAR(30) NOT NULL COMMENT '海关出口货物报关单编号',
    customs_item_no VARCHAR(10) NOT NULL COMMENT '报关单内商品项号，不作为申报批次',
    declaration_date DATE NULL COMMENT '报关单申报日期',
    export_date DATE NULL COMMENT '报关单出口日期',
    contract_no VARCHAR(100) NULL COMMENT '报关单合同协议号',
    overseas_consignee VARCHAR(255) NULL COMMENT '报关单境外收货人名称',
    export_invoice_no VARCHAR(100) NULL COMMENT '出口发票号码，报关单无来源时允许后续补录',
    agency_certificate_no VARCHAR(100) NULL COMMENT '代理出口货物证明号',
    export_product_code VARCHAR(20) NOT NULL COMMENT '报关单商品编号或出口商品代码',
    export_product_name VARCHAR(500) NULL COMMENT '从报关单商品名称及规格型号中提取的商品名称',
    product_specification VARCHAR(1000) NULL COMMENT '报关单商品名称及规格型号完整原文',
    sku_original VARCHAR(200) NULL COMMENT '从报关单规格型号中提取的原始完整SKU',
    sku_normalized VARCHAR(200) NULL COMMENT '标准化后用于库存精确匹配的完整SKU',
    unit VARCHAR(50) NULL COMMENT '报关单商品计量单位',
    export_quantity DECIMAL(20,6) NOT NULL COMMENT '报关单商品出口数量',
    statutory_quantity DECIMAL(20,6) NULL COMMENT '报关资料法定数量',
    statutory_unit VARCHAR(50) NULL COMMENT '报关资料法定单位',
    unit_price DECIMAL(20,8) NULL COMMENT '报关单商品单价',
    fob_amount DECIMAL(20,2) NULL COMMENT '报关单商品美元离岸价或经审核确认的出口金额',
    currency_code VARCHAR(10) NULL COMMENT '报关单商品金额币种代码，如USD',
    declaration_month CHAR(6) NULL COMMENT '退税申报年月，库存分配确认后填写，格式YYYYMM',
    declaration_batch CHAR(3) NULL COMMENT '退税申报批次，库存分配确认后填写',
    sequence_no CHAR(8) NULL COMMENT '申报任务内8位序号，库存分配确认后生成',
    relation_no VARCHAR(40) NULL COMMENT '申报关联号，由申报年月、批次和序号拼接生成',
    declaration_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '申报状态：PENDING待匹配、PARTIAL部分分配、ALLOCATED分配完成、DECLARED已申报、CANCELLED已取消',
    declared_product_code VARCHAR(20) NULL COMMENT '退税申报商品代码，业务确认后填写',
    tax_business_type VARCHAR(50) NULL COMMENT '退免税业务类型',
    remark VARCHAR(1000) NULL COMMENT '人工备注、解析异常或业务补充说明',
    customs_match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED' COMMENT '报关资料匹配状态',
    customs_match_message VARCHAR(1000) NULL COMMENT '匹配差异或异常说明',
    source_file_name VARCHAR(255) NOT NULL COMMENT '来源报关单PDF文件名',
    source_file_hash CHAR(64) NOT NULL COMMENT '来源报关单PDF的SHA-256摘要',
    source_page_no INT NULL COMMENT '该商品首次出现的PDF页码',
    parse_confidence DECIMAL(5,4) NULL COMMENT '关键字段综合解析置信度，范围0至1',
    parse_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '解析状态：PENDING待校验、CONFIRMED已确认、ERROR异常',
    import_batch_id BIGINT NOT NULL COMMENT '对应文件导入批次主键',
    is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '逻辑删除标志：0正常、1已删除',
    deleted_by VARCHAR(64) NULL COMMENT '执行逻辑删除的用户标识',
    deleted_at DATETIME(3) NULL COMMENT '逻辑删除时间',
    created_by VARCHAR(64) NOT NULL COMMENT '创建用户或导入任务标识',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_by VARCHAR(64) NULL COMMENT '最后修改用户标识',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_export_customs_item (customs_declaration_no, customs_item_no, is_deleted),
    UNIQUE KEY uk_export_relation_no (relation_no),
    KEY idx_export_sku_status (sku_normalized, declaration_status),
    KEY idx_export_date (export_date),
    KEY idx_export_import_batch (import_batch_id),
    KEY idx_export_excel_item (customs_excel_item_id),
    CONSTRAINT fk_export_import_batch FOREIGN KEY (import_batch_id) REFERENCES import_batch (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='报关单出口商品明细及后续退税申报状态表';

-- -----------------------------------------------------------
-- 3. 进货库存表（发票商品）
-- -----------------------------------------------------------
DROP TABLE IF EXISTS purchase_inventory;
CREATE TABLE purchase_inventory (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '进货发票商品库存主键',
    invoice_no VARCHAR(50) NOT NULL COMMENT '增值税发票号码',
    invoice_date DATE NOT NULL COMMENT '发票完整开票日期',
    invoice_item_no INT NOT NULL COMMENT '发票内商品行序号',
    supplier_name VARCHAR(255) NULL COMMENT '发票销售方或供货方名称',
    supplier_tax_no VARCHAR(30) NOT NULL COMMENT '发票销售方统一社会信用代码或纳税人识别号',
    buyer_name VARCHAR(255) NULL COMMENT '发票购买方名称',
    buyer_tax_no VARCHAR(30) NULL COMMENT '发票购买方统一社会信用代码或纳税人识别号',
    tax_type VARCHAR(30) NOT NULL DEFAULT 'V|增值税' COMMENT '税种，默认V|增值税',
    product_name VARCHAR(500) NULL COMMENT '发票项目名称或去除税收分类前缀后的商品名称',
    product_specification VARCHAR(500) NULL COMMENT '发票规格型号完整原文',
    sku_original VARCHAR(200) NULL COMMENT '从发票规格型号中提取的原始完整SKU',
    sku_normalized VARCHAR(200) NULL COMMENT '标准化后用于出口库存精确匹配的完整SKU',
    unit VARCHAR(50) NULL COMMENT '发票商品计量单位',
    purchased_quantity DECIMAL(20,6) NOT NULL COMMENT '发票商品采购数量或入库数量',
    allocated_quantity DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已被有效申报分配占用的数量缓存',
    remaining_quantity DECIMAL(20,6) NOT NULL COMMENT '当前可分配剩余数量缓存，等于采购数量减已分配数量',
    unit_price DECIMAL(20,8) NULL COMMENT '发票商品不含税单价',
    taxable_amount DECIMAL(20,2) NOT NULL COMMENT '发票商品行不含税金额，即进货申报计税金额来源',
    tax_rate DECIMAL(8,6) NULL COMMENT '发票商品征税率，小数存储，如13%存0.130000',
    refund_rate DECIMAL(8,6) NULL COMMENT '商品退税率，小数存储，申报前可根据商品代码维护',
    tax_amount DECIMAL(20,2) NOT NULL COMMENT '发票商品行税额',
    refundable_tax_amount DECIMAL(20,2) NULL COMMENT '该库存批次可退税额总额，最终按分配数量拆分',
    inventory_status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE' COMMENT '库存状态：AVAILABLE可用、PARTIAL部分使用、EXHAUSTED已用完、LOCKED锁定、CANCELLED作废',
    remark VARCHAR(1000) NULL COMMENT '人工备注、发票解析异常或库存调整说明',
    source_file_name VARCHAR(255) NOT NULL COMMENT '来源发票PDF文件名',
    source_file_hash CHAR(64) NOT NULL COMMENT '来源发票PDF的SHA-256摘要',
    source_page_no INT NULL COMMENT '来源发票PDF页码',
    parse_confidence DECIMAL(5,4) NULL COMMENT '关键字段综合解析置信度，范围0至1',
    parse_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '解析状态：PENDING待校验、CONFIRMED已确认、ERROR异常',
    import_batch_id BIGINT NOT NULL COMMENT '对应文件导入批次主键',
    is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '逻辑删除标志：0正常、1已删除',
    deleted_by VARCHAR(64) NULL COMMENT '执行逻辑删除的用户标识',
    deleted_at DATETIME(3) NULL COMMENT '逻辑删除时间',
    created_by VARCHAR(64) NOT NULL COMMENT '创建用户或导入任务标识',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_by VARCHAR(64) NULL COMMENT '最后修改用户标识',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_purchase_invoice_item (invoice_no, invoice_item_no, is_deleted),
    KEY idx_purchase_sku_inventory (sku_normalized, inventory_status, invoice_date),
    KEY idx_purchase_supplier (supplier_tax_no),
    KEY idx_purchase_import_batch (import_batch_id),
    CONSTRAINT fk_purchase_import_batch FOREIGN KEY (import_batch_id) REFERENCES import_batch (id),
    CONSTRAINT chk_purchase_quantity CHECK (purchased_quantity >= 0 AND allocated_quantity >= 0 AND remaining_quantity >= 0),
    CONSTRAINT chk_purchase_allocation CHECK (allocated_quantity + remaining_quantity = purchased_quantity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='增值税发票商品库存及可申报剩余数量表';

DROP TABLE IF EXISTS export_purchase_allocation;
DROP TABLE IF EXISTS declaration_task;

-- -----------------------------------------------------------
-- 6. 外汇 — 报关单应收表
-- -----------------------------------------------------------
DROP TABLE IF EXISTS forex_receipt_allocation;
DROP TABLE IF EXISTS forex_receipt_old;
DROP TABLE IF EXISTS forex_receipt;
DROP TABLE IF EXISTS forex_export_receivable;

CREATE TABLE forex_export_receivable (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '应收主键',
    customs_no_match_key CHAR(18) NOT NULL COMMENT '报关单号前18位标准匹配键',
    customs_declaration_no VARCHAR(30) NOT NULL COMMENT '原始报关单号',
    contract_no VARCHAR(100) NULL COMMENT '合同编号',
    business_entity VARCHAR(50) NULL COMMENT '业务主体',
    export_date DATE NULL COMMENT '出口日期',
    customs_port VARCHAR(100) NULL COMMENT '出口口岸',
    customs_contract_usd DECIMAL(20,2) NULL COMMENT '报关合同金额USD',
    export_amount_usd DECIMAL(20,2) NULL COMMENT '出口金额USD',
    monthly_exchange_rate DECIMAL(12,6) NULL COMMENT '月度汇率标准化值',
    monthly_exchange_rate_raw DECIMAL(12,6) NULL COMMENT '月度汇率原始值',
    source_type VARCHAR(20) NOT NULL DEFAULT 'EXCEL_IMPORT',
    source_file_name VARCHAR(255) NULL,
    source_sheet_name VARCHAR(100) NULL,
    source_row_no INT NULL,
    import_batch_id BIGINT NULL,
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_receivable_customs (customs_no_match_key),
    KEY idx_receivable_contract (contract_no),
    KEY idx_receivable_entity (business_entity),
    KEY idx_receivable_import_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='报关单应收记录';

-- -----------------------------------------------------------
-- 6b. 外汇 — 银行回款主记录
-- -----------------------------------------------------------
CREATE TABLE forex_receipt (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '回款主键',
    receipt_business_key CHAR(64) NOT NULL COMMENT '回款唯一指纹',
    core_transaction_no VARCHAR(100) NULL COMMENT '银行核心流水号',
    receipt_total_usd DECIMAL(20,2) NULL COMMENT '回款总金额USD',
    actual_exchange_rate DECIMAL(12,6) NULL COMMENT '实际汇率标准化值',
    actual_exchange_rate_raw DECIMAL(12,6) NULL COMMENT '实际汇率原始值',
    settlement_receipt_rmb DECIMAL(20,2) NULL COMMENT '回单结汇金额RMB',
    receipt_date DATE NULL COMMENT '收汇日期',
    difference_usd DECIMAL(20,2) NULL COMMENT '收汇总额与关联报关单回款金额的差额USD',
    business_entity VARCHAR(50) NULL,
    source_sheet_name VARCHAR(100) NULL,
    import_batch_id BIGINT NULL,
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_receipt_business (receipt_business_key),
    KEY idx_receipt_core_tx (core_transaction_no),
    KEY idx_receipt_date (receipt_date),
    KEY idx_receipt_import_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行回款主记录';

-- -----------------------------------------------------------
-- 6c. 外汇 — 回款分配明细
-- -----------------------------------------------------------
CREATE TABLE forex_receipt_allocation (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '分配主键',
    receipt_id BIGINT NOT NULL COMMENT '回款主记录ID',
    receivable_id BIGINT NOT NULL COMMENT '应收记录ID',
    allocated_amount_usd DECIMAL(20,2) NOT NULL COMMENT '分配金额USD',
    source_sheet_name VARCHAR(100) NULL,
    source_row_no INT NULL,
    import_batch_id BIGINT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_allocation (receipt_id, receivable_id),
    KEY idx_allocation_receivable (receivable_id),
    CONSTRAINT fk_allocation_receipt FOREIGN KEY (receipt_id) REFERENCES forex_receipt (id),
    CONSTRAINT fk_allocation_receivable FOREIGN KEY (receivable_id) REFERENCES forex_export_receivable (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='回款与报关单分配关系';

DROP TABLE IF EXISTS sku_unit_conversion;
