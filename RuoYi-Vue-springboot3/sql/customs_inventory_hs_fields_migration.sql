-- 出入库清单申报要素拆分字段：海关编码 + 申报要素说明。
-- 重复执行安全：仅在字段不存在时新增，并用 declaration_elements 回填空字段。

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN hs_code varchar(50) NULL COMMENT ''海关编码，从申报要素开头数字拆分'' AFTER declaration_elements',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'hs_code'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE customs_inventory_list ADD COLUMN hs_description text NULL COMMENT ''申报要素说明，去除开头海关编码后的内容'' AFTER hs_code',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'customs_inventory_list' AND COLUMN_NAME = 'hs_description'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE customs_inventory_list
SET hs_code = CASE
        WHEN TRIM(IFNULL(declaration_elements, '')) REGEXP '^[0-9]{6,13}'
        THEN REGEXP_SUBSTR(TRIM(declaration_elements), '^[0-9]{6,13}')
        ELSE IFNULL(hs_code, '')
    END,
    hs_description = CASE
        WHEN TRIM(IFNULL(declaration_elements, '')) REGEXP '^[0-9]{6,13}'
        THEN TRIM(REGEXP_REPLACE(TRIM(declaration_elements), '^[0-9]{6,13}[[:space:]]*', ''))
        ELSE IFNULL(hs_description, declaration_elements)
    END
WHERE declaration_elements IS NOT NULL
  AND (IFNULL(hs_code, '') = '' OR hs_description IS NULL);

-- 统一匹配视图：库存拆分字段优先；旧数据兜底从 declaration_elements 现场拆分；最后使用历史报关资料。
CREATE OR REPLACE VIEW customs_declaration_product_view AS
SELECT
  i.id,
  i.sku,
  normalize_customs_sku_key(i.sku) AS sku_key,
  IFNULL(i.product_code, '') AS product_code,
  COALESCE(NULLIF(i.product_name, ''), h.description_cn, '') AS description_cn,
  COALESCE(NULLIF(h.model, ''), '无型号') AS model,
  COALESCE(NULLIF(i.customs_unit, ''), NULLIF(i.unit, ''), h.unit, '个') AS unit,
  COALESCE(h.unit_price_usd,
    CASE WHEN i.tax_included_price REGEXP '^[0-9.]+(/[0-9.]+)*$'
         THEN CAST(SUBSTRING_INDEX(i.tax_included_price, '/', -1) AS DECIMAL(18,4)) END) AS unit_price_usd,
  COALESCE(NULLIF(h.currency, ''), 'USD') AS currency,
  h.single_weight, h.packing_net_weight, h.packing_gross_weight, h.packing_cbm,
  h.box_length, h.box_width, h.box_height, h.box_no,
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
    AND (h2.product_code COLLATE utf8mb4_0900_ai_ci = IFNULL(i.product_code, '') COLLATE utf8mb4_0900_ai_ci OR h2.product_code = '')
  ORDER BY CASE
      WHEN h2.sku COLLATE utf8mb4_0900_ai_ci = i.sku COLLATE utf8mb4_0900_ai_ci THEN 0
      WHEN UPPER(h2.sku) LIKE 'JMH%' THEN 1
      WHEN h2.sku REGEXP '^[0-9]' THEN 2
      ELSE 3 END,
    CASE WHEN h2.product_code COLLATE utf8mb4_0900_ai_ci = IFNULL(i.product_code, '') COLLATE utf8mb4_0900_ai_ci THEN 0 ELSE 1 END,
    h2.updated_at DESC, h2.id DESC
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
  h.sku, h.sku_key, h.product_code, h.description_cn, h.model, h.unit,
  h.unit_price_usd, h.currency, h.single_weight, h.packing_net_weight,
  h.packing_gross_weight, h.packing_cbm, h.box_length, h.box_width, h.box_height,
  h.box_no, h.hs_code, h.hs_description, h.origin_country, h.destination_country,
  h.source_location, h.exemption, h.is_tax, h.source_type, h.source_file_name,
  h.source_sheet, h.source_row_no, h.updated_by, h.created_at, h.updated_at
FROM customs_declaration_history h
WHERE NOT EXISTS (
  SELECT 1 FROM customs_inventory_list i
  WHERE normalize_customs_sku_key(i.sku) COLLATE utf8mb4_0900_ai_ci = h.sku_key COLLATE utf8mb4_0900_ai_ci
);
