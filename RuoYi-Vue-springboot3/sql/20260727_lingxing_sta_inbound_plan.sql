-- 领星STA任务及商品明细表。
-- 可重复执行，不清空已有数据。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `lingxing_sta_inbound_plan` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `inbound_plan_id` varchar(128) NOT NULL COMMENT '领星STA任务编号',
  `query_shipment_id` varchar(128) DEFAULT NULL COMMENT '本次精确查询使用的货件ID或货件单号',
  `sid` bigint DEFAULT NULL COMMENT '领星Amazon店铺SID',
  `plan_name` varchar(500) DEFAULT NULL COMMENT 'STA任务名称',
  `status` varchar(64) DEFAULT NULL COMMENT 'STA任务状态',
  `position_type` int DEFAULT NULL COMMENT '分仓方式：1先装箱再分仓，2先分仓再装箱',
  `gmt_create` datetime DEFAULT NULL COMMENT '领星创建时间',
  `gmt_modified` datetime DEFAULT NULL COMMENT '领星更新时间',
  `raw_json` longtext COMMENT 'STA任务原始JSON',
  `sync_time` datetime NOT NULL COMMENT '同步时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_sta_plan_id` (`inbound_plan_id`),
  KEY `idx_lingxing_sta_query_shipment` (`query_shipment_id`),
  KEY `idx_lingxing_sta_gmt_create` (`gmt_create`),
  KEY `idx_lingxing_sta_gmt_modified` (`gmt_modified`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星STA任务主表';

CREATE TABLE IF NOT EXISTS `lingxing_sta_inbound_plan_item` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `inbound_plan_id` varchar(128) NOT NULL COMMENT '领星STA任务编号',
  `item_index` int NOT NULL COMMENT '商品在接口数组中的序号',
  `asin` varchar(32) DEFAULT NULL,
  `fnsku` varchar(64) DEFAULT NULL,
  `msku` varchar(255) DEFAULT NULL,
  `parent_asin` varchar(32) DEFAULT NULL,
  `product_name` varchar(1000) DEFAULT NULL COMMENT '品名',
  `quantity` int DEFAULT NULL COMMENT '申报量',
  `sku` varchar(255) DEFAULT NULL,
  `title` varchar(2000) DEFAULT NULL COMMENT '标题',
  `url` varchar(2000) DEFAULT NULL COMMENT '图片URL',
  `raw_json` longtext COMMENT '商品原始JSON',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_sta_plan_item` (`inbound_plan_id`, `item_index`),
  KEY `idx_lingxing_sta_item_msku` (`msku`),
  KEY `idx_lingxing_sta_item_sku` (`sku`),
  KEY `idx_lingxing_sta_item_fnsku` (`fnsku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星STA任务商品明细表';

CREATE TABLE IF NOT EXISTS `lingxing_sta_inbound_plan_shipment` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `inbound_plan_id` varchar(128) NOT NULL COMMENT '领星STA任务编号',
  `shipment_index` int NOT NULL COMMENT '货件在接口数组中的序号',
  `shipment_id` varchar(128) DEFAULT NULL COMMENT '领星内部货件ID',
  `shipment_confirmation_id` varchar(128) DEFAULT NULL COMMENT 'FBA货件单号',
  `raw_json` longtext COMMENT '货件原始JSON',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_sta_plan_shipment` (`inbound_plan_id`, `shipment_index`),
  KEY `idx_lingxing_sta_shipment_id` (`shipment_id`),
  KEY `idx_lingxing_sta_confirmation_id` (`shipment_confirmation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星STA任务货件明细表';

-- 兼容已经执行过旧版本脚本的环境。
SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan'
           AND column_name = 'sid'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan` ADD COLUMN `sid` bigint DEFAULT NULL COMMENT ''领星Amazon店铺SID'' AFTER `query_shipment_id`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan'
           AND column_name = 'plan_name'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan` ADD COLUMN `plan_name` varchar(500) DEFAULT NULL COMMENT ''STA任务名称'' AFTER `sid`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan'
           AND column_name = 'status'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan` ADD COLUMN `status` varchar(64) DEFAULT NULL COMMENT ''STA任务状态'' AFTER `plan_name`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_schema = DATABASE()
           AND table_name = 'lingxing_sta_inbound_plan'
           AND column_name = 'position_type'),
  'DO 0',
  'ALTER TABLE `lingxing_sta_inbound_plan` ADD COLUMN `position_type` int DEFAULT NULL COMMENT ''分仓方式：1先装箱再分仓，2先分仓再装箱'' AFTER `status`'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 将旧版本已保存的原始JSON回填到新增字段，避免必须再次拉取后才能使用。
UPDATE `lingxing_sta_inbound_plan`
SET `sid` = COALESCE(
      `sid`, CAST(JSON_UNQUOTE(JSON_EXTRACT(`raw_json`, '$.sid')) AS UNSIGNED)),
    `plan_name` = COALESCE(
      `plan_name`, JSON_UNQUOTE(JSON_EXTRACT(`raw_json`, '$.planName'))),
    `status` = COALESCE(
      `status`, JSON_UNQUOTE(JSON_EXTRACT(`raw_json`, '$.status'))),
    `position_type` = COALESCE(
      `position_type`, CAST(JSON_UNQUOTE(
        COALESCE(JSON_EXTRACT(`raw_json`, '$.positionType'),
                 JSON_EXTRACT(`raw_json`, '$.position_type'))) AS SIGNED))
WHERE JSON_VALID(`raw_json`);

INSERT INTO `lingxing_sta_inbound_plan_shipment` (
  `inbound_plan_id`, `shipment_index`, `shipment_id`,
  `shipment_confirmation_id`, `raw_json`, `create_time`, `update_time`
)
SELECT
  p.`inbound_plan_id`,
  j.`shipment_index`,
  j.`shipment_id`,
  j.`shipment_confirmation_id`,
  j.`raw_json`,
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP
FROM `lingxing_sta_inbound_plan` p
JOIN JSON_TABLE(
  IF(JSON_VALID(p.`raw_json`), p.`raw_json`, JSON_OBJECT()),
  '$.shipmentList[*]' COLUMNS (
    `shipment_index` FOR ORDINALITY,
    `shipment_id` varchar(128) PATH '$.shipmentId',
    `shipment_confirmation_id` varchar(128) PATH '$.shipmentConfirmationId',
    `raw_json` json PATH '$'
  )
) j
ON TRUE
ON DUPLICATE KEY UPDATE
  `shipment_id` = VALUES(`shipment_id`),
  `shipment_confirmation_id` = VALUES(`shipment_confirmation_id`),
  `raw_json` = VALUES(`raw_json`),
  `update_time` = CURRENT_TIMESTAMP;
