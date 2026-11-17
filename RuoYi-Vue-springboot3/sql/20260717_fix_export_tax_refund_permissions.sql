-- 修复 leiyongyu 外汇退税权限。
-- 说明：若用户已登录，执行后需要退出重新登录，若依登录态里的权限才会刷新。

SET @finance_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = 0 AND path = 'finance'
  ORDER BY menu_id
  LIMIT 1
);

SET @export_tax_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND path = 'export-tax-refund'
  ORDER BY menu_id
  LIMIT 1
);

-- 如果按钮权限缺失，补齐。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT '外汇退税查询', @export_tax_menu_id, 1, '', NULL, NULL, '',
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
SELECT '外汇退税导入', @export_tax_menu_id, 2, '', NULL, NULL, '',
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
SELECT '外汇退税导出', @export_tax_menu_id, 3, '', NULL, NULL, '',
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
SELECT '外汇退税生成', @export_tax_menu_id, 4, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:exportTaxRefund:generate', '#',
       'SYSTEM', NOW(), ''
WHERE @export_tax_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:generate'
  );

-- 授权给 leiyongyu 当前拥有的所有角色。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @finance_menu_id,
  @export_tax_menu_id,
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:query' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:import' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:export' ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu WHERE parent_id = @export_tax_menu_id AND perms = 'finance:exportTaxRefund:generate' ORDER BY menu_id LIMIT 1)
)
WHERE u.user_name = 'leiyongyu'
  AND m.menu_id IS NOT NULL;

-- 验证：正常应返回 query/import/export/generate 四个按钮权限。
SELECT u.user_name, r.role_key, m.menu_name, m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = r.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND m.perms LIKE 'finance:exportTaxRefund:%'
ORDER BY r.role_key, m.order_num, m.menu_id;
