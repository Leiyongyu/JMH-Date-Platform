/*
 Navicat/MySQL one-click deploy patch
 Target database: jmh_data_platform

 Purpose:
 1. Fill missing customs declaration structures on deployment.
 2. Overwrite normalize_customs_sku_key() with the latest matching rule.
 3. Add inventory auto-stock fields and HS split fields.
 4. Create history table, generate log table, and product view.
 5. Add FBA box/product listing indexes used by the latest logic.

 Safe to rerun:
 - Tables use CREATE TABLE IF NOT EXISTS.
 - Columns and indexes are added only when absent.
 - Function and view are replaced.

 Intentionally excluded:
 - customs_inventory_remaining_stock_recalc.sql is NOT included because it recalculates stock values.
*/

USE `jmh_data_platform`;
SET NAMES utf8mb4;

/* 1) Latest SKU normalize function */
DROP FUNCTION IF EXISTS `normalize_customs_sku_key`;
DELIMITER $$
CREATE FUNCTION `normalize_customs_sku_key`(p_sku VARCHAR(512)) RETURNS varchar(512) CHARSET utf8mb4
    NO SQL
    DETERMINISTIC
BEGIN
    DECLARE prefix VARCHAR(255);
    DECLARE dash_pos INT;
    DECLARE segment VARCHAR(255);
    DECLARE rest VARCHAR(512);

    IF p_sku IS NULL OR p_sku = '' THEN
        RETURN '';
    END IF;

    SET dash_pos = INSTR(p_sku, '-');
    IF dash_pos = 0 THEN
        RETURN p_sku;
    END IF;

    SET prefix = UPPER(SUBSTRING_INDEX(p_sku, '-', 1));
    IF prefix LIKE '%PC%' THEN
        RETURN p_sku;
    END IF;

    SET rest = p_sku;
    segment_loop: LOOP
        SET dash_pos = INSTR(rest, '-');
        IF dash_pos = 0 THEN
            SET segment = rest;
        ELSE
            SET segment = LEFT(rest, dash_pos - 1);
        END IF;

        IF segment REGEXP '[0-9]' THEN
            RETURN CONCAT(REGEXP_REPLACE(segment, '^[^0-9]+', ''), IF(dash_pos = 0, '', SUBSTRING(rest, dash_pos)));
        END IF;

        IF dash_pos = 0 THEN
            LEAVE segment_loop;
        END IF;

        SET rest = SUBSTRING(rest, dash_pos + 1);
    END LOOP segment_loop;

    RETURN p_sku;
END$$
DELIMITER ;

/* 2) customs_products_list compatibility fields/index */
SET @sql := IF(
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list') > 0
    AND (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list' AND COLUMN_NAME = 'product_code') = 0,
    'ALTER TABLE customs_products_list ADD COLUMN product_code varchar(100) NOT NULL DEFAULT '''' COMMENT ''商品编码'' AFTER sku',
    'SELECT ''skip customs_products_list.product_code'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list') > 0
    AND (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list' AND INDEX_NAME = 'uk_sku') > 0,
    'ALTER TABLE customs_products_list DROP INDEX uk_sku',
    'SELECT ''skip drop customs_products_list.uk_sku'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list') > 0
    AND (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list' AND INDEX_NAME = 'uk_sku_product_code') = 0,
    'ALTER TABLE customs_products_list ADD UNIQUE KEY uk_sku_product_code (sku, product_code)',
    'SELECT ''skip customs_products_list.uk_sku_product_code'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

/* 3) Current history table for declaration products */
CREATE TABLE IF NOT EXISTS `customs_declaration_history` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `sku` varchar(100) NOT NULL COMMENT '历史报关单中的完整SKU',
  `sku_key` varchar(100) NOT NULL COMMENT '忽略品牌前缀后的匹配键',
  `product_code` varchar(100) NOT NULL DEFAULT '' COMMENT '出入库商品编码',
  `description_cn` varchar(255) NOT NULL DEFAULT '' COMMENT '中文品名',
  `model` varchar(255) NOT NULL DEFAULT '' COMMENT '规格型号',
  `unit` varchar(50) NOT NULL DEFAULT '' COMMENT '申报单位',
  `unit_price_usd` decimal(18,4) DEFAULT NULL COMMENT '历史报关单价，仅保存当前值',
  `currency` varchar(20) NOT NULL DEFAULT 'USD' COMMENT '币种',
  `single_weight` decimal(18,6) DEFAULT NULL COMMENT '单件净重KG',
  `packing_net_weight` decimal(18,4) DEFAULT NULL COMMENT '装箱净重KG',
  `packing_gross_weight` decimal(18,4) DEFAULT NULL COMMENT '装箱毛重KG',
  `packing_cbm` decimal(18,6) DEFAULT NULL COMMENT '装箱体积CBM',
  `box_length` decimal(18,4) DEFAULT NULL COMMENT '箱长CM',
  `box_width` decimal(18,4) DEFAULT NULL COMMENT '箱宽CM',
  `box_height` decimal(18,4) DEFAULT NULL COMMENT '箱高CM',
  `box_no` varchar(100) DEFAULT NULL COMMENT '箱号',
  `hs_code` varchar(50) NOT NULL DEFAULT '' COMMENT '海关编码',
  `hs_description` text COMMENT '海关申报要素说明',
  `origin_country` varchar(100) NOT NULL DEFAULT '中国' COMMENT '原产国',
  `destination_country` varchar(100) NOT NULL DEFAULT '' COMMENT '最终目的国',
  `source_location` varchar(255) NOT NULL DEFAULT '' COMMENT '境内货源地',
  `exemption` varchar(100) NOT NULL DEFAULT '' COMMENT '征免方式',
  `is_tax` tinyint NOT NULL DEFAULT 0 COMMENT '是否含税商品：0否，1是',
  `source_type` varchar(20) NOT NULL DEFAULT 'IMPORT' COMMENT '来源：IMPORT/MANUAL',
  `source_file_name` varchar(255) DEFAULT NULL COMMENT '最后导入文件名',
  `source_sheet` varchar(100) DEFAULT NULL COMMENT '最后导入Sheet',
  `source_row_no` int DEFAULT NULL COMMENT '最后导入行号',
  `updated_by` varchar(64) DEFAULT NULL COMMENT '最后修改人',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sku_product_code` (`sku`,`product_code`),
  KEY `idx_sku_key` (`sku_key`),
  KEY `idx_sku_key_product_code` (`sku_key`,`product_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='历史报关商品当前值表';

ALTER TABLE `customs_declaration_history` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

/* 4) customs_inventory_list HS fields */
SET @sql := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'hs_code') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN hs_code varchar(50) DEFAULT NULL COMMENT ''商品编码/海关编码'' AFTER declaration_elements',
    'SELECT ''skip customs_inventory_list.hs_code'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'hs_description') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN hs_description text COMMENT ''申报要素说明（不含商品编码）'' AFTER hs_code',
    'SELECT ''skip customs_inventory_list.hs_description'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE customs_inventory_list
SET hs_code = NULLIF(REGEXP_SUBSTR(TRIM(IFNULL(declaration_elements, '')), '^[0-9]{6,13}'), ''),
    hs_description = NULLIF(TRIM(REGEXP_REPLACE(TRIM(IFNULL(declaration_elements, '')), '^[0-9]{6,13}[[:space:]]*', '')), '')
WHERE (hs_code IS NULL OR hs_code = '' OR hs_description IS NULL OR hs_description = '')
  AND declaration_elements IS NOT NULL
  AND declaration_elements != '';

/* 5) customs_inventory_list auto calculated stock fields */
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_czech_warehouse_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_czech_warehouse_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算捷克仓库存'' AFTER czech_warehouse_qty',
    'SELECT ''skip auto_czech_warehouse_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_uk_warehouse_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_uk_warehouse_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算英国仓库存'' AFTER uk_warehouse_qty',
    'SELECT ''skip auto_uk_warehouse_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_us_warehouse_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_us_warehouse_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算美国谷仓库存'' AFTER us_warehouse_qty',
    'SELECT ''skip auto_us_warehouse_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_de_warehouse_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_de_warehouse_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算德国仓库存'' AFTER de_warehouse_qty',
    'SELECT ''skip auto_de_warehouse_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_fba_de_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_de_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算FBA(DE)库存'' AFTER fba_de_qty',
    'SELECT ''skip auto_fba_de_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_fba_uk_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_uk_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算FBA(UK)库存'' AFTER fba_uk_qty',
    'SELECT ''skip auto_fba_uk_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_fba_us_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_us_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算FBA(US)库存'' AFTER fba_us_qty',
    'SELECT ''skip auto_fba_us_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_fba_fr_qty') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_fba_fr_qty decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算FBA(FR)库存'' AFTER fba_fr_qty',
    'SELECT ''skip auto_fba_fr_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'auto_remaining_stock') = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN auto_remaining_stock decimal(18,2) DEFAULT NULL COMMENT ''系统自动计算剩余库存'' AFTER remaining_stock',
    'SELECT ''skip auto_remaining_stock''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE customs_inventory_list
SET auto_czech_warehouse_qty = COALESCE(auto_czech_warehouse_qty, czech_warehouse_qty),
    auto_uk_warehouse_qty = COALESCE(auto_uk_warehouse_qty, uk_warehouse_qty),
    auto_us_warehouse_qty = COALESCE(auto_us_warehouse_qty, us_warehouse_qty),
    auto_de_warehouse_qty = COALESCE(auto_de_warehouse_qty, de_warehouse_qty),
    auto_fba_de_qty = COALESCE(auto_fba_de_qty, fba_de_qty),
    auto_fba_uk_qty = COALESCE(auto_fba_uk_qty, fba_uk_qty),
    auto_fba_us_qty = COALESCE(auto_fba_us_qty, fba_us_qty),
    auto_fba_fr_qty = COALESCE(auto_fba_fr_qty, fba_fr_qty),
    auto_remaining_stock = COALESCE(auto_remaining_stock, remaining_stock);

/* 6) Declaration generation stock deduction log */
CREATE TABLE IF NOT EXISTS `customs_declaration_generate_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `declaration_no` varchar(80) NOT NULL COMMENT '本次报关生成批次号',
  `source_type` varchar(20) NOT NULL COMMENT '来源类型：EBAY/FBA/MANUAL',
  `source_order_no` varchar(100) NOT NULL COMMENT '来源单号：备货单号/FBA货件号/手工批次',
  `source_line_id` varchar(100) NOT NULL COMMENT '来源明细ID',
  `raw_sku` varchar(200) DEFAULT NULL COMMENT '来源原始SKU',
  `standard_sku` varchar(200) NOT NULL COMMENT '匹配后的出入库清单SKU',
  `product_code` varchar(200) NOT NULL DEFAULT '' COMMENT '商品编码',
  `source_location` varchar(200) DEFAULT NULL COMMENT '货源地',
  `warehouse_bucket` varchar(30) NOT NULL COMMENT '仓库归类：CZ/UK/US_GC/DE/FBA_DE/FBA_UK/FBA_US/FBA_FR/UNKNOWN',
  `warehouse_name` varchar(200) DEFAULT NULL COMMENT '实际仓库名称或原始仓库信息',
  `quantity` decimal(18,4) NOT NULL DEFAULT 0.0000 COMMENT '本次报关数量',
  `match_status` varchar(30) NOT NULL DEFAULT 'MATCHED' COMMENT '匹配状态：MATCHED/UNKNOWN_WAREHOUSE/MISSING_INVENTORY',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `created_by` varchar(64) DEFAULT NULL COMMENT '创建人',
  `created_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_customs_decl_source_line` (`source_type`,`source_order_no`,`source_line_id`,`warehouse_bucket`),
  KEY `idx_customs_decl_sku_code` (`standard_sku`,`product_code`),
  KEY `idx_customs_decl_bucket` (`warehouse_bucket`),
  KEY `idx_customs_decl_no` (`declaration_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报关单生成库存扣减日志';

/* 7) FBA box/import query indexes */
SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_fba_shipment_box' AND INDEX_NAME = 'idx_fba_box_shipment_sku') = 0,
    'ALTER TABLE amz_fba_shipment_box ADD INDEX idx_fba_box_shipment_sku (shipment_id, sku)',
    'SELECT ''skip idx_fba_box_shipment_sku''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_fba_shipment_box' AND INDEX_NAME = 'idx_fba_box_shipment_msku') = 0,
    'ALTER TABLE amz_fba_shipment_box ADD INDEX idx_fba_box_shipment_msku (shipment_id, msku)',
    'SELECT ''skip idx_fba_box_shipment_msku''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'amz_product_listing' AND INDEX_NAME = 'idx_amz_listing_sid_seller_sku') = 0,
    'ALTER TABLE amz_product_listing ADD INDEX idx_amz_listing_sid_seller_sku (sid, seller_sku)',
    'SELECT ''skip idx_amz_listing_sid_seller_sku''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

/* 8) Migrate old customs_products_list current values into history, only when absent */
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_products_list') > 0,
  'INSERT IGNORE INTO customs_declaration_history (
    sku, sku_key, product_code, description_cn, model, unit,
    unit_price_usd, currency, hs_code, hs_description,
    origin_country, destination_country, source_location, exemption,
    source_type, updated_by, created_at, updated_at
)
SELECT
    p.sku,
    normalize_customs_sku_key(p.sku),
    IFNULL(p.product_code, ''''),
    IFNULL(p.description_cn, ''''),
    IFNULL(p.model, ''''),
    IFNULL(p.unit, ''''),
    p.unit_price_usd,
    ''USD'',
    IFNULL(p.hs_code, ''''),
    p.hs_description,
    ''中国'',
    '''',
    IFNULL(p.source_location, ''''),
    IFNULL(p.exemption, ''''),
    ''LEGACY'',
    ''SYSTEM'',
    NOW(),
    NOW()
FROM customs_products_list p
WHERE p.sku IS NOT NULL AND p.sku != ''''',
  'SELECT ''skip migrate customs_products_list'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

/* 9) Quartz schedule: FBA shipment first, box detail after shipment */
UPDATE sys_job
SET cron_expression = '0 0 6 * * ?',
    status = '0',
    update_time = NOW(),
    remark = CONCAT(IFNULL(remark, ''), IF(INSTR(IFNULL(remark, ''), '20260713: FBA货件每天06:00') > 0, '', '；20260713: FBA货件每天06:00'))
WHERE invoke_target = 'operationSyncTask.syncAmzFbaShipment';

UPDATE sys_job
SET cron_expression = '0 30 6 * * ?',
    status = '0',
    update_time = NOW(),
    remark = CONCAT(IFNULL(remark, ''), IF(INSTR(IFNULL(remark, ''), '20260713: FBA装箱信息每天06:30') > 0, '', '；20260713: FBA装箱信息每天06:30'))
WHERE invoke_target = 'operationSyncTask.syncAmzFbaShipmentBox';

/* 10) Unified declaration product view: inventory first, history fallback */
CREATE OR REPLACE VIEW `customs_declaration_product_view` AS
SELECT
    i.id,
    i.sku,
    normalize_customs_sku_key(i.sku) AS sku_key,
    IFNULL(i.product_code, '') AS product_code,
    COALESCE(NULLIF(i.product_name, ''), h.description_cn, '') AS description_cn,
    COALESCE(NULLIF(h.model, ''), '无型号') AS model,
    COALESCE(NULLIF(i.customs_unit, ''), NULLIF(i.unit, ''), h.unit, '个') AS unit,
    COALESCE(
        h.unit_price_usd,
        CASE
            WHEN i.tax_included_price REGEXP '^[0-9.]+(/[0-9.]+)*$'
                THEN CAST(SUBSTRING_INDEX(i.tax_included_price, '/', -1) AS DECIMAL(18,4))
            ELSE NULL
        END
    ) AS unit_price_usd,
    COALESCE(NULLIF(h.currency, ''), 'USD') AS currency,
    h.single_weight,
    h.packing_net_weight,
    h.packing_gross_weight,
    h.packing_cbm,
    h.box_length,
    h.box_width,
    h.box_height,
    h.box_no,
    COALESCE(
        NULLIF(i.hs_code, ''),
        NULLIF(REGEXP_SUBSTR(TRIM(IFNULL(i.declaration_elements, '')), '^[0-9]{6,13}'), ''),
        h.hs_code,
        ''
    ) AS hs_code,
    COALESCE(
        NULLIF(i.hs_description, ''),
        NULLIF(TRIM(REGEXP_REPLACE(TRIM(IFNULL(i.declaration_elements, '')), '^[0-9]{6,13}[[:space:]]*', '')), ''),
        h.hs_description,
        ''
    ) AS hs_description,
    COALESCE(NULLIF(h.origin_country, ''), '中国') AS origin_country,
    COALESCE(NULLIF(h.destination_country, ''), '美国') AS destination_country,
    COALESCE(NULLIF(h.source_location, ''), NULLIF(i.product_code, ''), '') AS source_location,
    COALESCE(NULLIF(h.exemption, ''), '照章') AS exemption,
    COALESCE(po.is_tax, h.is_tax, 0) AS is_tax,
    COALESCE(h.source_type, 'INVENTORY') AS source_type,
    h.source_file_name,
    h.source_sheet,
    h.source_row_no,
    h.updated_by,
    COALESCE(h.created_at, i.created_at) AS created_at,
    GREATEST(COALESCE(h.updated_at, '1970-01-01'), COALESCE(i.updated_at, '1970-01-01')) AS updated_at
FROM customs_inventory_list i
LEFT JOIN customs_declaration_history h ON h.id = (
    SELECT h2.id
    FROM customs_declaration_history h2
    WHERE h2.sku_key COLLATE utf8mb4_0900_ai_ci = normalize_customs_sku_key(i.sku) COLLATE utf8mb4_0900_ai_ci
      AND (
          h2.product_code COLLATE utf8mb4_0900_ai_ci = IFNULL(i.product_code, '') COLLATE utf8mb4_0900_ai_ci
          OR h2.product_code = ''
      )
    ORDER BY
      CASE
        WHEN h2.sku COLLATE utf8mb4_0900_ai_ci = i.sku COLLATE utf8mb4_0900_ai_ci THEN 0
        WHEN UPPER(h2.sku) LIKE 'JMH%' THEN 1
        WHEN h2.sku REGEXP '^[0-9]' THEN 2
        ELSE 3
      END,
      CASE
        WHEN h2.product_code COLLATE utf8mb4_0900_ai_ci = IFNULL(i.product_code, '') COLLATE utf8mb4_0900_ai_ci THEN 0
        ELSE 1
      END,
      h2.updated_at DESC,
      h2.id DESC
    LIMIT 1
)
LEFT JOIN (
    SELECT item_sku, MAX(IFNULL(is_tax, 0)) AS is_tax
    FROM purchase_order
    WHERE item_sku IS NOT NULL AND item_sku != ''
    GROUP BY item_sku
) po ON po.item_sku COLLATE utf8mb4_unicode_ci = i.sku COLLATE utf8mb4_unicode_ci
WHERE i.sku IS NOT NULL AND i.sku != ''

UNION ALL

SELECT
    -h.id AS id,
    h.sku,
    h.sku_key,
    h.product_code,
    h.description_cn,
    h.model,
    h.unit,
    h.unit_price_usd,
    h.currency,
    h.single_weight,
    h.packing_net_weight,
    h.packing_gross_weight,
    h.packing_cbm,
    h.box_length,
    h.box_width,
    h.box_height,
    h.box_no,
    h.hs_code,
    h.hs_description,
    h.origin_country,
    h.destination_country,
    h.source_location,
    h.exemption,
    h.is_tax,
    h.source_type,
    h.source_file_name,
    h.source_sheet,
    h.source_row_no,
    h.updated_by,
    h.created_at,
    h.updated_at
FROM customs_declaration_history h
WHERE NOT EXISTS (
    SELECT 1
    FROM customs_inventory_list i
    WHERE normalize_customs_sku_key(i.sku) COLLATE utf8mb4_0900_ai_ci = h.sku_key COLLATE utf8mb4_0900_ai_ci
);

/* 11) Simple verification */
SELECT 'customs_declaration_history' AS object_name, COUNT(*) AS exists_count
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_declaration_history'
UNION ALL
SELECT 'customs_declaration_generate_log', COUNT(*)
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_declaration_generate_log'
UNION ALL
SELECT 'customs_declaration_product_view', COUNT(*)
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customs_declaration_product_view';

SELECT 'missing_customs_inventory_columns' AS check_name, COUNT(*) AS missing_count
FROM (
    SELECT 'auto_czech_warehouse_qty' AS column_name UNION ALL
    SELECT 'auto_uk_warehouse_qty' UNION ALL
    SELECT 'auto_us_warehouse_qty' UNION ALL
    SELECT 'auto_de_warehouse_qty' UNION ALL
    SELECT 'auto_fba_de_qty' UNION ALL
    SELECT 'auto_fba_uk_qty' UNION ALL
    SELECT 'auto_fba_us_qty' UNION ALL
    SELECT 'auto_fba_fr_qty' UNION ALL
    SELECT 'auto_remaining_stock' UNION ALL
    SELECT 'hs_code' UNION ALL
    SELECT 'hs_description'
) required_columns
WHERE NOT EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS c
    WHERE c.TABLE_SCHEMA = DATABASE()
      AND c.TABLE_NAME = 'customs_inventory_list'
      AND c.COLUMN_NAME = required_columns.column_name
);
