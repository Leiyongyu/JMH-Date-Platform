-- Amazon 最近90天 MSKU 利润率。
-- 可重复执行；先执行本脚本，再启动包含本次代码的后端。

CREATE TABLE IF NOT EXISTS `amz_order_profit_90d` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺ID',
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Seller SKU / MSKU',
  `gross_margin` decimal(10, 4) NULL DEFAULT NULL COMMENT '最近90天毛利率（接口原始小数）',
  `sync_time` datetime NULL DEFAULT NULL COMMENT '本地最近同步时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_amz_order_profit_90d_sid_sku` (`sid`, `seller_sku`),
  KEY `idx_amz_order_profit_90d_sync_time` (`sync_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Amazon最近90天订单利润表(MSKU维度)';

DROP PROCEDURE IF EXISTS add_amz_profit_90d_snapshot_column;
DELIMITER $$
CREATE PROCEDURE add_amz_profit_90d_snapshot_column()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'amz_replenishment_us_snapshot'
      AND COLUMN_NAME = 'profit_rate_90d'
  ) THEN
    ALTER TABLE `amz_replenishment_us_snapshot`
      ADD COLUMN `profit_rate_90d` decimal(10, 2) NULL DEFAULT NULL COMMENT '最近90天利润率(%)' AFTER `profit_rate_30d`;
  END IF;

  -- 两张快照仍需支持现有统一查询映射；欧洲组该列始终不写入、不展示、不导出。
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'amz_replenishment_eu_snapshot'
      AND COLUMN_NAME = 'profit_rate_90d'
  ) THEN
    ALTER TABLE `amz_replenishment_eu_snapshot`
      ADD COLUMN `profit_rate_90d` decimal(10, 2) NULL DEFAULT NULL COMMENT '保留兼容列（欧洲组不使用）' AFTER `profit_rate_30d`;
  END IF;
END$$
DELIMITER ;

CALL add_amz_profit_90d_snapshot_column();
DROP PROCEDURE IF EXISTS add_amz_profit_90d_snapshot_column;
