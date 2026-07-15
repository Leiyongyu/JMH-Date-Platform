-- 财务模块 / 外汇退税 菜单与 leiyongyu 权限。可重复执行。

-- 1. 顶级目录：财务模块
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

-- 2. 页面菜单：外汇退税
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税', @finance_menu_id, 1, 'export-tax-refund', 'finance/exportTaxRefund/index', NULL, 'ExportTaxRefund',
  1, 0, 'C', '0', '0', 'finance:exportTaxRefund:list', 'chart',
  'SYSTEM', NOW(), '外汇退税静态看板'
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

-- 3. 页面按钮权限：查询、导出
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

-- 4. 授权给账号 leiyongyu 当前拥有的所有角色
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @finance_menu_id,
  @export_tax_menu_id,
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:query' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:export' ORDER BY menu_id LIMIT 1)
)
WHERE u.user_name = 'leiyongyu'
  AND m.menu_id IS NOT NULL;

-- 5. 验证结果
SELECT menu_id, menu_name, parent_id, order_num, path, component, menu_type, perms, icon
FROM sys_menu
WHERE menu_id IN (
  @finance_menu_id,
  @export_tax_menu_id,
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:query' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:export' ORDER BY menu_id LIMIT 1)
)
ORDER BY parent_id, order_num, menu_id;
