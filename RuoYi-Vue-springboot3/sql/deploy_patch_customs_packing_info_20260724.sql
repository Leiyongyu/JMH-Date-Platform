-- 装箱信息回传领星：复用发货单上传批次/日志表，增加业务类型标识。
-- 可重复执行；仅修改 Java ERP 数据库 jmh_data_platform。

USE `jmh_data_platform`;

SET @ddl := IF(
  EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customs_shipment_fee_import_batch'
      AND COLUMN_NAME = 'business_type'
  ),
  'SELECT ''customs_shipment_fee_import_batch.business_type already exists''',
  'ALTER TABLE `customs_shipment_fee_import_batch`
     ADD COLUMN `business_type` varchar(30) NOT NULL DEFAULT ''SHIPMENT_LOGISTICS''
       COMMENT ''SHIPMENT_LOGISTICS发货单物流/PACKING_INFO装箱信息''
       AFTER `id`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
  EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customs_shipment_fee_import_log'
      AND COLUMN_NAME = 'business_type'
  ),
  'SELECT ''customs_shipment_fee_import_log.business_type already exists''',
  'ALTER TABLE `customs_shipment_fee_import_log`
     ADD COLUMN `business_type` varchar(30) NOT NULL DEFAULT ''SHIPMENT_LOGISTICS''
       COMMENT ''SHIPMENT_LOGISTICS发货单物流/PACKING_INFO装箱信息''
       AFTER `batch_id`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
  EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customs_shipment_fee_import_batch'
      AND INDEX_NAME = 'idx_customs_shipment_fee_batch_business'
  ),
  'SELECT ''idx_customs_shipment_fee_batch_business already exists''',
  'CREATE INDEX `idx_customs_shipment_fee_batch_business`
     ON `customs_shipment_fee_import_batch` (`business_type`, `upload_time`)'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := IF(
  EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customs_shipment_fee_import_log'
      AND INDEX_NAME = 'idx_customs_shipment_fee_log_business'
  ),
  'SELECT ''idx_customs_shipment_fee_log_business already exists''',
  'CREATE INDEX `idx_customs_shipment_fee_log_business`
     ON `customs_shipment_fee_import_log` (`business_type`, `upload_time`)'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 兼容旧版本 order_sn(100)，装箱日志会写入“STA编号 / 店铺”。
SET @ddl := IF(
  EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customs_shipment_fee_import_log'
      AND COLUMN_NAME = 'order_sn'
      AND CHARACTER_MAXIMUM_LENGTH < 255
  ),
  'ALTER TABLE `customs_shipment_fee_import_log`
     MODIFY COLUMN `order_sn` varchar(255) DEFAULT NULL
       COMMENT ''业务单号；发货单号或STA编号/店铺''',
  'SELECT ''customs_shipment_fee_import_log.order_sn length is ready'''
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `customs_shipment_fee_import_batch`
SET `business_type` = 'SHIPMENT_LOGISTICS'
WHERE `business_type` IS NULL OR `business_type` = '';

UPDATE `customs_shipment_fee_import_log`
SET `business_type` = 'SHIPMENT_LOGISTICS'
WHERE `business_type` IS NULL OR `business_type` = '';

SELECT id, business_type, batch_no, status, upload_time
FROM customs_shipment_fee_import_batch
ORDER BY id DESC
LIMIT 10;
