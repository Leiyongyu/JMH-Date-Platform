-- 历史报关商品当前值表：完整 SKU + product_code 唯一，重复导入/保存直接覆盖当前值。
CREATE TABLE IF NOT EXISTS customs_declaration_history (
  id bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  sku varchar(100) NOT NULL COMMENT '历史报关单中的完整SKU',
  sku_key varchar(100) NOT NULL COMMENT '忽略品牌前缀后的匹配键',
  product_code varchar(100) NOT NULL DEFAULT '' COMMENT '出入库商品编码',
  description_cn varchar(255) NOT NULL DEFAULT '' COMMENT '中文品名',
  model varchar(255) NOT NULL DEFAULT '' COMMENT '规格型号',
  unit varchar(50) NOT NULL DEFAULT '' COMMENT '申报单位',
  unit_price_usd decimal(18,4) DEFAULT NULL COMMENT '历史报关单价，仅保存当前值',
  currency varchar(20) NOT NULL DEFAULT 'USD' COMMENT '币种',
  single_weight decimal(18,6) DEFAULT NULL COMMENT '单件净重KG',
  packing_net_weight decimal(18,4) DEFAULT NULL COMMENT '装箱净重KG',
  packing_gross_weight decimal(18,4) DEFAULT NULL COMMENT '装箱毛重KG',
  packing_cbm decimal(18,6) DEFAULT NULL COMMENT '装箱体积CBM',
  box_length decimal(18,4) DEFAULT NULL COMMENT '箱长CM',
  box_width decimal(18,4) DEFAULT NULL COMMENT '箱宽CM',
  box_height decimal(18,4) DEFAULT NULL COMMENT '箱高CM',
  box_no varchar(100) DEFAULT NULL COMMENT '箱号',
  hs_code varchar(50) NOT NULL DEFAULT '' COMMENT '海关编码',
  hs_description text COMMENT '海关申报要素说明',
  origin_country varchar(100) NOT NULL DEFAULT '中国' COMMENT '原产国',
  destination_country varchar(100) NOT NULL DEFAULT '' COMMENT '最终目的国',
  source_location varchar(255) NOT NULL DEFAULT '' COMMENT '境内货源地',
  exemption varchar(100) NOT NULL DEFAULT '' COMMENT '征免方式',
  is_tax tinyint NOT NULL DEFAULT 0 COMMENT '是否含税商品：0否，1是',
  source_type varchar(20) NOT NULL DEFAULT 'IMPORT' COMMENT '来源：IMPORT/MANUAL',
  source_file_name varchar(255) DEFAULT NULL COMMENT '最后导入文件名',
  source_sheet varchar(100) DEFAULT NULL COMMENT '最后导入Sheet',
  source_row_no int DEFAULT NULL COMMENT '最后导入行号',
  updated_by varchar(64) DEFAULT NULL COMMENT '最后修改人',
  created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sku_product_code (sku, product_code),
  KEY idx_sku_key (sku_key),
  KEY idx_sku_key_product_code (sku_key, product_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='历史报关商品当前值表';

ALTER TABLE customs_declaration_history CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 首次迁移时保留旧商品库中已经维护的数据；重复执行不会覆盖新历史数据。
INSERT IGNORE INTO customs_declaration_history
  (sku, sku_key, product_code, description_cn, model, unit, unit_price_usd, currency,
   single_weight, packing_net_weight, packing_gross_weight, packing_cbm,
   box_length, box_width, box_height, box_no, hs_code, hs_description,
   origin_country, destination_country, source_location, exemption, is_tax,
   source_type, source_file_name, updated_by, created_at, updated_at)
SELECT
  sku, normalize_customs_sku_key(sku), '', IFNULL(description_cn, ''),
  IFNULL(model, ''), IFNULL(unit, ''), unit_price_usd, IFNULL(currency, 'USD'),
  single_weight, packing_net_weight, packing_gross_weight, packing_cbm,
  box_length, box_width, box_height, box_no, IFNULL(hs_code, ''), hs_description,
  IFNULL(origin_country, '中国'), IFNULL(destination_country, ''), IFNULL(source_location, ''),
  IFNULL(exemption, ''), IFNULL(is_tax, 0), 'MIGRATION', 'customs_products_list', 'migration',
  IFNULL(created_at, CURRENT_TIMESTAMP), IFNULL(updated_at, CURRENT_TIMESTAMP)
FROM customs_products_list
WHERE sku IS NOT NULL AND sku != '';

-- 统一匹配视图：库存清单优先，空字段由历史报关补齐；库存不存在时直接使用历史记录。
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
  COALESCE(h.destination_country, '') AS destination_country,
  COALESCE(NULLIF(h.source_location, ''), '') AS source_location,
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
