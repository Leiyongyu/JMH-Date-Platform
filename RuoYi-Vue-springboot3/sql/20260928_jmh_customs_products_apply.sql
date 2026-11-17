-- JMH 报关商品迁移：把已审批的 NEW_VALID 快照安全写入 customs_declaration_history。
-- 前置：先执行 20260928_jmh_customs_products_validate.sql 并审核冲突报告。
-- 可重复执行：已成功应用的同一批次只做一致性核验，不会重复插入。

USE jmh_data_platform;
SET NAMES utf8mb4;

SET @batch_id := '20260928-jmh-products-v1';
SET @approved_new_valid := 201;

CREATE TABLE IF NOT EXISTS jmh_customs_declaration_history_backup (
    backup_batch_id VARCHAR(40) NOT NULL,
    id BIGINT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    sku_key VARCHAR(100) NOT NULL,
    product_code VARCHAR(100) NOT NULL DEFAULT '',
    description_cn VARCHAR(255) NOT NULL DEFAULT '',
    model VARCHAR(255) NOT NULL DEFAULT '',
    unit VARCHAR(50) NOT NULL DEFAULT '',
    unit_price_usd DECIMAL(18,4) DEFAULT NULL,
    currency VARCHAR(20) NOT NULL DEFAULT 'USD',
    single_weight DECIMAL(18,6) DEFAULT NULL,
    packing_net_weight DECIMAL(18,4) DEFAULT NULL,
    packing_gross_weight DECIMAL(18,4) DEFAULT NULL,
    packing_cbm DECIMAL(18,6) DEFAULT NULL,
    box_length DECIMAL(18,4) DEFAULT NULL,
    box_width DECIMAL(18,4) DEFAULT NULL,
    box_height DECIMAL(18,4) DEFAULT NULL,
    box_no VARCHAR(100) DEFAULT NULL,
    hs_code VARCHAR(50) NOT NULL DEFAULT '',
    hs_description TEXT DEFAULT NULL,
    origin_country VARCHAR(100) NOT NULL DEFAULT '中国',
    destination_country VARCHAR(100) NOT NULL DEFAULT '',
    source_location VARCHAR(255) NOT NULL DEFAULT '',
    exemption VARCHAR(100) NOT NULL DEFAULT '',
    is_tax TINYINT NOT NULL DEFAULT 0,
    source_type VARCHAR(20) NOT NULL DEFAULT 'IMPORT',
    source_file_name VARCHAR(255) DEFAULT NULL,
    source_sheet VARCHAR(100) DEFAULT NULL,
    source_row_no INT DEFAULT NULL,
    updated_by VARCHAR(64) DEFAULT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    backup_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (backup_batch_id, id),
    KEY idx_jmh_customs_history_backup_sku_key (backup_batch_id, sku_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='JMH 报关商品迁移前 customs_declaration_history 完整快照';

DROP PROCEDURE IF EXISTS sp_apply_jmh_customs_products;
DELIMITER $$

CREATE PROCEDURE sp_apply_jmh_customs_products(
    IN p_batch_id VARCHAR(40),
    IN p_approved_new_valid INT
)
main: BEGIN
    DECLARE v_lock_acquired INT DEFAULT 0;
    DECLARE v_run_count INT DEFAULT 0;
    DECLARE v_run_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_source_rows INT DEFAULT 0;
    DECLARE v_classified_rows INT DEFAULT 0;
    DECLARE v_expected_new_valid INT DEFAULT 0;
    DECLARE v_recorded_applied_rows INT DEFAULT 0;
    DECLARE v_audit_new_valid INT DEFAULT 0;
    DECLARE v_current_candidate_rows INT DEFAULT 0;
    DECLARE v_existing_batch_rows INT DEFAULT 0;
    DECLARE v_inserted_rows INT DEFAULT 0;
    DECLARE v_history_rows INT DEFAULT 0;
    DECLARE v_backup_rows INT DEFAULT 0;
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

    IF p_approved_new_valid IS NULL OR p_approved_new_valid < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'approved_new_valid must be a non-negative integer';
    END IF;

    SET v_updated_by = CONCAT('migration:jmh-customs:', p_batch_id);

    SELECT GET_LOCK('jmh_customs_products_migration_apply', 10)
      INTO v_lock_acquired;
    IF v_lock_acquired <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Could not acquire the customs migration lock';
    END IF;

    SELECT COUNT(*), MAX(run_status), COALESCE(MAX(source_rows), 0),
           COALESCE(MAX(classified_rows), 0), COALESCE(MAX(expected_new_valid), 0),
           COALESCE(MAX(applied_rows), 0)
      INTO v_run_count, v_run_status, v_source_rows, v_classified_rows,
           v_expected_new_valid, v_recorded_applied_rows
    FROM jmh_customs_products_migration_run
    WHERE batch_id = p_batch_id;

    IF v_run_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Validated migration batch was not found';
    END IF;

    SELECT COUNT(*)
      INTO v_existing_batch_rows
    FROM customs_declaration_history
    WHERE source_type = 'JMH_PLUGIN_MIGRATION'
      AND source_file_name = 'jmh_data_platform.products'
      AND updated_by = v_updated_by;

    IF v_run_status = 'APPLIED' THEN
        IF v_existing_batch_rows <> v_recorded_applied_rows
           OR v_recorded_applied_rows <> p_approved_new_valid THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Applied batch metadata does not match current migration rows';
        END IF;

        DO RELEASE_LOCK('jmh_customs_products_migration_apply');
        SELECT p_batch_id AS batch_id, 'ALREADY_APPLIED' AS result,
               v_existing_batch_rows AS applied_rows;
        LEAVE main;
    END IF;

    IF v_run_status <> 'VALIDATED' THEN
        SET v_message = CONCAT('Batch status must be VALIDATED, actual=', IFNULL(v_run_status, 'NULL'));
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    IF v_source_rows <> v_classified_rows THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source and classified row counts do not match';
    END IF;

    IF v_expected_new_valid <> p_approved_new_valid THEN
        SET v_message = CONCAT('Approved NEW_VALID=', p_approved_new_valid,
                               ' but validated NEW_VALID=', v_expected_new_valid);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    SELECT COUNT(*)
      INTO v_audit_new_valid
    FROM jmh_customs_products_migration_audit
    WHERE batch_id = p_batch_id
      AND validation_status = 'NEW_VALID';

    IF v_audit_new_valid <> p_approved_new_valid THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Audit NEW_VALID count does not match the approved count';
    END IF;

    IF v_existing_batch_rows <> 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Untracked rows already exist for this migration batch';
    END IF;

    START TRANSACTION;

    -- 锁定批次行，防止同批次并发应用。
    SELECT run_status
      INTO v_run_status
    FROM jmh_customs_products_migration_run
    WHERE batch_id = p_batch_id
    FOR UPDATE;

    IF v_run_status <> 'VALIDATED' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Batch status changed while acquiring the transaction lock';
    END IF;

    SELECT COUNT(*) INTO v_history_rows FROM customs_declaration_history;

    SELECT COUNT(*)
      INTO v_backup_rows
    FROM jmh_customs_declaration_history_backup
    WHERE backup_batch_id = p_batch_id;

    IF v_backup_rows <> 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A pre-migration backup already exists for this unapplied batch';
    END IF;

    INSERT INTO jmh_customs_declaration_history_backup (
        backup_batch_id, id, sku, sku_key, product_code, description_cn,
        model, unit, unit_price_usd, currency, single_weight,
        packing_net_weight, packing_gross_weight, packing_cbm,
        box_length, box_width, box_height, box_no, hs_code, hs_description,
        origin_country, destination_country, source_location, exemption, is_tax,
        source_type, source_file_name, source_sheet, source_row_no, updated_by,
        created_at, updated_at
    )
    SELECT p_batch_id, h.id, h.sku, h.sku_key, h.product_code, h.description_cn,
           h.model, h.unit, h.unit_price_usd, h.currency, h.single_weight,
           h.packing_net_weight, h.packing_gross_weight, h.packing_cbm,
           h.box_length, h.box_width, h.box_height, h.box_no, h.hs_code,
           h.hs_description, h.origin_country, h.destination_country,
           h.source_location, h.exemption, h.is_tax, h.source_type,
           h.source_file_name, h.source_sheet, h.source_row_no, h.updated_by,
           h.created_at, h.updated_at
    FROM customs_declaration_history h
    ORDER BY h.id;

    SET v_backup_rows = ROW_COUNT();
    IF v_backup_rows <> v_history_rows THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Pre-migration backup row count does not match history row count';
    END IF;

    -- 校验到应用之间若 ERP 新增了相同业务键，则整批停止，不静默跳过。
    SELECT COUNT(*)
      INTO v_current_candidate_rows
    FROM jmh_customs_products_migration_audit a
    WHERE a.batch_id = p_batch_id
      AND a.validation_status = 'NEW_VALID'
      AND NOT EXISTS (
          SELECT 1
          FROM customs_declaration_history h
          WHERE h.sku_key COLLATE utf8mb4_0900_ai_ci =
                a.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
      )
      AND NOT EXISTS (
          SELECT 1
          FROM customs_inventory_list i
          WHERE normalize_customs_sku_key(i.sku) COLLATE utf8mb4_0900_ai_ci =
                a.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
      );

    IF v_current_candidate_rows <> p_approved_new_valid THEN
        SET v_message = CONCAT('Current safe candidates=', v_current_candidate_rows,
                               ' but approved NEW_VALID=', p_approved_new_valid,
                               '; re-run validation with a new batch');
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    INSERT INTO customs_declaration_history (
        sku, sku_key, product_code, description_cn, model, unit,
        unit_price_usd, currency, single_weight,
        packing_net_weight, packing_gross_weight, packing_cbm,
        box_length, box_width, box_height, box_no,
        hs_code, hs_description, origin_country, destination_country,
        source_location, exemption, is_tax,
        source_type, source_file_name, source_sheet, source_row_no,
        updated_by, created_at, updated_at
    )
    SELECT
        TRIM(a.raw_sku),
        a.normalized_sku_key,
        '',
        TRIM(IFNULL(a.description_cn, '')),
        TRIM(IFNULL(a.model, '')),
        TRIM(IFNULL(a.unit, '')),
        a.unit_price_usd,
        COALESCE(NULLIF(UPPER(TRIM(a.currency)), ''), 'USD'),
        a.single_weight,
        NULL, NULL, NULL,
        NULL, NULL, NULL, NULL,
        TRIM(IFNULL(a.hs_code, '')),
        NULLIF(REGEXP_REPLACE(TRIM(IFNULL(a.hs_description, '')), '[[:space:]]+', ' '), ''),
        COALESCE(NULLIF(TRIM(a.origin_country), ''), '中国'),
        TRIM(IFNULL(a.destination_country, '')),
        REGEXP_REPLACE(TRIM(IFNULL(a.source_location, '')), '[[:space:]]+', ' '),
        TRIM(IFNULL(a.exemption, '')),
        0,
        'JMH_PLUGIN_MIGRATION',
        'jmh_data_platform.products',
        'products',
        a.legacy_id,
        v_updated_by,
        COALESCE(a.source_created_at, NOW()),
        COALESCE(a.source_updated_at, a.source_created_at, NOW())
    FROM jmh_customs_products_migration_audit a
    WHERE a.batch_id = p_batch_id
      AND a.validation_status = 'NEW_VALID'
      AND NOT EXISTS (
          SELECT 1
          FROM customs_declaration_history h
          WHERE h.sku_key COLLATE utf8mb4_0900_ai_ci =
                a.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
      )
      AND NOT EXISTS (
          SELECT 1
          FROM customs_inventory_list i
          WHERE normalize_customs_sku_key(i.sku) COLLATE utf8mb4_0900_ai_ci =
                a.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
      )
    ORDER BY a.legacy_id;

    SET v_inserted_rows = ROW_COUNT();

    IF v_inserted_rows <> p_approved_new_valid THEN
        SET v_message = CONCAT('Inserted rows=', v_inserted_rows,
                               ' but approved NEW_VALID=', p_approved_new_valid);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_message;
    END IF;

    UPDATE jmh_customs_products_migration_run
    SET run_status = 'APPLIED',
        applied_rows = v_inserted_rows,
        applied_at = NOW(),
        rolled_back_at = NULL,
        notes = CONCAT('Safely inserted ', v_inserted_rows,
                       ' NEW_VALID rows; existing normalized keys were not overwritten.')
    WHERE batch_id = p_batch_id;

    COMMIT;
    DO RELEASE_LOCK('jmh_customs_products_migration_apply');

    SELECT p_batch_id AS batch_id, 'APPLIED' AS result,
           v_inserted_rows AS applied_rows;
END$$

DELIMITER ;
CALL sp_apply_jmh_customs_products(@batch_id, @approved_new_valid);
DROP PROCEDURE IF EXISTS sp_apply_jmh_customs_products;

-- 应用后验收：所有 problem_count 必须为 0。
SELECT batch_id, source_rows, classified_rows, expected_new_valid,
       applied_rows, run_status, validated_at, applied_at
FROM jmh_customs_products_migration_run
WHERE batch_id = @batch_id;

SELECT 'batch_row_count_mismatch' AS check_name,
       ABS(@approved_new_valid - COUNT(*)) AS problem_count
FROM customs_declaration_history
WHERE source_type = 'JMH_PLUGIN_MIGRATION'
  AND source_file_name = 'jmh_data_platform.products'
  AND updated_by = CONCAT('migration:jmh-customs:', @batch_id)
UNION ALL
SELECT 'batch_rows_missing_from_view', COUNT(*)
FROM customs_declaration_history h
WHERE h.source_type = 'JMH_PLUGIN_MIGRATION'
  AND h.source_file_name = 'jmh_data_platform.products'
  AND h.updated_by = CONCAT('migration:jmh-customs:', @batch_id)
  AND NOT EXISTS (
      SELECT 1
      FROM customs_declaration_product_view v
      WHERE v.sku COLLATE utf8mb4_0900_ai_ci = h.sku COLLATE utf8mb4_0900_ai_ci
  )
UNION ALL
SELECT 'duplicate_batch_normalized_key', COUNT(*)
FROM (
    SELECT sku_key
    FROM customs_declaration_history
    WHERE source_type = 'JMH_PLUGIN_MIGRATION'
      AND source_file_name = 'jmh_data_platform.products'
      AND updated_by = CONCAT('migration:jmh-customs:', @batch_id)
    GROUP BY sku_key
    HAVING COUNT(*) > 1
) duplicate_keys
UNION ALL
SELECT 'backup_row_count_mismatch',
       ABS(
           (SELECT COUNT(*)
            FROM jmh_customs_declaration_history_backup
            WHERE backup_batch_id = @batch_id)
           -
           ((SELECT COUNT(*) FROM customs_declaration_history)
            - @approved_new_valid)
       );
