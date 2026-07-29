-- 领星FBA货件单号与发货单号映射。
-- 执行后，STA发货链路的第一步会同步货件号与发货单号：
-- 1. 表为空时，读取 amz_fba_shipment.shipment_id，每20个货件一组全量查询；
-- 2. 表不为空时，使用 time_type=2 拉取最近3个自然日创建的发货单；
-- 3. 两种模式都按 shipment_id 唯一键增量覆盖。
-- 可重复执行，不清空历史映射。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `lingxing_shipment_order_mapping` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `shipment_id` varchar(128) NOT NULL COMMENT 'FBA货件单号',
  `shipment_sn` varchar(128) NOT NULL COMMENT '领星发货单号',
  `shipment_list_id` bigint DEFAULT NULL COMMENT '领星发货单列表记录ID',
  `sid` bigint DEFAULT NULL COMMENT '领星Amazon店铺SID',
  `store_name` varchar(500) DEFAULT NULL COMMENT '领星店铺名称',
  `order_status` int DEFAULT NULL COMMENT '发货单状态',
  `shipment_status` varchar(64) DEFAULT NULL COMMENT '关联货件状态',
  `is_delete` tinyint NOT NULL DEFAULT 0 COMMENT '发货单是否删除：0否1是',
  `remote_create_time` datetime DEFAULT NULL COMMENT '领星发货单创建时间',
  `remote_update_time` datetime DEFAULT NULL COMMENT '领星发货单更新时间',
  `sync_time` datetime NOT NULL COMMENT '最近同步时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
      ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_shipment_order_shipment_id` (`shipment_id`),
  KEY `idx_lingxing_shipment_order_shipment_sn` (`shipment_sn`),
  KEY `idx_lingxing_shipment_order_sid` (`sid`),
  KEY `idx_lingxing_shipment_order_sync_time` (`sync_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星FBA货件单号与发货单号映射';

-- 兼容已提前创建且 shipment_status 为 int 的本地/部署表。
SET @sql = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'lingxing_shipment_order_mapping'
      AND column_name = 'shipment_status'
      AND data_type <> 'varchar'
  ),
  'ALTER TABLE `lingxing_shipment_order_mapping`
     MODIFY COLUMN `shipment_status` varchar(64) DEFAULT NULL
       COMMENT ''关联货件状态''',
  'DO 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 上传日志同时记录Excel货件单号和解析后的领星发货单号。
SET @sql = IF(
  EXISTS(
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'customs_shipment_fee_import_log'
  )
  AND NOT EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'customs_shipment_fee_import_log'
      AND column_name = 'shipment_id'
  ),
  'ALTER TABLE `customs_shipment_fee_import_log`
     ADD COLUMN `shipment_id` varchar(128) DEFAULT NULL
       COMMENT ''Excel来源货件单号'' AFTER `business_type`,
     ADD KEY `idx_shipment_fee_log_shipment_id` (`shipment_id`)',
  'DO 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 更新现有STA任务说明；执行时间仍为每天03:00。
UPDATE `sys_job`
SET `remark` =
    'STA发货链路：货件与发货单映射（空表全量/非空最近3天）→STA任务列表；每天03:00执行',
    `update_by` = 'SYSTEM',
    `update_time` = CURRENT_TIMESTAMP
WHERE `invoke_target` IN (
  'operationSyncTask.runStaShipmentChain',
  'operationSyncTask.runStaShipmentChain()',
  'chainSyncTask.runStaShipmentChain',
  'chainSyncTask.runStaShipmentChain()'
);

-- 部署后验证：
-- SELECT COUNT(*) AS mapping_count FROM lingxing_shipment_order_mapping;
-- SELECT shipment_id, shipment_sn, sync_time
-- FROM lingxing_shipment_order_mapping ORDER BY update_time DESC LIMIT 20;
