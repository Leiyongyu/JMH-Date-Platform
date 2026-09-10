-- 周报仓位业务键升级。仅操作 date-project 的仓位ODS结构，不删改原始记录。
-- 已建表环境执行本脚本；首次部署先02/04，再执行10和11。schema.sql已含新结构。
-- 先备份表/结构并暂停周报任务。DDL会隐式提交和等待元数据锁，不能靠ROLLBACK撤回。
-- 使用支持DELIMITER的MySQL客户端执行；需要CREATE/ALTER/INDEX及临时过程权限。
USE `date-project`;
DELIMITER $$
DROP PROCEDURE IF EXISTS `migrate_weekly_bin_identity_20260910`$$
CREATE PROCEDURE `migrate_weekly_bin_identity_20260910`()
BEGIN
    DECLARE v_lock INT DEFAULT 0;
    DECLARE v_old_wait BIGINT DEFAULT 31536000;
    DECLARE v_exists INT DEFAULT 0;
    DECLARE v_valid INT DEFAULT 0;
    DECLARE v_index TEXT;
    DECLARE v_non_unique INT;
    DECLARE v_prefix_parts INT;
    DECLARE v_before BIGINT;
    DECLARE v_after BIGINT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET SESSION lock_wait_timeout = v_old_wait;
        IF v_lock = 1 THEN DO RELEASE_LOCK('inventory:weekly-export'); END IF;
        RESIGNAL;
    END;

    SET v_old_wait = @@SESSION.lock_wait_timeout;
    SET SESSION lock_wait_timeout = 15;
    -- 与周报调度使用同一把锁，正在拉取/写入时拒绝升级，不干扰运行中的任务。
    SELECT GET_LOCK('inventory:weekly-export',15) INTO v_lock;
    IF v_lock IS NULL OR v_lock <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Cannot acquire weekly bin migration lock';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM information_schema.TABLES
                  WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Weekly bin table missing; run 02 first';
    END IF;

    SELECT COUNT(*) INTO v_before FROM ods_lingxing_inventory_bin_detail_weekly;
    SELECT COUNT(*),COALESCE(SUM(COLUMN_TYPE='varbinary(1600)' AND EXTRA LIKE '%STORED GENERATED%'
            AND COLUMN_COMMENT='weekly-bin-identity-v1: store_id,msku,fnsku; byte-exact length framing'),0)
      INTO v_exists,v_valid FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly'
        AND COLUMN_NAME='bin_identity_key';
    IF v_exists > 0 AND v_valid <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unexpected existing bin_identity_key; inspect, do not overwrite';
    END IF;

    SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX),MAX(NON_UNIQUE),SUM(SUB_PART IS NOT NULL)
      INTO v_index,v_non_unique,v_prefix_parts FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly'
        AND INDEX_NAME='uk_bin_week';
    IF v_index IS NOT NULL AND
       (v_index NOT IN ('snapshot_date,wid,whb_id,product_id',
                       'snapshot_date,sync_batch_id,wid,whb_id,product_id',
                       'snapshot_date,sync_batch_id,wid,whb_id,product_id,bin_identity_key')
        OR v_non_unique <> 0 OR v_prefix_parts <> 0) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unexpected uk_bin_week definition; inspect before migration';
    END IF;

    IF v_exists = 0 OR v_index IS NULL OR
       v_index <> 'snapshot_date,sync_batch_id,wid,whb_id,product_id,bin_identity_key' THEN
        -- One ALTER adds the generated column (when missing) and swaps only the index.
        -- A duplicate full business key causes ALTER to fail; never delete/merge source rows.
        SET @weekly_bin_ddl = CONCAT(
            'ALTER TABLE `ods_lingxing_inventory_bin_detail_weekly` ',
            IF(v_exists=0,'ADD COLUMN `bin_identity_key` VARBINARY(1600) GENERATED ALWAYS AS (CONCAT(CHAR_LENGTH(COALESCE(NULLIF(TRIM(`store_id`),''''),''0'')),'':'',COALESCE(NULLIF(TRIM(`store_id`),''''),''0''),CHAR_LENGTH(COALESCE(`msku`,'''')),'':'',COALESCE(`msku`,''''),CHAR_LENGTH(COALESCE(`fnsku`,'''')),'':'',COALESCE(`fnsku`,''''))) STORED COMMENT ''weekly-bin-identity-v1: store_id,msku,fnsku; byte-exact length framing'', ',''),
            IF(v_index IS NOT NULL,'DROP INDEX `uk_bin_week`, ',''),
            'ADD UNIQUE KEY `uk_bin_week` (`snapshot_date`,`sync_batch_id`,`wid`,`whb_id`,`product_id`,`bin_identity_key`)');
        PREPARE weekly_bin_stmt FROM @weekly_bin_ddl;
        EXECUTE weekly_bin_stmt;
        DEALLOCATE PREPARE weekly_bin_stmt;
    END IF;

    SELECT COUNT(*) INTO v_after FROM ods_lingxing_inventory_bin_detail_weekly;
    IF v_before <> v_after THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Row count changed; check concurrent writes before continuing';
    END IF;
    SET SESSION lock_wait_timeout = v_old_wait;
    DO RELEASE_LOCK('inventory:weekly-export');
    SET v_lock=0;
    SELECT 'OK' AS migration_status,v_before AS rows_before,v_after AS rows_after;
END$$
CALL `migrate_weekly_bin_identity_20260910`()$$
DROP PROCEDURE `migrate_weekly_bin_identity_20260910`$$
DELIMITER ;
-- 仍需运行11_周报仓位业务键_验证_只读.sql，确认OK后加载新Python代码。
