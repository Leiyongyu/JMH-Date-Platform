-- AMZ补货公式配置：策略配置器字段。可重复执行。
SET @table_name := 'amz_replenishment_formula_config';

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'strategy_type');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN strategy_type varchar(50) NOT NULL DEFAULT ''CUSTOM'' COMMENT ''策略类型'' AFTER marketplaces', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'deduct_fba_stock');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN deduct_fba_stock tinyint(1) NOT NULL DEFAULT 1 COMMENT ''扣减FBA在库'' AFTER replenish_days', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'deduct_fba_inbound');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN deduct_fba_inbound tinyint(1) NOT NULL DEFAULT 1 COMMENT ''扣减FBA在途'' AFTER deduct_fba_stock', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'deduct_domestic_stock');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN deduct_domestic_stock tinyint(1) NOT NULL DEFAULT 1 COMMENT ''扣减国内仓库存'' AFTER deduct_fba_inbound', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'deduct_purchased_qty');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN deduct_purchased_qty tinyint(1) NOT NULL DEFAULT 1 COMMENT ''扣减已采购数量'' AFTER deduct_domestic_stock', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'deduct_pending_ship_qty');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN deduct_pending_ship_qty tinyint(1) NOT NULL DEFAULT 1 COMMENT ''扣减待出库数量'' AFTER deduct_purchased_qty', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'allow_negative_replenish');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN allow_negative_replenish tinyint(1) NOT NULL DEFAULT 1 COMMENT ''允许负数补货量'' AFTER deduct_pending_ship_qty', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'min_replenish_qty');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN min_replenish_qty decimal(18,2) NULL DEFAULT NULL COMMENT ''最小补货量'' AFTER allow_negative_replenish', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'max_replenish_qty');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN max_replenish_qty decimal(18,2) NULL DEFAULT NULL COMMENT ''最大补货量'' AFTER min_replenish_qty', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_col := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = @table_name AND column_name = 'round_mode');
SET @sql := IF(@has_col = 0, 'ALTER TABLE amz_replenishment_formula_config ADD COLUMN round_mode varchar(30) NOT NULL DEFAULT ''NONE'' COMMENT ''取整方式'' AFTER max_replenish_qty', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
