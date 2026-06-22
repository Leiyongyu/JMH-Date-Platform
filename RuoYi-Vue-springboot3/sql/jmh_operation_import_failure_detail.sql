-- Operation import failure detail enhancement.
-- Adds a JSON field to operation_import_task for row-level import errors.

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

CALL jmh_add_column_if_missing(
    'operation_import_task',
    'fail_detail_json',
    "longtext NULL COMMENT '导入失败行明细JSON'"
);

DROP PROCEDURE IF EXISTS jmh_add_column_if_missing;
