-- 目标库：Date-Project（Python数据库）。不要在jmh_data_platform执行。
-- 月度库存统计新增eBay SKU利润文件上传、负责人清洗和实际达成汇总。

CREATE TABLE IF NOT EXISTS `ods_inventory_report_ebay_sales` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM，由上传时选择',
    `sku` VARCHAR(255) NOT NULL COMMENT 'eBay商品SKU',
    `brand_code` VARCHAR(32) NOT NULL COMMENT '从SKU解析出的品牌编码',
    `image_url` TEXT NULL COMMENT '商品图片链接',
    `multi_variant` VARCHAR(16) NULL COMMENT '是否多属性',
    `product_sales_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '商品销售额',
    `receivable_shipping_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '应收运费',
    `amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '实际达成金额，商品销售额加应收运费',
    `source_file_name` VARCHAR(255) NOT NULL COMMENT '上传源文件名',
    `source_sheet` VARCHAR(128) NOT NULL COMMENT '上传源工作表名',
    `source_row` INT NOT NULL COMMENT '上传源文件行号',
    `import_batch_id` VARCHAR(64) NOT NULL COMMENT '上传批次ID，用于数据追溯',
    `imported_by` VARCHAR(64) NULL COMMENT '上传人账号',
    `imported_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '数据导入时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_inventory_ebay_sales_month_sku` (`stat_month`,`sku`),
    KEY `idx_inventory_ebay_sales_month_brand` (`stat_month`,`brand_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-月度库存统计eBay SKU销售额上传源数据';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_ebay_sales_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT 'eBay销售额ODS源表主键',
    `sku` VARCHAR(255) NOT NULL COMMENT 'eBay商品SKU',
    `brand_code` VARCHAR(32) NOT NULL COMMENT '从SKU解析出的品牌编码',
    `image_url` TEXT NULL COMMENT '商品图片链接',
    `multi_variant` VARCHAR(16) NULL COMMENT '是否多属性',
    `department_code` VARCHAR(32) NOT NULL DEFAULT 'EBAY-1' COMMENT '汇总部门编码，固定EBAY-1',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '按eBay品牌规则匹配的负责人',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `product_sales_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '商品销售额',
    `receivable_shipping_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '应收运费',
    `amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'eBay实际达成金额，商品销售额加应收运费',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_ebay_sales_month_source` (`stat_month`,`source_id`),
    KEY `idx_inventory_ebay_sales_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_ebay_sales_month_brand` (`stat_month`,`brand_code`),
    KEY `idx_inventory_ebay_sales_month_sku` (`stat_month`,`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-月度库存统计eBay实际达成负责人清洗明细';

SELECT table_name,table_comment
FROM information_schema.tables
WHERE table_schema=DATABASE()
  AND table_name IN (
      'ods_inventory_report_ebay_sales',
      'dwd_inventory_report_ebay_sales_detail'
  )
ORDER BY table_name;
