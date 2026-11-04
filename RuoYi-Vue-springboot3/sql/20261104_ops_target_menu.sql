-- Target DB: jmh_data_platform (Java ERP). Pure ASCII: Chinese names are written as UTF-8 hex literals.
-- Adds menu "Finance Center > Ops targets & efficiency" (finance/opsTarget/index) and its edit button.
-- Only the admin role is granted; grant other roles from the role page later. Safe to re-run; touches nothing else.
-- Run after the Python migration 20261104_ops_dept_target.sql and after deploying the new Java/frontend build.
USE jmh_data_platform;
SET NAMES utf8mb4;
START TRANSACTION;

SET @finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='finance-center'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E8BF90E890A5E79BAEE6A087E4B88EE4BABAE69588' USING utf8mb4),@finance_root,3,'ops-target',
  'finance/opsTarget/index','OpsTarget','C','0','0',1,1,'finance:opsTarget:list','chart','SYSTEM',NOW(),
  CONVERT(X'E6B1BDE9858DE8BF90E890A5E983A8E997A8E5B9B4E5BAA6E79BAEE6A087E38081E5ADA3E5BAA62FE69C88E5BAA6E58886E8A7A3E4B88EE4BABAE695884B5049EFBC88E6898BE5B7A5E7BBB4E68AA4EFBC8CE98791E9A29DE58D95E4BD8DE4B887E58583EFBC89' USING utf8mb4)
WHERE @finance_root IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:opsTarget:list');
SET @ops_target_page := (
  SELECT menu_id FROM sys_menu WHERE perms='finance:opsTarget:list' ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'E8BF90E890A5E79BAEE6A087E4BFAEE694B9' USING utf8mb4),@ops_target_page,1,'#','F','0','0',1,0,
  'finance:opsTarget:edit','#','SYSTEM',NOW()
WHERE @ops_target_page IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:opsTarget:edit');
SET @ops_target_edit := (
  SELECT menu_id FROM sys_menu WHERE perms='finance:opsTarget:edit' ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_menu m ON m.menu_id IN (@finance_root,@ops_target_page,@ops_target_edit)
WHERE r.role_key='admin' AND r.del_flag='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id);
COMMIT;
