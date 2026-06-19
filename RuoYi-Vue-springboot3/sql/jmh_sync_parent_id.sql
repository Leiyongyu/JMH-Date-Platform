-- data_sync_log 增加 parent_id 字段，支持父子步骤日志
DROP PROCEDURE IF EXISTS jmh_add_parent_id;

DELIMITER //
CREATE PROCEDURE jmh_add_parent_id()
BEGIN
    DECLARE col_count INT DEFAULT 0;
    SELECT COUNT(*) INTO col_count FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_sync_log' AND COLUMN_NAME = 'parent_id';
    IF col_count = 0 THEN
        ALTER TABLE data_sync_log ADD COLUMN parent_id bigint DEFAULT NULL COMMENT '父日志ID，用于关联父子步骤';
        CREATE INDEX idx_parent_id ON data_sync_log(parent_id);
    END IF;
END //
DELIMITER ;

CALL jmh_add_parent_id();
DROP PROCEDURE IF EXISTS jmh_add_parent_id;
