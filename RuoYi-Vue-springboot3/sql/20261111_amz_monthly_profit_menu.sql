-- Target DB: jmh_data_platform (Java ERP). Pure ASCII on purpose: Chinese text is written as UTF-8 hex literals.
-- Adds the page "Finance center > AMZ monthly profit statement" with export / edit buttons (admin role only),
-- and the Quartz job that pulls the previous month every 7th at 06:00 (pythonAmzMonthlyProfitTask).
-- Only inserts / aligns this module's menus, role grants and one sys_job; idempotent; changes nothing else.
-- Run after deploying the Java build that contains AmzMonthlyProfitController and pythonAmzMonthlyProfitTask,
-- and after 20261111_amz_monthly_profit.sql has been applied to date-project. Re-login to refresh menus.
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='finance-center'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'414D5AE69C88E5BAA6E588A9E6B6A6E8A1A8' USING utf8mb4),@finance_root,3,'amz-monthly-profit','finance/amzMonthlyProfit/index','AmzMonthlyProfit','C','0','0',1,1,
  'finance:amzMonthlyProfit:list','money','SYSTEM',NOW(),
  CONVERT(X'414D5AE5BA97E993BAE588A9E6B6A6E4B88EE5B08FE7BB84E588A9E6B6A6EFBC88E4BABAE6B091E5B881EFBC8CE7BB93E7AE97E58FA3E5BE84EFBC89EFBC8CE6AF8FE69C8837E697A5E887AAE58AA8E68B89E58F96E9A286E6989FE588A9E6B6A6E68AA5E8A1A8' USING utf8mb4)
WHERE @finance_root IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:amzMonthlyProfit:list');
SET @page := (SELECT menu_id FROM sys_menu WHERE perms='finance:amzMonthlyProfit:list' ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'414D5AE69C88E5BAA6E588A9E6B6A6E8A1A8E5AFBCE587BA' USING utf8mb4),@page,1,'#','F','0','0',1,0,'finance:amzMonthlyProfit:export','#','SYSTEM',NOW()
WHERE @page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:amzMonthlyProfit:export');
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'414D5AE69C88E5BAA6E588A9E6B6A6E8A1A8E8A1A5E58585E8B4B9E794A8E7BBB4E68AA4' USING utf8mb4),@page,2,'#','F','0','0',1,0,'finance:amzMonthlyProfit:edit','#','SYSTEM',NOW()
WHERE @page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:amzMonthlyProfit:edit');
SET @export_btn := (SELECT menu_id FROM sys_menu WHERE perms='finance:amzMonthlyProfit:export' ORDER BY menu_id LIMIT 1);
SET @edit_btn := (SELECT menu_id FROM sys_menu WHERE perms='finance:amzMonthlyProfit:edit' ORDER BY menu_id LIMIT 1);

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

INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT CONVERT(X'414D5AE69C88E5BAA6E588A9E6B6A6E8A1A8E695B0E68DAEE68B89E58F96' USING utf8mb4),'DATA_CENTER','pythonAmzMonthlyProfitTask.syncPreviousMonth()','0 0 6 7 * ?',
  '2','1','0','SYSTEM',NOW(),
  CONVERT(X'E6AF8FE69C8837E697A530363A3030E68B89E58F96E4B88AE4B8AAE5AE8CE695B4E887AAE784B6E69C88E9A286E6989FE588A9E6B6A6E68AA5E8A1A8EFBC884D534B55E4B88EE5BA97E993BAEFBC8CE7BB93E7AE97E58FA3E5BE84EFBC8CE4BABAE6B091E5B881EFBC89EFBC8CE695B4E69C88E69BBFE68DA2EFBC9BE68C89E69C80E696B0E695B0E9878DE587BAE69F90E69C88E794A820707974686F6E416D7A4D6F6E74686C7950726F6669745461736B2E73796E634D6F6E74682827323032362D30392729' USING utf8mb4)
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonAmzMonthlyProfitTask.syncPreviousMonth()');
COMMIT;

SELECT menu_id,perms FROM sys_menu WHERE perms LIKE 'finance:amzMonthlyProfit:%' ORDER BY menu_id;
SELECT job_id,invoke_target,cron_expression,status FROM sys_job WHERE invoke_target LIKE 'pythonAmzMonthlyProfitTask.%';
