SET @schema_name := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_czech_warehouse_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_czech_warehouse_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-捷克仓'' AFTER remaining_stock',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_uk_warehouse_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_uk_warehouse_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-英国仓'' AFTER auto_czech_warehouse_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_us_warehouse_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_us_warehouse_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-美国谷仓'' AFTER auto_uk_warehouse_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_de_warehouse_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_de_warehouse_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-德国仓'' AFTER auto_us_warehouse_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_fba_de_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_de_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-FBA(DE)'' AFTER auto_de_warehouse_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_fba_uk_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_uk_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-FBA(UK)'' AFTER auto_fba_de_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_fba_us_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_us_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-FBA(US)'' AFTER auto_fba_uk_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_fba_fr_qty') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_fr_qty DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-FBA(FR)'' AFTER auto_fba_us_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@schema_name AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='auto_remaining_stock') = 0,
  'ALTER TABLE customs_inventory_list ADD COLUMN auto_remaining_stock DECIMAL(18,4) NULL COMMENT ''系统自动库存基准-剩余库存'' AFTER auto_fba_fr_qty',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE customs_inventory_list
SET auto_czech_warehouse_qty = COALESCE(auto_czech_warehouse_qty, czech_warehouse_qty),
    auto_uk_warehouse_qty = COALESCE(auto_uk_warehouse_qty, uk_warehouse_qty),
    auto_us_warehouse_qty = COALESCE(auto_us_warehouse_qty, us_warehouse_qty),
    auto_de_warehouse_qty = COALESCE(auto_de_warehouse_qty, de_warehouse_qty),
    auto_fba_de_qty = COALESCE(auto_fba_de_qty, fba_de_qty),
    auto_fba_uk_qty = COALESCE(auto_fba_uk_qty, fba_uk_qty),
    auto_fba_us_qty = COALESCE(auto_fba_us_qty, fba_us_qty),
    auto_fba_fr_qty = COALESCE(auto_fba_fr_qty, fba_fr_qty),
    auto_remaining_stock = COALESCE(auto_remaining_stock, remaining_stock);
