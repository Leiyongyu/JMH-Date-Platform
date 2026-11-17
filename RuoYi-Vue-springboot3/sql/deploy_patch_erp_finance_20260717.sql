-- ============================================================
-- ERP部署补丁：财务模块/外汇退税菜单权限 + 必要字段兜底
-- 目标库：jmh_data_platform
-- 说明：
--   1. Python端 export_tax_refund 数据库表不在本脚本处理范围内。
--   2. 本脚本可重复执行。
--   3. 执行后建议 leiyongyu 重新登录，刷新前端路由权限缓存。
-- ============================================================

USE `jmh_data_platform`;

-- ============================================================
-- 1. ERP业务字段兜底：AMZ产品性质
-- 部署机当前导出已包含这些字段；这里保留幂等兜底，防止其他环境缺字段。
-- ============================================================
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_product_listing'
     AND COLUMN_NAME = 'listing_create_date') = 0,
  'ALTER TABLE amz_product_listing ADD COLUMN listing_create_date DATE NULL COMMENT ''商品创建日期，来自领星open_date_display前10位'' AFTER price',
  'SELECT ''skip amz_product_listing.listing_create_date'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_replenishment_snapshot'
     AND COLUMN_NAME = 'product_nature') = 0,
  'ALTER TABLE amz_replenishment_snapshot ADD COLUMN product_nature TINYINT NULL DEFAULT 1 COMMENT ''产品性质：1老品，2新品；按listing_create_date距离当前日期60天计算'' AFTER product_category',
  'SELECT ''skip amz_replenishment_snapshot.product_nature'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_replenishment_snapshot'
     AND INDEX_NAME = 'idx_amz_repl_product_nature') = 0,
  'ALTER TABLE amz_replenishment_snapshot ADD INDEX idx_amz_repl_product_nature (product_nature)',
  'SELECT ''skip idx_amz_repl_product_nature'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- 2. ERP业务字段兜底：外部接口同步时间 sync_time
-- 部署机当前导出已包含这些字段；这里保留幂等兜底。
-- ============================================================
DROP PROCEDURE IF EXISTS add_column_if_not_exists;
DELIMITER $$
CREATE PROCEDURE add_column_if_not_exists(
    IN p_table_name VARCHAR(128),
    IN p_column_name VARCHAR(128),
    IN p_column_def TEXT
)
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = p_table_name
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = p_table_name
          AND column_name = p_column_name
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table_name, '` ADD COLUMN `', p_column_name, '` ', p_column_def);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL add_column_if_not_exists('shop_list', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('warehouse', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('ebay_product_listing', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('warehouse_inventory_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('warehouse_statement', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('purchase_order', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('purchase_plan', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_product_listing', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_order_profit', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_restock_summary', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_product_performance_inventory', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_warehouse_inventory_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_fba_shipment', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_fba_shipment_box', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_warehouse', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_product_info', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_grn_list', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_grn_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('lingxing_product_weight', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('overseas_stock_order', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('overseas_stock_order_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');

DROP PROCEDURE IF EXISTS add_column_if_not_exists;

-- ============================================================
-- 3. 清理旧报表中心菜单与角色权限
-- ============================================================
DELETE rm
FROM sys_role_menu rm
JOIN (
  SELECT menu_id FROM (
    SELECT p.menu_id
    FROM sys_menu p
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT c.menu_id
    FROM sys_menu c
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT g.menu_id
    FROM sys_menu g
    JOIN sys_menu c ON g.parent_id = c.menu_id
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
  ) ids
) t ON t.menu_id = rm.menu_id;

DELETE m
FROM sys_menu m
JOIN (
  SELECT menu_id FROM (
    SELECT p.menu_id
    FROM sys_menu p
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT c.menu_id
    FROM sys_menu c
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT g.menu_id
    FROM sys_menu g
    JOIN sys_menu c ON g.parent_id = c.menu_id
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
  ) ids
) t ON t.menu_id = m.menu_id;

-- ============================================================
-- 4. 新增/修复：财务模块 + 外汇退税页面
-- ============================================================
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '财务模块', 0, 2, 'finance', NULL, NULL, 'Finance',
  1, 0, 'M', '0', '0', NULL, 'money',
  'SYSTEM', NOW(), '财务功能目录'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu WHERE parent_id = 0 AND path = 'finance'
);

UPDATE sys_menu
SET menu_name = '财务模块',
    order_num = 2,
    component = NULL,
    route_name = 'Finance',
    menu_type = 'M',
    visible = '0',
    status = '0',
    icon = 'money',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE parent_id = 0 AND path = 'finance';

SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id = 0 AND path = 'finance' ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税', @finance_menu_id, 1, 'export-tax-refund', 'finance/exportTaxRefund/index', NULL, 'ExportTaxRefund',
  1, 0, 'C', '0', '0', 'finance:exportTaxRefund:list', 'chart',
  'SYSTEM', NOW(), '外汇退税流程工作台'
WHERE @finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @finance_menu_id AND path = 'export-tax-refund'
  );

UPDATE sys_menu
SET menu_name = '外汇退税',
    order_num = 1,
    component = 'finance/exportTaxRefund/index',
    route_name = 'ExportTaxRefund',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'finance:exportTaxRefund:list',
    icon = 'chart',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE parent_id = @finance_menu_id AND path = 'export-tax-refund';

SET @export_tax_menu_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id = @finance_menu_id AND path = 'export-tax-refund' ORDER BY menu_id LIMIT 1
);

-- 按钮权限：查询、导入、导出、生成
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税查询', @export_tax_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:exportTaxRefund:query', '#',
  'SYSTEM', NOW(), ''
WHERE @export_tax_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:query'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税导出', @export_tax_menu_id, 2, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:exportTaxRefund:export', '#',
  'SYSTEM', NOW(), ''
WHERE @export_tax_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:export'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税导入', @export_tax_menu_id, 3, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:exportTaxRefund:import', '#',
  'SYSTEM', NOW(), ''
WHERE @export_tax_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:import'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税生成', @export_tax_menu_id, 4, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:exportTaxRefund:generate', '#',
  'SYSTEM', NOW(), ''
WHERE @export_tax_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:generate'
  );

-- 授权给账号 leiyongyu 当前拥有的所有角色。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @finance_menu_id,
  @export_tax_menu_id,
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:query' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:export' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:import' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:generate' ORDER BY menu_id LIMIT 1)
)
WHERE u.user_name = 'leiyongyu'
  AND m.menu_id IS NOT NULL;

-- ============================================================
-- 5. 验证结果
-- ============================================================
SELECT 'report_menu_remaining' AS check_item, COUNT(*) AS value
FROM sys_menu
WHERE path = 'report'
   OR component LIKE 'report/%'
   OR perms LIKE 'report:%'
   OR menu_name = '报表中心';

SELECT 'finance_export_tax_menu' AS check_item,
       menu_id, menu_name, parent_id, order_num, path, component, menu_type, perms, icon, visible, status
FROM sys_menu
WHERE menu_id IN (
  @finance_menu_id,
  @export_tax_menu_id,
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:query' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:export' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:import' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:generate' ORDER BY menu_id LIMIT 1)
)
ORDER BY parent_id, order_num, menu_id;

SELECT 'leiyongyu_permission_count' AS check_item, COUNT(*) AS value
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role_menu rm ON rm.role_id = ur.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND (
    m.path IN ('finance', 'export-tax-refund')
    OR m.perms LIKE 'finance:exportTaxRefund:%'
  );
