-- JMH 报关商品迁移回滚：仅删除指定批次新增且迁移后未被业务修改的记录。
-- 一旦检测到数量或字段变化，整批回滚并报错，避免删除后续业务维护成果。

USE jmh_data_platform;
SET NAMES utf8mb4;

SET @batch_id := '20260928-jmh-products-v1';

DROP PROCEDURE IF EXISTS sp_rollback_jmh_customs_products;
DELIMITER $$

CREATE PROCEDURE sp_rollback_jmh_customs_products(IN p_batch_id VARCHAR(40))
main: BEGIN
    DECLARE v_lock_acquired INT DEFAULT 0;
    DECLARE v_run_count INT DEFAULT 0;
    DECLARE v_run_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_applied_rows INT DEFAULT 0;
    DECLARE v_current_rows INT DEFAULT 0;
    DECLARE v_unchanged_rows INT DEFAULT 0;
    DECLARE v_deleted_rows INT DEFAULT 0;
    DECLARE v_updated_by VARCHAR(64);
    DECLARE v_message VARCHAR(255);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DO RELEASE_LOCK('jmh_customs_products_migration_apply');
        RESIGNAL;
    END;

    IF p_batch_id IS NULL OR TRIM(p_batch_id) = '' OR CHAR_LENGTH(p_batch_id) > 40 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'batch_id is required and must be at most 40 characters';
    END IF;

    SET v_updated_by = CONCAT('migration:jmh-customs:', p_batch_id);

    SELECT GET_LOCK('jmh_customs_products_migration_apply', 10)
      INTO v_lock_acquired;
    IF v_lock_acquired <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Could not acquire the customs migration lock';
    END IF;

    SELECT COUNT(*), MAX(run_status), COALESCE(MAX(applied_rows), 0)
      INTO v_run_count, v_run_status, v_applied_rows
    FROM jmh_customs_products_migration_run
    WHERE batch_id = p_batch_id;

    IF v_run_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migration batch was not found';
    END IF;

    SELECT COUNT(*)
      INTO v_current_rows
    FROM customs_declaration_history
    WHERE source_type = 'JMH_PLUGIN_MIGRATION'
      AND source_file_name = 'jmh_data_platform.products'
      AND updated_by = v_updated_by;

    IF v_run_status = 'ROLLED_BACK' THEN
        IF v_current_rows <> 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Batch is marked ROLLED_BACK but migration rows still exist';
        END IF;

        DO RELEASE_LOCK('jmh_customs_products_migration_apply');
        SELECT p_batch_id AS batch_id, 'ALREADY_ROLLED_BACK' AS result,
               0 AS deleted_rows;
        LEAVE main;
    END IF;

    IF v_run_status <> 'APPLIED' THEN
        SET v_message = CONCAT('Batch status must be APPLIED, actual=', IFNULL(v_run_status, 'NULL'));
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    IF v_current_rows <> v_applied_rows THEN
        SET v_message = CONCAT('Current batch rows=', v_current_rows,
                               ' but recorded applied rows=', v_applied_rows);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    -- 逐字段确认记录仍等于迁移快照；业务编辑后的行不会被批量删除。
    SELECT COUNT(*)
      INTO v_unchanged_rows
    FROM customs_declaration_history h
    JOIN jmh_customs_products_migration_audit a
      ON a.batch_id = p_batch_id
     AND a.validation_status = 'NEW_VALID'
     AND a.legacy_id = h.source_row_no
    WHERE h.source_type = 'JMH_PLUGIN_MIGRATION'
      AND h.source_file_name = 'jmh_data_platform.products'
      AND h.source_sheet = 'products'
      AND h.updated_by = v_updated_by
      AND h.sku COLLATE utf8mb4_0900_ai_ci = TRIM(a.raw_sku) COLLATE utf8mb4_0900_ai_ci
      AND h.sku_key COLLATE utf8mb4_0900_ai_ci = a.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
      AND h.product_code = ''
      AND h.description_cn COLLATE utf8mb4_0900_ai_ci =
          TRIM(IFNULL(a.description_cn, '')) COLLATE utf8mb4_0900_ai_ci
      AND h.model COLLATE utf8mb4_0900_ai_ci =
          TRIM(IFNULL(a.model, '')) COLLATE utf8mb4_0900_ai_ci
      AND h.unit COLLATE utf8mb4_0900_ai_ci =
          TRIM(IFNULL(a.unit, '')) COLLATE utf8mb4_0900_ai_ci
      AND h.unit_price_usd <=> a.unit_price_usd
      AND h.currency = COALESCE(NULLIF(UPPER(TRIM(a.currency)), ''), 'USD')
      AND h.single_weight <=> a.single_weight
      AND h.packing_net_weight IS NULL
      AND h.packing_gross_weight IS NULL
      AND h.packing_cbm IS NULL
      AND h.box_length IS NULL
      AND h.box_width IS NULL
      AND h.box_height IS NULL
      AND h.box_no IS NULL
      AND h.hs_code COLLATE utf8mb4_0900_ai_ci =
          TRIM(IFNULL(a.hs_code, '')) COLLATE utf8mb4_0900_ai_ci
      AND h.hs_description <=> NULLIF(
          REGEXP_REPLACE(TRIM(IFNULL(a.hs_description, '')), '[[:space:]]+', ' '), '')
      AND h.origin_country COLLATE utf8mb4_0900_ai_ci =
          COALESCE(NULLIF(TRIM(a.origin_country), ''), '中国') COLLATE utf8mb4_0900_ai_ci
      AND h.destination_country COLLATE utf8mb4_0900_ai_ci =
          TRIM(IFNULL(a.destination_country, '')) COLLATE utf8mb4_0900_ai_ci
      AND h.source_location COLLATE utf8mb4_0900_ai_ci =
          REGEXP_REPLACE(TRIM(IFNULL(a.source_location, '')), '[[:space:]]+', ' ')
              COLLATE utf8mb4_0900_ai_ci
      AND h.exemption COLLATE utf8mb4_0900_ai_ci =
          TRIM(IFNULL(a.exemption, '')) COLLATE utf8mb4_0900_ai_ci
      AND h.is_tax = 0
      AND h.created_at = COALESCE(a.source_created_at, h.created_at)
      AND h.updated_at = COALESCE(a.source_updated_at, a.source_created_at, h.updated_at);

    IF v_unchanged_rows <> v_applied_rows THEN
        SET v_message = CONCAT('Only ', v_unchanged_rows, ' of ', v_applied_rows,
                               ' rows still match the migration snapshot; manual restore is required');
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    START TRANSACTION;

    SELECT run_status
      INTO v_run_status
    FROM jmh_customs_products_migration_run
    WHERE batch_id = p_batch_id
    FOR UPDATE;

    IF v_run_status <> 'APPLIED' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Batch status changed while acquiring the transaction lock';
    END IF;

    DELETE FROM customs_declaration_history
    WHERE source_type = 'JMH_PLUGIN_MIGRATION'
      AND source_file_name = 'jmh_data_platform.products'
      AND source_sheet = 'products'
      AND updated_by = v_updated_by;

    SET v_deleted_rows = ROW_COUNT();

    IF v_deleted_rows <> v_applied_rows THEN
        SET v_message = CONCAT('Deleted rows=', v_deleted_rows,
                               ' but recorded applied rows=', v_applied_rows);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    UPDATE jmh_customs_products_migration_run
    SET run_status = 'ROLLED_BACK',
        rolled_back_at = NOW(),
        notes = CONCAT('Rolled back ', v_deleted_rows,
                       ' unchanged migration rows; audit snapshot retained.')
    WHERE batch_id = p_batch_id;

    COMMIT;
    DO RELEASE_LOCK('jmh_customs_products_migration_apply');

    SELECT p_batch_id AS batch_id, 'ROLLED_BACK' AS result,
           v_deleted_rows AS deleted_rows;
END$$

DELIMITER ;
CALL sp_rollback_jmh_customs_products(@batch_id);
DROP PROCEDURE IF EXISTS sp_rollback_jmh_customs_products;

SELECT batch_id, source_rows, classified_rows, expected_new_valid,
       applied_rows, run_status, validated_at, applied_at, rolled_back_at
FROM jmh_customs_products_migration_run
WHERE batch_id = @batch_id;

SELECT COUNT(*) AS remaining_batch_rows
FROM customs_declaration_history
WHERE source_type = 'JMH_PLUGIN_MIGRATION'
  AND source_file_name = 'jmh_data_platform.products'
  AND updated_by = CONCAT('migration:jmh-customs:', @batch_id);
