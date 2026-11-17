-- AMZ补货新增FBA计划入库字段，并用其替代待出库参与补货抵扣。可重复执行。
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_product_performance_inventory'
     AND COLUMN_NAME = 'fba_inbound_working') = 0,
  'ALTER TABLE amz_product_performance_inventory ADD COLUMN fba_inbound_working INT NOT NULL DEFAULT 0 COMMENT ''FBA计划入库'' AFTER fba_inbound',
  'SELECT ''skip amz_product_performance_inventory.fba_inbound_working'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_replenishment_snapshot'
     AND COLUMN_NAME = 'fba_inbound_working') = 0,
  'ALTER TABLE amz_replenishment_snapshot ADD COLUMN fba_inbound_working INT NULL DEFAULT 0 COMMENT ''FBA计划入库'' AFTER fba_inbound',
  'SELECT ''skip amz_replenishment_snapshot.fba_inbound_working'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_replenishment_formula_config'
     AND COLUMN_NAME = 'deduct_fba_inbound_working') = 0,
  'ALTER TABLE amz_replenishment_formula_config ADD COLUMN deduct_fba_inbound_working TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''扣减FBA计划入库'' AFTER deduct_fba_inbound',
  'SELECT ''skip amz_replenishment_formula_config.deduct_fba_inbound_working'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE amz_replenishment_formula_config
SET deduct_pending_ship_qty = 0,
    deduct_fba_inbound_working = 1,
    formula_replenish = REPLACE(formula_replenish, '{locked}', '{inboundWorking}'),
    formula_restock = REPLACE(formula_restock, '{locked}', '{inboundWorking}')
WHERE region_group = 'EU';
