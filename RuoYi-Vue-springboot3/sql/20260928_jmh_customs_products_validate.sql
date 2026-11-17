-- JMH 报关商品迁移：从已导入的 jmh_data_platform.products 建立不可变批次快照并分类。
-- 本脚本只创建审计对象和验证快照，不写 customs_declaration_history。
-- MySQL 8.0+。

USE jmh_data_platform;
SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 1048576;

-- 每次正式迁移必须使用新的批次号；长度限制用于保证 updated_by 不超过 64 字符。
SET @batch_id := '20260928-jmh-products-v1';

CREATE TABLE IF NOT EXISTS jmh_customs_products_migration_run (
    batch_id VARCHAR(40) NOT NULL COMMENT '唯一迁移批次',
    source_table VARCHAR(128) NOT NULL DEFAULT 'jmh_data_platform.products',
    source_rows INT NOT NULL DEFAULT 0,
    classified_rows INT NOT NULL DEFAULT 0,
    expected_new_valid INT NOT NULL DEFAULT 0,
    applied_rows INT NOT NULL DEFAULT 0,
    source_fingerprint CHAR(64) DEFAULT NULL COMMENT '按 legacy_id 排序后的行哈希聚合 SHA-256',
    run_status VARCHAR(20) NOT NULL DEFAULT 'VALIDATING',
    validated_at DATETIME DEFAULT NULL,
    applied_at DATETIME DEFAULT NULL,
    rolled_back_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    notes VARCHAR(500) DEFAULT NULL,
    PRIMARY KEY (batch_id),
    KEY idx_jmh_customs_migration_run_status (run_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='JMH products 到 ERP 报关商品表的迁移批次';

CREATE TABLE IF NOT EXISTS jmh_customs_products_migration_audit (
    batch_id VARCHAR(40) NOT NULL,
    legacy_id INT NOT NULL,
    source_row_hash CHAR(64) NOT NULL,
    raw_sku VARCHAR(100) DEFAULT NULL,
    normalized_sku_key VARCHAR(100) DEFAULT NULL,
    description_cn VARCHAR(255) DEFAULT NULL,
    model VARCHAR(255) DEFAULT NULL,
    unit VARCHAR(50) DEFAULT NULL,
    unit_price_usd DECIMAL(18,4) DEFAULT NULL,
    currency VARCHAR(20) DEFAULT NULL,
    single_weight DECIMAL(18,6) DEFAULT NULL,
    hs_code VARCHAR(50) DEFAULT NULL,
    hs_description TEXT DEFAULT NULL,
    origin_country VARCHAR(100) DEFAULT NULL,
    destination_country VARCHAR(100) DEFAULT NULL,
    source_location VARCHAR(255) DEFAULT NULL,
    exemption VARCHAR(100) DEFAULT NULL,
    source_created_at DATETIME DEFAULT NULL,
    source_updated_at DATETIME DEFAULT NULL,
    validation_status VARCHAR(32) NOT NULL,
    conflict_type VARCHAR(64) DEFAULT NULL,
    conflict_detail VARCHAR(1000) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, legacy_id),
    KEY idx_jmh_customs_audit_batch_status (batch_id, validation_status),
    KEY idx_jmh_customs_audit_batch_key (batch_id, normalized_sku_key),
    CONSTRAINT fk_jmh_customs_audit_run
        FOREIGN KEY (batch_id)
        REFERENCES jmh_customs_products_migration_run (batch_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='JMH products 迁移源快照、唯一分类和冲突审计';

DROP PROCEDURE IF EXISTS sp_validate_jmh_customs_products;
DELIMITER $$

CREATE PROCEDURE sp_validate_jmh_customs_products(IN p_batch_id VARCHAR(40))
main: BEGIN
    DECLARE v_source_rows INT DEFAULT 0;
    DECLARE v_audit_rows INT DEFAULT 0;
    DECLARE v_new_valid INT DEFAULT 0;
    DECLARE v_existing_applied_rows INT DEFAULT 0;
    DECLARE v_existing_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_fingerprint CHAR(64) DEFAULT NULL;
    DECLARE v_function_count INT DEFAULT 0;

    IF p_batch_id IS NULL OR TRIM(p_batch_id) = '' OR CHAR_LENGTH(p_batch_id) > 40 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'batch_id is required and must be at most 40 characters';
    END IF;

    SELECT COUNT(*)
      INTO v_function_count
    FROM information_schema.ROUTINES
    WHERE ROUTINE_SCHEMA = DATABASE()
      AND ROUTINE_NAME = 'normalize_customs_sku_key'
      AND ROUTINE_TYPE = 'FUNCTION';

    IF v_function_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'normalize_customs_sku_key function is missing or ambiguous';
    END IF;

    SELECT MAX(run_status), COALESCE(MAX(applied_rows), 0)
      INTO v_existing_status, v_existing_applied_rows
    FROM jmh_customs_products_migration_run
    WHERE batch_id = p_batch_id;

    IF v_existing_status = 'APPLIED' OR v_existing_applied_rows > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'This batch was already applied; use a new batch_id for revalidation';
    END IF;

    DELETE FROM jmh_customs_products_migration_audit
    WHERE batch_id = p_batch_id;

    DELETE FROM jmh_customs_products_migration_run
    WHERE batch_id = p_batch_id;

    SELECT COUNT(*) INTO v_source_rows FROM products;

    INSERT INTO jmh_customs_products_migration_run (
        batch_id, source_table, source_rows, classified_rows,
        expected_new_valid, applied_rows, run_status, notes
    ) VALUES (
        p_batch_id, 'jmh_data_platform.products', v_source_rows, 0,
        0, 0, 'VALIDATING',
        'Validation snapshot created from the already imported products table; no production rows written.'
    );

    INSERT INTO jmh_customs_products_migration_audit (
        batch_id, legacy_id, source_row_hash, raw_sku, normalized_sku_key,
        description_cn, model, unit, unit_price_usd, currency, single_weight,
        hs_code, hs_description, origin_country, destination_country,
        source_location, exemption, source_created_at, source_updated_at,
        validation_status, conflict_type, conflict_detail
    )
    WITH source_base AS (
        SELECT
            p.id AS legacy_id,
            p.sku AS raw_sku,
            TRIM(IFNULL(p.sku, '')) AS clean_sku,
            normalize_customs_sku_key(TRIM(IFNULL(p.sku, ''))) AS normalized_sku_key,
            p.description_cn,
            p.model,
            p.unit,
            p.unit_price_usd,
            p.currency,
            p.single_weight,
            p.hs_code,
            p.hs_description,
            p.origin_country,
            p.destination_country,
            p.source_location,
            p.exemption,
            p.created_at AS source_created_at,
            p.updated_at AS source_updated_at,
            SHA2(CONCAT_WS(CHAR(31),
                p.id, IFNULL(p.sku, ''), IFNULL(p.description_cn, ''),
                IFNULL(p.model, ''), IFNULL(p.unit, ''), IFNULL(p.unit_price_usd, ''),
                IFNULL(p.currency, ''), IFNULL(p.single_weight, ''),
                IFNULL(p.hs_code, ''), IFNULL(p.hs_description, ''),
                IFNULL(p.origin_country, ''), IFNULL(p.destination_country, ''),
                IFNULL(p.source_location, ''), IFNULL(p.exemption, ''),
                IFNULL(DATE_FORMAT(p.created_at, '%Y-%m-%d %H:%i:%s'), ''),
                IFNULL(DATE_FORMAT(p.updated_at, '%Y-%m-%d %H:%i:%s'), '')
            ), 256) AS source_row_hash
        FROM products p
    ), source_keyed AS (
        SELECT b.*,
               COUNT(*) OVER (PARTITION BY b.normalized_sku_key) AS normalized_key_count
        FROM source_base b
    ), source_flags AS (
        SELECT k.*,
               CONCAT_WS('; ',
                   IF(k.normalized_sku_key = '', 'normalized SKU key is empty', NULL),
                   IF(CHAR_LENGTH(k.clean_sku) > 100, 'SKU exceeds 100 characters', NULL),
                   IF(CHAR_LENGTH(k.normalized_sku_key) > 100, 'normalized SKU key exceeds 100 characters', NULL),
                   IF(k.clean_sku REGEXP '[[:cntrl:]]', 'SKU contains control characters', NULL),
                   IF(k.clean_sku NOT REGEXP '[0-9A-Za-z]',
                      'SKU contains no ASCII letter or digit; likely template text', NULL),
                   IF(k.unit_price_usd < 0, 'unit price is negative', NULL),
                   IF(k.single_weight < 0, 'single weight is negative', NULL),
                   IF(TRIM(IFNULL(k.currency, '')) <> ''
                      AND UPPER(TRIM(k.currency)) NOT REGEXP '^[A-Z]{3}$',
                      'currency is not a three-letter code', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.description_cn, '')) > 255, 'description exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.model, '')) > 255, 'model exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.unit, '')) > 50, 'unit exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.hs_code, '')) > 50, 'HS code exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.origin_country, '')) > 100, 'origin country exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.destination_country, '')) > 100, 'destination country exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.source_location, '')) > 255, 'source location exceeds target length', NULL),
                   IF(CHAR_LENGTH(IFNULL(k.exemption, '')) > 100, 'exemption exceeds target length', NULL)
               ) AS invalid_detail,
               EXISTS (
                   SELECT 1
                   FROM customs_declaration_product_view v
                   WHERE v.sku COLLATE utf8mb4_0900_ai_ci =
                         k.clean_sku COLLATE utf8mb4_0900_ai_ci
               ) AS exact_exists,
               EXISTS (
                   SELECT 1
                   FROM customs_declaration_product_view v
                   WHERE v.sku_key COLLATE utf8mb4_0900_ai_ci =
                         k.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
               ) AS normalized_exists,
               EXISTS (
                   SELECT 1
                   FROM customs_declaration_product_view v
                   WHERE v.sku COLLATE utf8mb4_0900_ai_ci =
                         k.clean_sku COLLATE utf8mb4_0900_ai_ci
                     AND TRIM(IFNULL(v.description_cn, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.description_cn, '')) COLLATE utf8mb4_0900_ai_ci
                     AND TRIM(IFNULL(v.model, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.model, '')) COLLATE utf8mb4_0900_ai_ci
                     AND TRIM(IFNULL(v.unit, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.unit, '')) COLLATE utf8mb4_0900_ai_ci
                     AND v.unit_price_usd <=> k.unit_price_usd
                     AND UPPER(TRIM(IFNULL(v.currency, ''))) = UPPER(TRIM(IFNULL(k.currency, '')))
                     AND v.single_weight <=> k.single_weight
                     AND TRIM(IFNULL(v.hs_code, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.hs_code, '')) COLLATE utf8mb4_0900_ai_ci
                     AND REGEXP_REPLACE(TRIM(IFNULL(v.hs_description, '')), '[[:space:]]+', ' ')
                           COLLATE utf8mb4_0900_ai_ci =
                         REGEXP_REPLACE(TRIM(IFNULL(k.hs_description, '')), '[[:space:]]+', ' ')
                           COLLATE utf8mb4_0900_ai_ci
                     AND TRIM(IFNULL(v.origin_country, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.origin_country, '')) COLLATE utf8mb4_0900_ai_ci
                     AND TRIM(IFNULL(v.destination_country, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.destination_country, '')) COLLATE utf8mb4_0900_ai_ci
                     AND REGEXP_REPLACE(TRIM(IFNULL(v.source_location, '')), '[[:space:]]+', ' ')
                           COLLATE utf8mb4_0900_ai_ci =
                         REGEXP_REPLACE(TRIM(IFNULL(k.source_location, '')), '[[:space:]]+', ' ')
                           COLLATE utf8mb4_0900_ai_ci
                     AND TRIM(IFNULL(v.exemption, '')) COLLATE utf8mb4_0900_ai_ci =
                         TRIM(IFNULL(k.exemption, '')) COLLATE utf8mb4_0900_ai_ci
               ) AS exact_same_exists
        FROM source_keyed k
    ), classified AS (
        SELECT f.*,
               CASE
                   WHEN f.clean_sku = '' THEN 'REJECT_EMPTY_SKU'
                   WHEN f.invalid_detail <> '' THEN 'REJECT_INVALID'
                   WHEN f.normalized_key_count > 1 THEN 'SOURCE_NORMALIZED_DUPLICATE'
                   WHEN f.exact_exists = 1 AND f.exact_same_exists = 1 THEN 'EXACT_SAME'
                   WHEN f.exact_exists = 1 THEN 'EXACT_CONFLICT'
                   WHEN f.normalized_exists = 1 THEN 'NORMALIZED_CONFLICT'
                   ELSE 'NEW_VALID'
               END AS validation_status
        FROM source_flags f
    )
    SELECT
        p_batch_id,
        c.legacy_id,
        c.source_row_hash,
        c.raw_sku,
        c.normalized_sku_key,
        c.description_cn,
        c.model,
        c.unit,
        c.unit_price_usd,
        c.currency,
        c.single_weight,
        c.hs_code,
        c.hs_description,
        c.origin_country,
        c.destination_country,
        c.source_location,
        c.exemption,
        c.source_created_at,
        c.source_updated_at,
        c.validation_status,
        CASE WHEN c.validation_status = 'NEW_VALID' THEN NULL ELSE c.validation_status END,
        CASE c.validation_status
            WHEN 'REJECT_EMPTY_SKU' THEN 'SKU is empty after trimming'
            WHEN 'REJECT_INVALID' THEN c.invalid_detail
            WHEN 'SOURCE_NORMALIZED_DUPLICATE' THEN CONCAT(
                'normalized key ', c.normalized_sku_key,
                ' occurs ', c.normalized_key_count, ' times in products')
            WHEN 'EXACT_SAME' THEN 'exact SKU exists and compared business fields are equal'
            WHEN 'EXACT_CONFLICT' THEN 'exact SKU exists but one or more compared business fields differ'
            WHEN 'NORMALIZED_CONFLICT' THEN CONCAT(
                'normalized key ', c.normalized_sku_key,
                ' already exists under another complete SKU')
            ELSE NULL
        END
    FROM classified c;

    SELECT COUNT(*),
           COALESCE(SUM(validation_status = 'NEW_VALID'), 0),
           SHA2(GROUP_CONCAT(source_row_hash ORDER BY legacy_id SEPARATOR ''), 256)
      INTO v_audit_rows, v_new_valid, v_fingerprint
    FROM jmh_customs_products_migration_audit
    WHERE batch_id = p_batch_id;

    IF v_audit_rows <> v_source_rows THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Validation failed: classified row count does not equal source row count';
    END IF;

    UPDATE jmh_customs_products_migration_run
    SET classified_rows = v_audit_rows,
        expected_new_valid = v_new_valid,
        source_fingerprint = v_fingerprint,
        run_status = 'VALIDATED',
        validated_at = NOW(),
        notes = CONCAT('All ', v_audit_rows,
                       ' source rows received exactly one classification; NEW_VALID=',
                       v_new_valid, '.')
    WHERE batch_id = p_batch_id;
END$$

DELIMITER ;
CALL sp_validate_jmh_customs_products(@batch_id);
DROP PROCEDURE IF EXISTS sp_validate_jmh_customs_products;

-- 汇总：所有状态数量相加必须等于 source_rows。
SELECT r.batch_id, r.source_table, r.source_rows, r.classified_rows,
       r.expected_new_valid, r.applied_rows, r.source_fingerprint,
       r.run_status, r.validated_at
FROM jmh_customs_products_migration_run r
WHERE r.batch_id = @batch_id;

SELECT validation_status, COUNT(*) AS row_count
FROM jmh_customs_products_migration_audit
WHERE batch_id = @batch_id
GROUP BY validation_status
ORDER BY FIELD(validation_status,
    'REJECT_EMPTY_SKU', 'REJECT_INVALID', 'SOURCE_NORMALIZED_DUPLICATE',
    'EXACT_SAME', 'EXACT_CONFLICT', 'NORMALIZED_CONFLICT', 'NEW_VALID');

-- 完整性检查：problem_count 必须全部为 0。
SELECT 'unclassified_rows' AS check_name,
       source_rows - classified_rows AS problem_count
FROM jmh_customs_products_migration_run
WHERE batch_id = @batch_id
UNION ALL
SELECT 'unknown_status', COUNT(*)
FROM jmh_customs_products_migration_audit
WHERE batch_id = @batch_id
  AND validation_status NOT IN (
      'REJECT_EMPTY_SKU', 'REJECT_INVALID', 'SOURCE_NORMALIZED_DUPLICATE',
      'EXACT_SAME', 'EXACT_CONFLICT', 'NORMALIZED_CONFLICT', 'NEW_VALID')
UNION ALL
SELECT 'new_valid_with_existing_normalized_key', COUNT(*)
FROM jmh_customs_products_migration_audit a
WHERE a.batch_id = @batch_id
  AND a.validation_status = 'NEW_VALID'
  AND EXISTS (
      SELECT 1
      FROM customs_declaration_product_view v
      WHERE v.sku_key COLLATE utf8mb4_0900_ai_ci =
            a.normalized_sku_key COLLATE utf8mb4_0900_ai_ci
  );

-- 报告查询：按需导出 CSV。默认只展示前 100 条，避免终端输出过大。
SELECT legacy_id, raw_sku, normalized_sku_key, validation_status,
       conflict_type, conflict_detail
FROM jmh_customs_products_migration_audit
WHERE batch_id = @batch_id
  AND validation_status <> 'NEW_VALID'
ORDER BY validation_status, normalized_sku_key, legacy_id
LIMIT 100;

SELECT legacy_id, raw_sku, normalized_sku_key, description_cn,
       unit_price_usd, single_weight, hs_code
FROM jmh_customs_products_migration_audit
WHERE batch_id = @batch_id
  AND validation_status = 'NEW_VALID'
ORDER BY legacy_id
LIMIT 100;
