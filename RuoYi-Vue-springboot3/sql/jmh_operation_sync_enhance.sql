-- ============================================================
-- JMH 运营同步框架增强 SQL
-- 功能：增强 data_sync_log 表、注册若依定时任务分组字典
-- 执行前提：jmh_data_platform 数据库已存在 data_sync_log 表
-- 说明：可重复执行，已存在的列/索引会自动跳过
-- ============================================================

-- 1. 增强 data_sync_log 表 —— 使用存储过程安全新增字段
DROP PROCEDURE IF EXISTS jmh_add_column_if_missing;

DELIMITER //
CREATE PROCEDURE jmh_add_column_if_missing(
    IN tbl_name VARCHAR(128),
    IN col_name VARCHAR(128),
    IN col_def  TEXT
)
BEGIN
    DECLARE col_count INT DEFAULT 0;
    SELECT COUNT(*) INTO col_count
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = tbl_name
      AND COLUMN_NAME = col_name;
    IF col_count = 0 THEN
        SET @ddl = CONCAT('ALTER TABLE ', tbl_name, ' ADD COLUMN ', col_name, ' ', col_def);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- 执行新增字段
CALL jmh_add_column_if_missing('data_sync_log', 'api_path',    "varchar(300) DEFAULT '' COMMENT '调用的API路径'");
CALL jmh_add_column_if_missing('data_sync_log', 'job_id',      "bigint DEFAULT NULL COMMENT '若依sys_job.job_id'");
CALL jmh_add_column_if_missing('data_sync_log', 'job_log_id',  "bigint DEFAULT NULL COMMENT '若依sys_job_log.job_log_id'");
CALL jmh_add_column_if_missing('data_sync_log', 'detail_json', "longtext NULL COMMENT '完整执行详情JSON'");
CALL jmh_add_column_if_missing('data_sync_log', 'failed_json', "longtext NULL COMMENT '失败明细JSON'");

-- 清理存储过程
DROP PROCEDURE IF EXISTS jmh_add_column_if_missing;

-- 2. 添加索引（安全方式：先检查再创建）
DROP PROCEDURE IF EXISTS jmh_add_index_if_missing;

DELIMITER //
CREATE PROCEDURE jmh_add_index_if_missing(
    IN tbl_name VARCHAR(128),
    IN idx_name VARCHAR(128),
    IN idx_def  TEXT
)
BEGIN
    DECLARE idx_count INT DEFAULT 0;
    SELECT COUNT(*) INTO idx_count
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = tbl_name
      AND INDEX_NAME = idx_name;
    IF idx_count = 0 THEN
        SET @ddl = CONCAT('CREATE INDEX ', idx_name, ' ON ', tbl_name, ' ', idx_def);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

CALL jmh_add_index_if_missing('data_sync_log', 'idx_job_id',     '(job_id)');
CALL jmh_add_index_if_missing('data_sync_log', 'idx_job_log_id', '(job_log_id)');

DROP PROCEDURE IF EXISTS jmh_add_index_if_missing;

-- 3. 添加"运营同步"任务分组字典（若依 sys_dict_data）
INSERT IGNORE INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, remark)
VALUES (3, '运营同步', 'OPERATION', 'sys_job_group', '', '', 'N', '0', 'admin', NOW(), '运营数据同步任务分组');

-- 4. 使用说明
-- 定时任务通过 系统监控 > 定时任务 页面新增，调用目标字符串填写：
--   operationSyncTask.syncLingxingWarehouse()
--   operationSyncTask.syncLingxingInventory()
--   operationSyncTask.syncEbayListing()
--   operationSyncTask.syncAmzListing()
--   operationSyncTask.syncGoodcangWarehouse()
--   operationSyncTask.syncGoodcangGrn()
--   operationSyncTask.syncGoodcangProduct()
--   operationSyncTask.refreshEbayReplenishmentSnapshot()
--   operationSyncTask.refreshEbayPriceTrackingSnapshot()
--   operationSyncTask.refreshAmzReplenishmentSnapshot()
--
-- 任务组选择：OPERATION（运营同步）
