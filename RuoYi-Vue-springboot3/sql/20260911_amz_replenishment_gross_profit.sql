-- AMZ补货：30天、90天毛利润（人民币）。2026-09-11
-- 前置：4张现有业务表已部署。本脚本不创建空替代表，表不存在将明确报错。
-- 仅新增6个可空列；不更新/删除记录，不改现有利润率。MySQL DDL会隐式提交。
-- 执行前备份并选择低峰期；先执行本脚本，再部署Java与前端。
-- 可重复执行，已存在的列不修改；原行新增值为NULL，禁止填0冒充已同步。
SET NAMES utf8mb4;
USE `jmh_data_platform`;

SET @amz_gross_profit_ddl = IF(
    EXISTS(SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_order_profit' AND COLUMN_NAME = 'gross_profit'),
    'SELECT ''amz_order_profit.gross_profit already exists'' AS migration_status',
    'ALTER TABLE `amz_order_profit` ADD COLUMN `gross_profit` DECIMAL(20,6) NULL DEFAULT NULL COMMENT ''领星gross_profit毛利润CNY原值'''
);
PREPARE amz_gross_profit_stmt FROM @amz_gross_profit_ddl;
EXECUTE amz_gross_profit_stmt;
DEALLOCATE PREPARE amz_gross_profit_stmt;

SET @amz_gross_profit_ddl = IF(
    EXISTS(SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_order_profit_90d' AND COLUMN_NAME = 'gross_profit'),
    'SELECT ''amz_order_profit_90d.gross_profit already exists'' AS migration_status',
    'ALTER TABLE `amz_order_profit_90d` ADD COLUMN `gross_profit` DECIMAL(20,6) NULL DEFAULT NULL COMMENT ''领星gross_profit毛利润CNY原值'''
);
PREPARE amz_gross_profit_stmt FROM @amz_gross_profit_ddl;
EXECUTE amz_gross_profit_stmt;
DEALLOCATE PREPARE amz_gross_profit_stmt;

SET @amz_gross_profit_ddl = IF(
    EXISTS(SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_replenishment_us_snapshot' AND COLUMN_NAME = 'gross_profit_30d'),
    'SELECT ''amz_replenishment_us_snapshot.gross_profit_30d already exists'' AS migration_status',
    'ALTER TABLE `amz_replenishment_us_snapshot` ADD COLUMN `gross_profit_30d` DECIMAL(20,6) NULL DEFAULT NULL COMMENT ''30天毛利润人民币元沿用原30天窗口'''
);
PREPARE amz_gross_profit_stmt FROM @amz_gross_profit_ddl;
EXECUTE amz_gross_profit_stmt;
DEALLOCATE PREPARE amz_gross_profit_stmt;

SET @amz_gross_profit_ddl = IF(
    EXISTS(SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_replenishment_us_snapshot' AND COLUMN_NAME = 'gross_profit_90d'),
    'SELECT ''amz_replenishment_us_snapshot.gross_profit_90d already exists'' AS migration_status',
    'ALTER TABLE `amz_replenishment_us_snapshot` ADD COLUMN `gross_profit_90d` DECIMAL(20,6) NULL DEFAULT NULL COMMENT ''90天毛利润人民币元'''
);
PREPARE amz_gross_profit_stmt FROM @amz_gross_profit_ddl;
EXECUTE amz_gross_profit_stmt;
DEALLOCATE PREPARE amz_gross_profit_stmt;

SET @amz_gross_profit_ddl = IF(
    EXISTS(SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_replenishment_eu_snapshot' AND COLUMN_NAME = 'gross_profit_30d'),
    'SELECT ''amz_replenishment_eu_snapshot.gross_profit_30d already exists'' AS migration_status',
    'ALTER TABLE `amz_replenishment_eu_snapshot` ADD COLUMN `gross_profit_30d` DECIMAL(20,6) NULL DEFAULT NULL COMMENT ''30天毛利润人民币元沿用原30天窗口'''
);
PREPARE amz_gross_profit_stmt FROM @amz_gross_profit_ddl;
EXECUTE amz_gross_profit_stmt;
DEALLOCATE PREPARE amz_gross_profit_stmt;

SET @amz_gross_profit_ddl = IF(
    EXISTS(SELECT 1 FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_replenishment_eu_snapshot' AND COLUMN_NAME = 'gross_profit_90d'),
    'SELECT ''amz_replenishment_eu_snapshot.gross_profit_90d already exists'' AS migration_status',
    'ALTER TABLE `amz_replenishment_eu_snapshot` ADD COLUMN `gross_profit_90d` DECIMAL(20,6) NULL DEFAULT NULL COMMENT ''90天毛利润人民币元'''
);
PREPARE amz_gross_profit_stmt FROM @amz_gross_profit_ddl;
EXECUTE amz_gross_profit_stmt;
DEALLOCATE PREPARE amz_gross_profit_stmt;

-- 应返回6行，均DECIMAL(20,6)、可空。此处仅验证列结构，不触发数据拉取。
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND ((TABLE_NAME IN ('amz_order_profit','amz_order_profit_90d') AND COLUMN_NAME='gross_profit')
    OR (TABLE_NAME IN ('amz_replenishment_us_snapshot','amz_replenishment_eu_snapshot')
        AND COLUMN_NAME IN ('gross_profit_30d','gross_profit_90d')))
ORDER BY TABLE_NAME, COLUMN_NAME;
