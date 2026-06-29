-- 报关商品库：手动维护按 sku + 境内货源地 判断唯一。
-- 可重复执行；只调整索引与 source_location 空值默认，不删除业务数据。

UPDATE customs_products_list
SET source_location = ''
WHERE source_location IS NULL;

ALTER TABLE customs_products_list
    MODIFY source_location varchar(100) NOT NULL DEFAULT '';

DROP PROCEDURE IF EXISTS jmh_drop_index_if_exists;
DELIMITER //
CREATE PROCEDURE jmh_drop_index_if_exists(
    IN p_table varchar(64),
    IN p_index varchar(64)
)
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = p_table
          AND index_name = p_index
    ) THEN
        SET @sql := CONCAT('ALTER TABLE `', p_table, '` DROP INDEX `', p_index, '`');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

DROP PROCEDURE IF EXISTS jmh_add_unique_index_if_missing;
DELIMITER //
CREATE PROCEDURE jmh_add_unique_index_if_missing(
    IN p_table varchar(64),
    IN p_index varchar(64),
    IN p_columns varchar(255)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = p_table
          AND index_name = p_index
    ) THEN
        SET @sql := CONCAT('ALTER TABLE `', p_table, '` ADD UNIQUE KEY `', p_index, '` ', p_columns);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

CALL jmh_drop_index_if_exists('customs_products_list', 'sku');
CALL jmh_add_unique_index_if_missing('customs_products_list', 'uk_customs_products_sku_source', '(sku, source_location)');

DROP PROCEDURE IF EXISTS jmh_drop_index_if_exists;
DROP PROCEDURE IF EXISTS jmh_add_unique_index_if_missing;
