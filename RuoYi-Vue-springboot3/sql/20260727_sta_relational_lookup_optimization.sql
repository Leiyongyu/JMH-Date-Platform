-- STA任务关系化存储与按货件号查询优化。
-- 依赖：先执行 20260727_lingxing_sta_inbound_plan.sql。
-- 本脚本可重复执行，不删除旧字段或旧数据。
--
-- raw_json、query_shipment_id 仅保留为旧版本兼容字段；
-- 新版Java代码不再写入、读取或解析这些字段。

SET NAMES utf8mb4;

-- record_key是内部关系键：优先由货件号生成，不改变接口原始字段的空值。
SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan'
           AND column_name = 'record_key'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan`
     ADD COLUMN `record_key` varchar(255) DEFAULT NULL COMMENT ''内部关系键，优先使用货件号'' AFTER `id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `lingxing_sta_inbound_plan`
SET `record_key` = CASE
  WHEN `query_shipment_id` IS NOT NULL AND `query_shipment_id` <> ''
    THEN CONCAT('SHIPMENT:', `query_shipment_id`)
  WHEN `inbound_plan_id` IS NOT NULL AND `inbound_plan_id` <> ''
    THEN CONCAT('PLAN:', `inbound_plan_id`)
  ELSE CONCAT('LEGACY:', `id`)
END
WHERE `record_key` IS NULL OR `record_key` = '';

ALTER TABLE `lingxing_sta_inbound_plan`
  MODIFY COLUMN `record_key` varchar(255) NOT NULL COMMENT '内部关系键，优先使用货件号',
  MODIFY COLUMN `inbound_plan_id` varchar(128) NULL COMMENT '领星STA任务编号，接口为空时保持NULL';

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan'
           AND index_name = 'uk_lingxing_sta_record_key'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan`
     ADD UNIQUE KEY `uk_lingxing_sta_record_key` (`record_key`)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan_item'
           AND column_name = 'record_key'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan_item`
     ADD COLUMN `record_key` varchar(255) DEFAULT NULL COMMENT ''内部关系键'' AFTER `id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `lingxing_sta_inbound_plan_item` i
INNER JOIN `lingxing_sta_inbound_plan` p
  ON p.`inbound_plan_id` = i.`inbound_plan_id`
SET i.`record_key` = p.`record_key`
WHERE i.`record_key` IS NULL OR i.`record_key` = '';

UPDATE `lingxing_sta_inbound_plan_item`
SET `record_key` = CONCAT('LEGACY_ITEM:', `id`)
WHERE `record_key` IS NULL OR `record_key` = '';

ALTER TABLE `lingxing_sta_inbound_plan_item`
  MODIFY COLUMN `record_key` varchar(255) NOT NULL COMMENT '内部关系键',
  MODIFY COLUMN `inbound_plan_id` varchar(128) NULL COMMENT '领星STA任务编号';

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan_shipment'
           AND column_name = 'record_key'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan_shipment`
     ADD COLUMN `record_key` varchar(255) DEFAULT NULL COMMENT ''内部关系键'' AFTER `id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `lingxing_sta_inbound_plan_shipment` s
INNER JOIN `lingxing_sta_inbound_plan` p
  ON p.`inbound_plan_id` = s.`inbound_plan_id`
SET s.`record_key` = p.`record_key`
WHERE s.`record_key` IS NULL OR s.`record_key` = '';

UPDATE `lingxing_sta_inbound_plan_shipment`
SET `record_key` = CONCAT('LEGACY_SHIPMENT:', `id`)
WHERE `record_key` IS NULL OR `record_key` = '';

ALTER TABLE `lingxing_sta_inbound_plan_shipment`
  MODIFY COLUMN `record_key` varchar(255) NOT NULL COMMENT '内部关系键',
  MODIFY COLUMN `inbound_plan_id` varchar(128) NULL COMMENT '领星STA任务编号';

-- 同一FBA货件号只保留最新记录，之后由ON DUPLICATE KEY覆盖。
DELETE old_row
FROM `lingxing_sta_inbound_plan_shipment` old_row
INNER JOIN `lingxing_sta_inbound_plan_shipment` new_row
  ON old_row.`shipment_confirmation_id` = new_row.`shipment_confirmation_id`
 AND old_row.`id` < new_row.`id`
WHERE old_row.`shipment_confirmation_id` IS NOT NULL
  AND old_row.`shipment_confirmation_id` <> '';

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan_shipment'
           AND index_name = 'uk_lingxing_sta_confirmation_id'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan_shipment`
     ADD UNIQUE KEY `uk_lingxing_sta_confirmation_id` (`shipment_confirmation_id`)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 装箱导入只提交FBA货件号，使用该覆盖索引直接关联：
-- 货件号 -> 内部shipmentId + inboundPlanId -> sid + 商品MSKU。
SET @sql = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'lingxing_sta_inbound_plan_shipment'
      AND index_name = 'idx_lingxing_sta_confirmation_lookup'
  ),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan_shipment`
     ADD KEY `idx_lingxing_sta_confirmation_lookup`
       (`shipment_confirmation_id`, `inbound_plan_id`, `shipment_id`)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT
  s.`shipment_confirmation_id`,
  s.`shipment_id`,
  p.`inbound_plan_id`,
  p.`sid`,
  p.`gmt_modified`,
  s.`update_time`
FROM `lingxing_sta_inbound_plan_shipment` s
INNER JOIN `lingxing_sta_inbound_plan` p
  ON p.`record_key` = s.`record_key`
ORDER BY s.`update_time` DESC
LIMIT 20;
