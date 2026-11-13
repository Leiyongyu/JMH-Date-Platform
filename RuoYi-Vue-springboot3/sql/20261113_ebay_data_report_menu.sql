-- Target DB: jmh_data_platform (Java ERP). Pure ASCII: Chinese text is written as UTF-8 hex literals.
-- Menu change: add the directory "Operations / eBay / Data report" and move two existing pages under it:
--   eBay replenishment 2.0 (operations/ebay/replenishmentV2/index) and eBay inventory detail
--   (operations/ebay/inventoryDetail/index). Their buttons move with them (children keep parent_id).
-- Page URLs change: /operations/ebay/replenishment-v2 -> /operations/ebay/data-report/replenishment-v2,
--   /operations/ebay/inventory-detail -> /operations/ebay/data-report/inventory-detail. API paths do not change.
-- Grants: every role that can see either page also gets the new directory; otherwise non-admin users lose
--   both pages from the menu (dynamic routes are built from the root through every ancestor).
-- Idempotent: menus are located by path / component, safe to re-run. Only sys_menu / sys_role_menu are written,
--   nothing is deleted. Users must log out and in again to see the new menu.
USE jmh_data_platform;
SET NAMES utf8mb4;

SET @operations_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='operations' ORDER BY menu_id LIMIT 1);
SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(path)='ebay'
  ORDER BY menu_id LIMIT 1);
SET @replenishment_id := (
  SELECT menu_id FROM sys_menu WHERE menu_type='C' AND component='operations/ebay/replenishmentV2/index'
  ORDER BY menu_id LIMIT 1);
SET @inventory_id := (
  SELECT menu_id FROM sys_menu WHERE menu_type='C' AND component='operations/ebay/inventoryDetail/index'
  ORDER BY menu_id LIMIT 1);

-- 1. Directory "Data report" (order 4 = where eBay replenishment 2.0 used to sit).
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E695B0E68DAEE68AA5E8A1A8' USING utf8mb4),@ebay_dir_id,4,'data-report',NULL,NULL,'',
       1,0,'M','0','0','','chart','SYSTEM',NOW(),
       CONVERT(X'65426179E695B0E68DAEE68AA5E8A1A8E79BAEE5BD95EFBC9A65426179E8A1A5E8B4A7322E30E3808145626179E5BA93E5AD98E6988EE7BB86' USING utf8mb4)
WHERE @ebay_dir_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND path='data-report');
SET @report_dir_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND path='data-report'
  ORDER BY menu_id LIMIT 1);

-- 2. Move the two pages under it; replenishment first, inventory detail second. Names, routes and buttons unchanged.
UPDATE sys_menu SET parent_id=@report_dir_id,order_num=1,update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@replenishment_id AND @report_dir_id IS NOT NULL;
UPDATE sys_menu SET parent_id=@report_dir_id,order_num=2,update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@inventory_id AND @report_dir_id IS NOT NULL;

-- 3. Grant the new directory to every role that has either page.
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT role_id,@report_dir_id FROM sys_role_menu
WHERE menu_id IN (@replenishment_id,@inventory_id) AND @report_dir_id IS NOT NULL;

-- 4. Checks.
-- Expect 3 rows: the directory (parent = eBay) and the two pages (parent = the directory).
SELECT menu_id,parent_id,menu_name,order_num,path,component,menu_type
FROM sys_menu WHERE menu_id IN (@report_dir_id,@replenishment_id,@inventory_id) ORDER BY parent_id,order_num;
-- Expect 0: roles that can see a page but not the new directory.
SELECT COUNT(DISTINCT p.role_id) AS roles_missing_directory
FROM sys_role_menu p
LEFT JOIN sys_role_menu d ON d.role_id=p.role_id AND d.menu_id=@report_dir_id
WHERE p.menu_id IN (@replenishment_id,@inventory_id) AND d.role_id IS NULL;
