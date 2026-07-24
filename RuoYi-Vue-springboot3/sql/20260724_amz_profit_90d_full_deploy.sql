-- =====================================================================
-- AMZ 最近90天利润率完整部署脚本
-- 包含：
--   1. amz_order_profit_90d 最近90天利润率表
--   2. amz_replenishment_us_snapshot 美国组快照表
--   3. amz_replenishment_eu_snapshot 欧洲组快照表
--   4. 两张快照表的 profit_rate_90d 兼容字段
--   5. AMZ补货链路定时任务（每天01:00）
--
-- 特点：
--   * 可重复执行。
--   * 不依赖旧表 amz_replenishment_snapshot，避免 1146 错误。
--   * 90天利润同步由 operationSyncTask.runAmzChain() 链路执行，
--     顺序为：刊登 → 30天利润 → 90天利润 → 补货/库存 → 快照。
-- =====================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- 1. 最近90天利润率表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `amz_order_profit_90d` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺ID',
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Seller SKU / MSKU',
  `gross_margin` decimal(10, 4) NULL DEFAULT NULL COMMENT '最近90天毛利率（领星接口原始小数）',
  `sync_time` datetime NULL DEFAULT NULL COMMENT '本地最近同步时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_amz_order_profit_90d_sid_sku` (`sid`, `seller_sku`),
  KEY `idx_amz_order_profit_90d_sync_time` (`sync_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon最近90天订单利润表(MSKU维度)';

-- ---------------------------------------------------------------------
-- 2. 自包含快照模板
-- 不使用 CREATE TABLE ... LIKE amz_replenishment_snapshot，
-- 因此部署库没有旧快照表时也能执行。
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS `_amz_replenishment_snapshot_template_20260724`;
CREATE TABLE `_amz_replenishment_snapshot_template_20260724` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NULL DEFAULT NULL,
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `warehouse_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `warehouse_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `asin` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `price` decimal(10, 2) NULL DEFAULT NULL COMMENT '价格',
  `tag_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '标签名称',
  `principal_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `store_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `product_category` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `product_nature` tinyint NULL DEFAULT 1 COMMENT '产品性质：1老品，2新品',
  `rating` decimal(3, 1) NULL DEFAULT NULL,
  `review_count` int NULL DEFAULT 0,
  `ad_rate` decimal(10, 4) NULL DEFAULT NULL,
  `profit_rate_30d` decimal(10, 4) NULL DEFAULT NULL,
  `profit_rate_90d` decimal(10, 2) NULL DEFAULT NULL COMMENT '最近90天利润率(%)',
  `refund_rate_90d` decimal(10, 4) NULL DEFAULT NULL,
  `tacos` decimal(10, 2) NULL DEFAULT NULL COMMENT 'TACOS广告费占比',
  `purchased_qty` int NULL DEFAULT 0,
  `domestic_stock` int NULL DEFAULT 0,
  `pending_ship_qty` int NULL DEFAULT 0,
  `product_qc_num` int NULL DEFAULT 0 COMMENT '待检待上架量',
  `fba_stock` int NULL DEFAULT 0,
  `fba_inbound` int NULL DEFAULT 0,
  `fba_inbound_working` int NULL DEFAULT 0 COMMENT 'FBA计划入库',
  `fba_reserved` int NULL DEFAULT 0 COMMENT 'FBA预留',
  `total_inventory` int NULL DEFAULT 0,
  `sales_7d` int NULL DEFAULT 0,
  `sales_14d` int NULL DEFAULT 0,
  `sales_30d` int NULL DEFAULT 0,
  `sales_60d` int NULL DEFAULT 0,
  `sales_speed_14d` decimal(10, 2) NULL DEFAULT NULL,
  `sales_speed_30d` decimal(10, 2) NULL DEFAULT NULL,
  `sales_speed_60d` decimal(10, 2) NULL DEFAULT NULL,
  `avg_monthly_sales` decimal(10, 2) NULL DEFAULT NULL,
  `safety_stock` decimal(10, 2) NULL DEFAULT NULL,
  `ship_qty` decimal(10, 2) NULL DEFAULT NULL,
  `replenish_qty` decimal(10, 2) NULL DEFAULT NULL,
  `restock_days` decimal(10, 2) NULL DEFAULT NULL,
  `shortage_qty` int NULL DEFAULT 0 COMMENT '缺货量=安全库存-FBA总库存',
  `region_group` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '区域组 US/EU',
  `fba_shipment_id` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'FBA货件单号(多个逗号分隔)',
  `fba_quantity_shipped` int NULL DEFAULT 0 COMMENT 'FBA申报量合计',
  `fba_quantity_received` int NULL DEFAULT 0 COMMENT 'FBA签收量合计',
  `fba_declared_diff` int NULL DEFAULT 0 COMMENT 'FBA申报差异合计',
  `fba_shipment_create_time` datetime NULL DEFAULT NULL COMMENT 'FBA最新货件创建时间',
  `source_overview_id` bigint NULL DEFAULT NULL,
  `calc_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `batch_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `current_flag` tinyint NOT NULL DEFAULT 1,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品缩略图',
  PRIMARY KEY (`id`),
  KEY `idx_sid_seller_sku` (`sid`, `seller_sku`),
  KEY `idx_warehouse_sku` (`warehouse_sku`),
  KEY `idx_asin` (`asin`),
  KEY `idx_store_name` (`store_name`),
  KEY `idx_amz_principal` (`principal_name`),
  KEY `idx_amz_category` (`product_category`),
  KEY `idx_ars_current` (`current_flag`),
  KEY `idx_ars_batch` (`batch_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon补货计算快照模板';

-- ---------------------------------------------------------------------
-- 3. 美国组、欧洲组独立快照表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `amz_replenishment_us_snapshot`
  LIKE `_amz_replenishment_snapshot_template_20260724`;

CREATE TABLE IF NOT EXISTS `amz_replenishment_eu_snapshot`
  LIKE `_amz_replenishment_snapshot_template_20260724`;

ALTER TABLE `amz_replenishment_us_snapshot`
  COMMENT='Amazon美国组补货计算快照';

ALTER TABLE `amz_replenishment_eu_snapshot`
  COMMENT='Amazon欧洲组补货计算快照';

DROP TABLE IF EXISTS `_amz_replenishment_snapshot_template_20260724`;

-- ---------------------------------------------------------------------
-- 4. 兼容已存在的旧US/EU快照表：缺少字段时再补字段
-- 此时两张快照表已由上一步保证存在，不会再出现1146。
-- 欧洲组保留同名兼容列，但不写入、不在前端显示、不在导出中使用。
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS `patch_amz_profit_90d_snapshot_columns`;
DELIMITER $$
CREATE PROCEDURE `patch_amz_profit_90d_snapshot_columns`()
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'amz_replenishment_us_snapshot'
      AND COLUMN_NAME = 'profit_rate_90d'
  ) THEN
    ALTER TABLE `amz_replenishment_us_snapshot`
      ADD COLUMN `profit_rate_90d` decimal(10, 2) NULL DEFAULT NULL
      COMMENT '最近90天利润率(%)'
      AFTER `profit_rate_30d`;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'amz_replenishment_eu_snapshot'
      AND COLUMN_NAME = 'profit_rate_90d'
  ) THEN
    ALTER TABLE `amz_replenishment_eu_snapshot`
      ADD COLUMN `profit_rate_90d` decimal(10, 2) NULL DEFAULT NULL
      COMMENT '兼容字段（欧洲组不使用）'
      AFTER `profit_rate_30d`;
  END IF;
END$$
DELIMITER ;

CALL `patch_amz_profit_90d_snapshot_columns`();
DROP PROCEDURE IF EXISTS `patch_amz_profit_90d_snapshot_columns`;

-- ---------------------------------------------------------------------
-- 5. AMZ补货链路定时任务
-- 若已有任务则更新为标准调用格式并启用；没有则新增。
-- 90天利润同步已经在 runAmzChain() 的快照刷新步骤之前。
-- ---------------------------------------------------------------------
UPDATE `sys_job`
SET `job_name` = 'AMZ补货链路同步',
    `job_group` = 'OPERATION',
    `invoke_target` = 'operationSyncTask.runAmzChain()',
    `cron_expression` = '0 0 1 * * ?',
    `misfire_policy` = '1',
    `concurrent` = '1',
    `status` = '0',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = '每天01:00 刊登→30天利润→90天利润→补货建议→库存→美国/欧洲快照'
WHERE `invoke_target` IN (
  'operationSyncTask.runAmzChain',
  'operationSyncTask.runAmzChain()'
);

-- 清理同一调用目标的历史重复任务，只保留 job_id 最小的一条，防止每天重复执行链路。
DELETE duplicate_job
FROM `sys_job` duplicate_job
INNER JOIN `sys_job` keeper_job
  ON duplicate_job.`invoke_target` = keeper_job.`invoke_target`
 AND duplicate_job.`job_id` > keeper_job.`job_id`
WHERE duplicate_job.`invoke_target` = 'operationSyncTask.runAmzChain()';

INSERT INTO `sys_job` (
  `job_name`, `job_group`, `invoke_target`, `cron_expression`,
  `misfire_policy`, `concurrent`, `status`,
  `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
  'AMZ补货链路同步',
  'OPERATION',
  'operationSyncTask.runAmzChain()',
  '0 0 1 * * ?',
  '1',
  '1',
  '0',
  'SYSTEM',
  NOW(),
  'SYSTEM',
  NOW(),
  '每天01:00 刊登→30天利润→90天利润→补货建议→库存→美国/欧洲快照'
WHERE NOT EXISTS (
  SELECT 1
  FROM `sys_job`
  WHERE `invoke_target` IN (
    'operationSyncTask.runAmzChain',
    'operationSyncTask.runAmzChain()'
  )
);

-- ---------------------------------------------------------------------
-- 6. 执行结果核对
-- ---------------------------------------------------------------------
SELECT
  TABLE_NAME,
  TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'amz_order_profit_90d',
    'amz_replenishment_us_snapshot',
    'amz_replenishment_eu_snapshot'
  )
ORDER BY TABLE_NAME;

SELECT
  TABLE_NAME,
  COLUMN_NAME,
  COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'amz_replenishment_us_snapshot',
    'amz_replenishment_eu_snapshot'
  )
  AND COLUMN_NAME = 'profit_rate_90d'
ORDER BY TABLE_NAME;

SELECT
  job_id,
  job_name,
  invoke_target,
  cron_expression,
  status,
  remark
FROM `sys_job`
WHERE `invoke_target` IN (
  'operationSyncTask.runAmzChain',
  'operationSyncTask.runAmzChain()'
);
