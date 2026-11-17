-- Target DB: jmh_data_platform (Java ERP). Pure ASCII on purpose: Chinese text is written as UTF-8 hex literals.
-- Adds the page "Finance center > project profit statement" (group statement ebay/EU/US1/US2/US3 and the AMZ
-- store statement) with export / edit buttons (admin role only). Edit covers the hand entered items and the
-- upload of the finance eBay profit workbook. No scheduled job: AMZ figures are read from the LingXing profit
-- report that pythonAmzMonthlyProfitTask already pulls on the 7th.
-- Only inserts this module's menus and role grants; idempotent; changes nothing else.
-- Run after deploying the Java build that contains ProjectProfitController, and after
-- Date-Project/migrations/20261116_project_profit.sql has been applied to date-project. Re-login to refresh menus.
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='finance-center'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E9A1B9E79BAEE588A9E6B6A6E680BBE8A1A8' USING utf8mb4),@finance_root,4,'project-profit','finance/projectProfit/index','ProjectProfit','C','0','0',1,1,
  'finance:projectProfit:list','chart','SYSTEM',NOW(),
  CONVERT(X'E5B08FE7BB84E9A1B9E79BAEE588A9E6B6A6E8A1A8E4B88EE5BA97E993BAE7BBB4E5BAA6E588A9E6B6A6E8A1A8EFBC88E4BABAE6B091E5B881EFBC89EFBC9B414D5AE68C89E9A286E6989FE588A9E6B6A6E68AA5E8A1A8E78EB0E7AE97EFBC8C65426179E4B88AE4BCA0E8B4A2E58AA1E588A9E6B6A6E6988EE7BB86E8A1A8EFBC8CE4BABAE58A9BE58886E6918AE7AD89E6898BE5B7A5E5BD95E585A5' USING utf8mb4)
WHERE @finance_root IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:projectProfit:list');
SET @page := (SELECT menu_id FROM sys_menu WHERE perms='finance:projectProfit:list' ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'E9A1B9E79BAEE588A9E6B6A6E680BBE8A1A8E5AFBCE587BA' USING utf8mb4),@page,1,'#','F','0','0',1,0,'finance:projectProfit:export','#','SYSTEM',NOW()
WHERE @page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:projectProfit:export');
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'E9A1B9E79BAEE588A9E6B6A6E680BBE8A1A8E5BD95E585A5E4B88EE4B88AE4BCA0' USING utf8mb4),@page,2,'#','F','0','0',1,0,'finance:projectProfit:edit','#','SYSTEM',NOW()
WHERE @page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:projectProfit:edit');
SET @export_btn := (SELECT menu_id FROM sys_menu WHERE perms='finance:projectProfit:export' ORDER BY menu_id LIMIT 1);
SET @edit_btn := (SELECT menu_id FROM sys_menu WHERE perms='finance:projectProfit:edit' ORDER BY menu_id LIMIT 1);

-- Admin role only: drop this module's grants of other roles, then grant finance root, page and buttons to admin.
DELETE rm FROM sys_role_menu rm
JOIN sys_role r ON r.role_id=rm.role_id
WHERE rm.menu_id IN (@page,@export_btn,@edit_btn) AND r.role_key<>'admin';

INSERT INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_menu m ON m.menu_id IN (@finance_root,@page,@export_btn,@edit_btn)
WHERE r.role_key='admin' AND r.del_flag='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id);
COMMIT;

SELECT menu_id,parent_id,order_num,perms FROM sys_menu WHERE perms LIKE 'finance:projectProfit:%' ORDER BY menu_id;
