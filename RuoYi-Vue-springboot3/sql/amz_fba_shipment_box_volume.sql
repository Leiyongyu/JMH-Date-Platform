SET @db_name = DATABASE();

SET @sql = IF(
    EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'amz_fba_shipment_box' AND COLUMN_NAME = 'box_volume'),
    'SELECT 1',
    'ALTER TABLE amz_fba_shipment_box ADD COLUMN box_volume VARCHAR(20) NULL COMMENT ''箱子体积m3'' AFTER box_weight'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
