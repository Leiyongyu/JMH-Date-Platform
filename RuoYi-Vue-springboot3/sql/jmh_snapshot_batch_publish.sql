-- Snapshot batch publish support.
-- Run this before deploying the optimized snapshot refresh code.

DROP PROCEDURE IF EXISTS jmh_add_column_if_missing;
DELIMITER $$
CREATE PROCEDURE jmh_add_column_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_column_name VARCHAR(64),
    IN p_column_def TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND COLUMN_NAME = p_column_name
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table_name, '` ADD COLUMN `', p_column_name, '` ', p_column_def);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS jmh_add_index_if_missing;
DELIMITER $$
CREATE PROCEDURE jmh_add_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_index_def TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND INDEX_NAME = p_index_name
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table_name, '` ADD INDEX `', p_index_name, '` ', p_index_def);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS jmh_drop_index_if_exists;
DELIMITER $$
CREATE PROCEDURE jmh_drop_index_if_exists(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64)
)
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND INDEX_NAME = p_index_name
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table_name, '` DROP INDEX `', p_index_name, '`');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS jmh_add_unique_index_if_missing;
DELIMITER $$
CREATE PROCEDURE jmh_add_unique_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_index_def TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND INDEX_NAME = p_index_name
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table_name, '` ADD UNIQUE INDEX `', p_index_name, '` ', p_index_def);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL jmh_add_column_if_missing('ebay_replenishment_snapshot', 'batch_no', 'VARCHAR(64) NULL');
CALL jmh_add_column_if_missing('ebay_replenishment_snapshot', 'current_flag', 'TINYINT NOT NULL DEFAULT 1');
CALL jmh_add_column_if_missing('ebay_price_tracking_snapshot', 'batch_no', 'VARCHAR(64) NULL');
CALL jmh_add_column_if_missing('ebay_price_tracking_snapshot', 'current_flag', 'TINYINT NOT NULL DEFAULT 1');
CALL jmh_add_column_if_missing('amz_replenishment_snapshot', 'batch_no', 'VARCHAR(64) NULL');
CALL jmh_add_column_if_missing('amz_replenishment_snapshot', 'current_flag', 'TINYINT NOT NULL DEFAULT 1');

UPDATE ebay_replenishment_snapshot
SET batch_no = 'legacy', current_flag = 1
WHERE batch_no IS NULL OR batch_no = '' OR current_flag IS NULL;

UPDATE ebay_price_tracking_snapshot
SET batch_no = 'legacy', current_flag = 1
WHERE batch_no IS NULL OR batch_no = '' OR current_flag IS NULL;

UPDATE amz_replenishment_snapshot
SET batch_no = 'legacy', current_flag = 1
WHERE batch_no IS NULL OR batch_no = '' OR current_flag IS NULL;

CALL jmh_add_index_if_missing('ebay_replenishment_snapshot', 'idx_ers_current', '(current_flag)');
CALL jmh_add_index_if_missing('ebay_replenishment_snapshot', 'idx_ers_batch', '(batch_no)');
CALL jmh_add_index_if_missing('ebay_price_tracking_snapshot', 'idx_epts_current', '(current_flag)');
CALL jmh_add_index_if_missing('ebay_price_tracking_snapshot', 'idx_epts_batch', '(batch_no)');
CALL jmh_add_index_if_missing('amz_replenishment_snapshot', 'idx_ars_current', '(current_flag)');
CALL jmh_add_index_if_missing('amz_replenishment_snapshot', 'idx_ars_batch', '(batch_no)');

CALL jmh_drop_index_if_exists('ebay_replenishment_snapshot', 'uk_site_sku');
CALL jmh_drop_index_if_exists('ebay_price_tracking_snapshot', 'uk_site_sku');
CALL jmh_add_unique_index_if_missing('ebay_replenishment_snapshot', 'uk_batch_site_sku', '(batch_no, site, sku)');
CALL jmh_add_unique_index_if_missing('ebay_price_tracking_snapshot', 'uk_batch_site_sku', '(batch_no, site, sku)');

DROP PROCEDURE IF EXISTS jmh_add_column_if_missing;
DROP PROCEDURE IF EXISTS jmh_add_index_if_missing;
DROP PROCEDURE IF EXISTS jmh_drop_index_if_exists;
DROP PROCEDURE IF EXISTS jmh_add_unique_index_if_missing;
