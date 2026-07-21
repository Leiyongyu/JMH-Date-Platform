-- eBay财务模块：export_tax_refund 业务表 + ERP 菜单权限，脚本可重复执行。

USE `export_tax_refund`;

CREATE TABLE IF NOT EXISTS `ebay_finance_import_batch` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '导入批次ID',
  `platform` varchar(32) NOT NULL COMMENT '平台，来自文件名',
  `site` varchar(64) NOT NULL COMMENT '站点，来自文件名',
  `period_start` date NOT NULL COMMENT '统计开始日期，来自文件名',
  `period_end` date NOT NULL COMMENT '统计结束日期，来自文件名',
  `file_name` varchar(255) NOT NULL COMMENT '源文件名',
  `file_hash` char(64) DEFAULT NULL COMMENT '源文件SHA-256',
  `total_rows` int NOT NULL DEFAULT 0 COMMENT '有效数据行数',
  `inserted_rows` int NOT NULL DEFAULT 0 COMMENT '新增行数',
  `updated_rows` int NOT NULL DEFAULT 0 COMMENT '覆盖行数',
  `operator` varchar(64) DEFAULT NULL COMMENT '导入账号',
  `status` varchar(20) NOT NULL DEFAULT 'SUCCESS' COMMENT '导入状态',
  `error_message` varchar(1000) DEFAULT NULL COMMENT '错误信息',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_finance_batch_period` (`platform`,`site`,`period_start`,`period_end`),
  KEY `idx_ebay_finance_batch_end` (`period_end`),
  KEY `idx_ebay_finance_batch_update` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay财务酋长利润导入批次';

CREATE TABLE IF NOT EXISTS `ebay_finance_profit` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '财务明细ID',
  `batch_id` bigint NOT NULL COMMENT '最近导入批次ID',
  `platform` varchar(32) NOT NULL COMMENT '平台',
  `site` varchar(64) NOT NULL COMMENT '站点',
  `period_start` date NOT NULL COMMENT '统计开始日期',
  `period_end` date NOT NULL COMMENT '统计结束日期',
  `sku` varchar(160) NOT NULL COMMENT 'SKU',
  `image_url` varchar(1000) DEFAULT NULL COMMENT '商品图片',
  `multi_attribute` varchar(20) DEFAULT NULL COMMENT '是否多属性',
  `order_total` decimal(20,6) DEFAULT NULL COMMENT '订单总额',
  `order_amount` decimal(20,6) DEFAULT NULL COMMENT '订单金额',
  `units_sold` int DEFAULT NULL COMMENT '售出数',
  `order_count` int DEFAULT NULL COMMENT '订单数',
  `tax_amount` decimal(20,6) DEFAULT NULL COMMENT '税费',
  `profit` decimal(20,6) DEFAULT NULL COMMENT '利润',
  `profit_margin` decimal(20,10) DEFAULT NULL COMMENT '利润率，小数',
  `product_sales_amount` decimal(20,6) DEFAULT NULL COMMENT '商品销售额',
  `shipping_revenue` decimal(20,6) DEFAULT NULL COMMENT '应收运费',
  `platform_fee` decimal(20,6) DEFAULT NULL COMMENT '平台费用',
  `payment_fee` decimal(20,6) DEFAULT NULL COMMENT '收款手续费',
  `purchase_cost` decimal(20,6) DEFAULT NULL COMMENT '采购成本',
  `first_leg_freight` decimal(20,6) DEFAULT NULL COMMENT '头程运费',
  `tail_freight` decimal(20,6) DEFAULT NULL COMMENT '尾程运费',
  `refund_amount` decimal(20,6) DEFAULT NULL COMMENT '退款金额',
  `advertising_fee` decimal(20,6) DEFAULT NULL COMMENT '广告费',
  `platform_other_fee` decimal(20,6) DEFAULT NULL COMMENT '平台其他费',
  `raw_data_json` json NOT NULL COMMENT 'Excel全部144列原始数据',
  `source_file_name` varchar(255) NOT NULL COMMENT '源文件名',
  `created_by` varchar(64) DEFAULT NULL COMMENT '创建账号',
  `updated_by` varchar(64) DEFAULT NULL COMMENT '修改账号',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_finance_period_sku` (`platform`,`site`,`period_start`,`period_end`,`sku`),
  KEY `idx_ebay_finance_sku` (`sku`),
  KEY `idx_ebay_finance_period` (`period_start`,`period_end`),
  KEY `idx_ebay_finance_site_end` (`site`,`period_end`),
  KEY `idx_ebay_finance_batch` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay财务酋长利润SKU明细';

-- 以下仅在 Java ERP 库中管理菜单和账号权限。
USE `jmh_data_platform`;

-- 财务中心目录兜底。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '财务中心', 0, 2, 'finance', NULL, NULL, 'Finance',
  1, 0, 'M', '0', '0', NULL, 'money',
  'SYSTEM', NOW(), '财务功能目录'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE parent_id = 0 AND path = 'finance'
);

SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id = 0 AND path = 'finance' ORDER BY menu_id LIMIT 1
);

-- eBay财务页面。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  'eBay财务', @finance_menu_id, 2, 'ebay-finance', 'finance/ebayFinance/index', NULL, 'EbayFinance',
  1, 0, 'C', '0', '0', 'finance:ebayFinance:list', 'chart',
  'SYSTEM', NOW(), 'eBay财务数据可视化与酋长利润导入'
WHERE @finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @finance_menu_id AND path = 'ebay-finance'
  );

UPDATE sys_menu
SET menu_name = 'eBay财务', order_num = 2, component = 'finance/ebayFinance/index',
    route_name = 'EbayFinance', is_frame = 1, is_cache = 0, menu_type = 'C',
    visible = '0', status = '0', perms = 'finance:ebayFinance:list', icon = 'chart',
    update_by = 'SYSTEM', update_time = NOW()
WHERE parent_id = @finance_menu_id AND path = 'ebay-finance';

SET @ebay_finance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id AND path = 'ebay-finance'
  ORDER BY menu_id LIMIT 1
);

-- 查询、导入、编辑按钮权限。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT 'eBay财务查询', @ebay_finance_menu_id, 1, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:ebayFinance:list', '#', 'SYSTEM', NOW(), ''
WHERE @ebay_finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @ebay_finance_menu_id AND perms = 'finance:ebayFinance:list'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT '导入酋长利润', @ebay_finance_menu_id, 2, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:ebayFinance:import', '#', 'SYSTEM', NOW(), ''
WHERE @ebay_finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @ebay_finance_menu_id AND perms = 'finance:ebayFinance:import'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT 'eBay财务编辑', @ebay_finance_menu_id, 3, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:ebayFinance:edit', '#', 'SYSTEM', NOW(), ''
WHERE @ebay_finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @ebay_finance_menu_id AND perms = 'finance:ebayFinance:edit'
  );

-- 授权给 leiyongyu 当前拥有的角色，包含目录、页面及查询/导入/编辑权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @finance_menu_id,
  @ebay_finance_menu_id,
  (SELECT menu_id FROM sys_menu WHERE parent_id = @ebay_finance_menu_id AND perms = 'finance:ebayFinance:list' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @ebay_finance_menu_id AND perms = 'finance:ebayFinance:import' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @ebay_finance_menu_id AND perms = 'finance:ebayFinance:edit' ORDER BY menu_id LIMIT 1)
)
WHERE u.user_name = 'leiyongyu' AND m.menu_id IS NOT NULL;

SELECT menu_id, menu_name, parent_id, order_num, path, component, menu_type, perms
FROM sys_menu
WHERE menu_id = @ebay_finance_menu_id OR parent_id = @ebay_finance_menu_id
ORDER BY menu_type, order_num, menu_id;
