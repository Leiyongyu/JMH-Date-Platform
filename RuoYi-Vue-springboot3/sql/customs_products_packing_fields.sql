SET @db_name = DATABASE();

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'packing_net_weight'),
    'SELECT 1',
    'ALTER TABLE customs_products_list ADD COLUMN packing_net_weight DECIMAL(12,4) NULL COMMENT ''装箱单净重kg'' AFTER single_weight'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'packing_gross_weight'),
    'SELECT 1',
    'ALTER TABLE customs_products_list ADD COLUMN packing_gross_weight DECIMAL(12,4) NULL COMMENT ''装箱单毛重kg'' AFTER packing_net_weight'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'packing_cbm'),
    'SELECT 1',
    'ALTER TABLE customs_products_list ADD COLUMN packing_cbm DECIMAL(12,6) NULL COMMENT ''装箱单体积CBM'' AFTER packing_gross_weight'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'box_length'),
    'SELECT 1',
    'ALTER TABLE customs_products_list ADD COLUMN box_length DECIMAL(12,4) NULL COMMENT ''箱长cm'' AFTER packing_cbm'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'box_width'),
    'SELECT 1',
    'ALTER TABLE customs_products_list ADD COLUMN box_width DECIMAL(12,4) NULL COMMENT ''箱宽cm'' AFTER box_length'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'box_height'),
    'SELECT 1',
    'ALTER TABLE customs_products_list ADD COLUMN box_height DECIMAL(12,4) NULL COMMENT ''箱高cm'' AFTER box_width'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
