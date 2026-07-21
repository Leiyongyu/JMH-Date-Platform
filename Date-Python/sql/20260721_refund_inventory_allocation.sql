-- 退税文件生成库存预占、FIFO 扣减、流水及冲销（增量迁移）
-- 执行库：export_tax_refund

-- MySQL 不支持 ADD COLUMN/CREATE INDEX IF NOT EXISTS。
-- 以下使用 information_schema + 动态 SQL，脚本可安全重复执行。
SET @schema_name = DATABASE();

SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='operator_id')=0,
    'ALTER TABLE api_task ADD COLUMN operator_id VARCHAR(64) NULL COMMENT ''ERP操作人ID'' AFTER created_by', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='operator_name')=0,
    'ALTER TABLE api_task ADD COLUMN operator_name VARCHAR(100) NULL COMMENT ''ERP操作人姓名快照'' AFTER operator_id', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND COLUMN_NAME='idempotency_key')=0,
    'ALTER TABLE api_task ADD COLUMN idempotency_key CHAR(64) NULL COMMENT ''请求幂等键SHA-256'' AFTER operator_name', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='api_task' AND INDEX_NAME='uk_api_task_idempotency')=0,
    'CREATE UNIQUE INDEX uk_api_task_idempotency ON api_task (idempotency_key)', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='reserved_quantity')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN reserved_quantity DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''退税生成任务已预占但尚未确认的数量'' AFTER allocated_quantity', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='last_allocated_at')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN last_allocated_at DATETIME(3) NULL COMMENT ''最近一次正式扣减时间'' AFTER inventory_status', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='last_allocation_task_id')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN last_allocation_task_id BIGINT NULL COMMENT ''最近一次库存操作任务ID'' AFTER last_allocated_at', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='version')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN version INT NOT NULL DEFAULT 0 COMMENT ''库存并发版本号'' AFTER last_allocation_task_id', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='declaration_month')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN declaration_month CHAR(6) NULL AFTER version', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='declaration_batch')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN declaration_batch CHAR(3) NULL AFTER declaration_month', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='sequence_no')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN sequence_no CHAR(8) NULL AFTER declaration_batch', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND COLUMN_NAME='relation_no')=0,
    'ALTER TABLE purchase_inventory ADD COLUMN relation_no VARCHAR(40) NULL AFTER sequence_no', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 旧约束不包含 reserved_quantity，存在时必须删除；应用事务负责维护新恒等式。
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND CONSTRAINT_NAME='chk_purchase_allocation' AND CONSTRAINT_TYPE='CHECK')>0,
    'ALTER TABLE purchase_inventory DROP CHECK chk_purchase_allocation', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='purchase_inventory' AND INDEX_NAME='idx_purchase_fifo')=0,
    'CREATE INDEX idx_purchase_fifo ON purchase_inventory (sku_normalized, supplier_tax_no, inventory_status, invoice_date, invoice_no, invoice_item_no, id)', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='export_detail' AND COLUMN_NAME='inventory_allocation_status')=0,
    'ALTER TABLE export_detail ADD COLUMN inventory_allocation_status VARCHAR(20) NOT NULL DEFAULT ''UNALLOCATED'' COMMENT ''UNALLOCATED/RESERVED/ALLOCATED/REVERSED'' AFTER declaration_status', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='export_detail' AND COLUMN_NAME='latest_refund_generation_id')=0,
    'ALTER TABLE export_detail ADD COLUMN latest_refund_generation_id BIGINT NULL COMMENT ''最近一次退税生成批次ID'' AFTER inventory_allocation_status', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='export_detail' AND COLUMN_NAME='inventory_allocated_at')=0,
    'ALTER TABLE export_detail ADD COLUMN inventory_allocated_at DATETIME(3) NULL COMMENT ''库存正式扣减时间'' AFTER latest_refund_generation_id', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='export_detail' AND INDEX_NAME='idx_export_inventory_allocation')=0,
    'CREATE INDEX idx_export_inventory_allocation ON export_detail (inventory_allocation_status, customs_match_status, id)', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 历史出口记录统一为21位：18位报关单基础编号 + 3位商品项号。
UPDATE export_detail
SET customs_declaration_no = CONCAT(
    LEFT(REPLACE(REPLACE(TRIM(customs_declaration_no), ' ', ''), CHAR(9), ''), 18),
    LPAD(CAST(customs_item_no AS UNSIGNED), 3, '0')
)
WHERE is_deleted = 0
  AND CHAR_LENGTH(REPLACE(REPLACE(TRIM(customs_declaration_no), ' ', ''), CHAR(9), '')) >= 18
  AND CAST(customs_item_no AS UNSIGNED) BETWEEN 1 AND 999
  AND customs_declaration_no <> CONCAT(
      LEFT(REPLACE(REPLACE(TRIM(customs_declaration_no), ' ', ''), CHAR(9), ''), 18),
      LPAD(CAST(customs_item_no AS UNSIGNED), 3, '0')
  );

CREATE TABLE IF NOT EXISTS refund_generation (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '退税文件生成批次主键',
    api_task_id BIGINT NOT NULL COMMENT '对应统一API任务ID',
    idempotency_key VARCHAR(128) NULL COMMENT 'ERP请求幂等键',
    declaration_month CHAR(6) NOT NULL COMMENT '申报年月',
    output_directory VARCHAR(1000) NULL COMMENT '最终输出目录',
    staging_directory VARCHAR(1000) NULL COMMENT '文件发布前临时目录',
    generation_status VARCHAR(20) NOT NULL DEFAULT 'PREPARING'
        COMMENT 'PREPARING/RESERVED/FILE_PENDING/COMMITTED/FAILED/REVERSED',
    generated_by_id VARCHAR(64) NOT NULL COMMENT 'ERP操作人ID',
    generated_by_name VARCHAR(100) NOT NULL COMMENT 'ERP操作人姓名快照',
    generated_at DATETIME(3) NULL COMMENT '文件生成时间',
    committed_at DATETIME(3) NULL COMMENT '库存正式扣减时间',
    reversed_at DATETIME(3) NULL COMMENT '冲销时间',
    reversed_by_id VARCHAR(64) NULL COMMENT '冲销人ID',
    reversed_by_name VARCHAR(100) NULL COMMENT '冲销人姓名快照',
    reversal_reason VARCHAR(1000) NULL COMMENT '冲销原因',
    result_payload JSON NULL COMMENT '生成结果快照',
    error_message TEXT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_refund_generation_task (api_task_id),
    UNIQUE KEY uk_refund_generation_idempotency (idempotency_key),
    KEY idx_refund_generation_status_time (generation_status, created_at),
    CONSTRAINT fk_refund_generation_task FOREIGN KEY (api_task_id) REFERENCES api_task (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='退税文件生成批次及库存扣减状态';

CREATE TABLE IF NOT EXISTS refund_inventory_allocation (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '库存分配流水主键',
    generation_id BIGINT NOT NULL COMMENT '退税生成批次ID',
    api_task_id BIGINT NOT NULL COMMENT '执行任务ID',
    entry_type VARCHAR(20) NOT NULL DEFAULT 'ALLOCATION' COMMENT 'ALLOCATION/REVERSAL',
    allocation_status VARCHAR(20) NOT NULL COMMENT 'RESERVED/COMMITTED/RELEASED',
    reversal_of_id BIGINT NULL COMMENT '冲销所对应的原分配流水ID',
    export_detail_id BIGINT NOT NULL COMMENT '出口明细ID',
    customs_declaration_no VARCHAR(30) NOT NULL COMMENT '报关单号快照',
    customs_item_no VARCHAR(10) NOT NULL COMMENT '报关项号快照',
    purchase_inventory_id BIGINT NOT NULL COMMENT '进货库存批次ID',
    invoice_no VARCHAR(50) NOT NULL COMMENT '发票号码快照',
    invoice_item_no INT NOT NULL COMMENT '发票商品行号快照',
    invoice_date DATE NOT NULL COMMENT '发票日期快照',
    supplier_tax_no VARCHAR(30) NOT NULL COMMENT '供货方税号快照',
    sku_original VARCHAR(200) NULL COMMENT '原始SKU快照',
    sku_normalized VARCHAR(200) NULL COMMENT '标准SKU快照',
    relation_no VARCHAR(40) NULL COMMENT '本次申报关联号',
    quantity_before DECIMAL(20,6) NOT NULL COMMENT '操作前可用或已分配数量',
    allocated_quantity DECIMAL(20,6) NOT NULL COMMENT '本次分配或冲销数量',
    quantity_after DECIMAL(20,6) NOT NULL COMMENT '操作后可用或已分配数量',
    operated_by_id VARCHAR(64) NOT NULL COMMENT 'ERP操作人ID',
    operated_by_name VARCHAR(100) NOT NULL COMMENT 'ERP操作人姓名快照',
    operated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_refund_allocation_generation (generation_id, allocation_status),
    KEY idx_refund_allocation_inventory (purchase_inventory_id, operated_at),
    KEY idx_refund_allocation_export (export_detail_id, operated_at),
    KEY idx_refund_allocation_invoice (invoice_no, invoice_item_no),
    KEY idx_refund_allocation_sku_time (sku_normalized, operated_at),
    CONSTRAINT fk_refund_allocation_generation FOREIGN KEY (generation_id) REFERENCES refund_generation (id),
    CONSTRAINT fk_refund_allocation_task FOREIGN KEY (api_task_id) REFERENCES api_task (id),
    CONSTRAINT fk_refund_allocation_export FOREIGN KEY (export_detail_id) REFERENCES export_detail (id),
    CONSTRAINT fk_refund_allocation_inventory FOREIGN KEY (purchase_inventory_id) REFERENCES purchase_inventory (id),
    CONSTRAINT fk_refund_allocation_reversal FOREIGN KEY (reversal_of_id) REFERENCES refund_inventory_allocation (id),
    CONSTRAINT chk_refund_allocation_quantity CHECK (allocated_quantity > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='退税库存分配及冲销审计流水，不允许物理删除';
