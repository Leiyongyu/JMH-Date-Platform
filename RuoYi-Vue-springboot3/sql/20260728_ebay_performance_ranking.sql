-- eBay 月度绩效排名：利润明细、品牌负责人规则、负责人汇总。
-- 可重复执行。执行前需先完成绩效排名菜单基础脚本。

CREATE TABLE IF NOT EXISTS `ebay_monthly_performance_profit` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM，来自文件名',
  `sku` varchar(255) NOT NULL COMMENT '利润表SKU原值',
  `brand_code` varchar(64) NOT NULL COMMENT 'SKU第一个连字符前的品牌码',
  `image_url` varchar(1000) DEFAULT NULL COMMENT '商品图片',
  `multi_variant` varchar(32) DEFAULT NULL COMMENT '是否多属性',
  `gross_profit` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '利润',
  `product_sales_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '商品销售额',
  `receivable_shipping_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费',
  `sales_amount` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT '销售额=商品销售额+应收运费',
  `refund_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额',
  `net_sales_amount` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT '净销售额=销售额-退款金额',
  `source_file_name` varchar(255) DEFAULT NULL COMMENT '来源Excel文件名',
  `source_sheet` varchar(64) DEFAULT NULL COMMENT '来源sheet',
  `source_row` int DEFAULT NULL COMMENT '来源行号',
  `imported_by` varchar(64) DEFAULT NULL COMMENT '导入人',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_ebay_perf_profit_month` (`stat_month`),
  KEY `idx_ebay_perf_profit_month_brand` (`stat_month`,`brand_code`),
  KEY `idx_ebay_perf_profit_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay月度绩效利润明细表';

-- 兼容已创建过旧版 eBay 利润明细表的数据库。
SET @ebay_product_sales_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ebay_monthly_performance_profit'
    AND COLUMN_NAME = 'product_sales_amount'
);
SET @ebay_product_sales_sql := IF(
  @ebay_product_sales_column_exists = 0,
  'ALTER TABLE `ebay_monthly_performance_profit`
     ADD COLUMN `product_sales_amount` decimal(20,6) NOT NULL DEFAULT 0
       COMMENT ''商品销售额'' AFTER `gross_profit`',
  'SELECT 1'
);
PREPARE ebay_product_sales_stmt FROM @ebay_product_sales_sql;
EXECUTE ebay_product_sales_stmt;
DEALLOCATE PREPARE ebay_product_sales_stmt;

SET @ebay_shipping_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ebay_monthly_performance_profit'
    AND COLUMN_NAME = 'receivable_shipping_amount'
);
SET @ebay_shipping_sql := IF(
  @ebay_shipping_column_exists = 0,
  'ALTER TABLE `ebay_monthly_performance_profit`
     ADD COLUMN `receivable_shipping_amount` decimal(20,6) NOT NULL DEFAULT 0
       COMMENT ''应收运费'' AFTER `product_sales_amount`',
  'SELECT 1'
);
PREPARE ebay_shipping_stmt FROM @ebay_shipping_sql;
EXECUTE ebay_shipping_stmt;
DEALLOCATE PREPARE ebay_shipping_stmt;

ALTER TABLE `ebay_monthly_performance_profit`
  MODIFY COLUMN `sales_amount` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT '销售额=商品销售额+应收运费',
  MODIFY COLUMN `net_sales_amount` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT '净销售额=销售额-退款金额';

-- 包装数量前缀不是品牌：2PC-BMW-...、4PC-HYD-... 均取第二段品牌。
UPDATE `ebay_monthly_performance_profit`
SET `brand_code` = UPPER(
      SUBSTRING_INDEX(SUBSTRING_INDEX(`sku`, '-', 2), '-', -1)
    ),
    `update_time` = NOW()
WHERE UPPER(SUBSTRING_INDEX(`sku`, '-', 1)) REGEXP '^[0-9]+PC$'
  AND `sku` LIKE '%-%';

CREATE TABLE IF NOT EXISTS `ebay_performance_owner_rule` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM',
  `brand_code` varchar(64) NOT NULL COMMENT '品牌码',
  `principal_name` varchar(100) NOT NULL COMMENT '负责人',
  `source_file_name` varchar(255) DEFAULT NULL COMMENT '来源Excel文件名',
  `source_sheet` varchar(64) DEFAULT NULL COMMENT '来源sheet',
  `source_row` int DEFAULT NULL COMMENT '来源行号',
  `imported_by` varchar(64) DEFAULT NULL COMMENT '导入人',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_perf_owner_month_brand` (`stat_month`,`brand_code`),
  KEY `idx_ebay_perf_owner_month_name` (`stat_month`,`principal_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay月度绩效品牌负责人规则表';

UPDATE `ebay_performance_owner_rule`
SET `principal_name` = '未分配',
    `update_time` = NOW()
WHERE TRIM(`principal_name`) IN ('待定', '待到');

CREATE TABLE IF NOT EXISTS `ebay_performance_ranking` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM',
  `principal_name` varchar(200) NOT NULL COMMENT '品牌规则匹配后的负责人',
  `gross_profit` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '负责人汇总利润',
  `sales_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '负责人汇总销售额',
  `refund_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '负责人汇总退款金额',
  `net_sales_amount` decimal(20,6) NOT NULL DEFAULT 0
    COMMENT '负责人汇总净销售额',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_perf_rank_month_owner` (`stat_month`,`principal_name`),
  KEY `idx_ebay_perf_rank_month_gross` (`stat_month`,`gross_profit`),
  KEY `idx_ebay_perf_rank_month_net` (`stat_month`,`net_sales_amount`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay负责人月度绩效排名汇总表';

-- eBay 与 AMZ 共用绩效排名页面的查询、编辑权限。
SET @finance_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id
  LIMIT 1
);

SET @performance_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND path = 'performance-ranking'
  ORDER BY menu_id
  LIMIT 1
);

INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT ur.role_id, permissions.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN (
  SELECT @finance_menu_id AS menu_id
  UNION ALL SELECT @performance_menu_id
  UNION ALL
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @performance_menu_id
    AND perms IN (
      'finance:performanceRanking:list',
      'finance:performanceRanking:edit'
    )
) permissions ON permissions.menu_id IS NOT NULL
WHERE u.user_name = 'leiyongyu';

-- 部署校验。
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'ebay_monthly_performance_profit',
    'ebay_performance_owner_rule',
    'ebay_performance_ranking'
  )
ORDER BY TABLE_NAME;
