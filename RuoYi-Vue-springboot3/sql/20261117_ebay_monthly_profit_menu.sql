-- Target DB: jmh_data_platform (Java ERP). Pure ASCII on purpose: Chinese text is written as UTF-8 hex literals.
-- Adds the page "Finance center > eBay monthly profit statement" with export / edit buttons (admin role only),
-- and two Quartz jobs on the 7th, before the AMZ monthly profit job (06:00):
--   05:00 pythonEbayMonthlyProfitTask.syncGoodcangBillPreviousMonth()   GoodCang bills of the eBay account
--   05:30 pythonEbayMonthlyProfitTask.syncEbayFinancePreviousMonth()    eBay Finances transactions of all stores
-- Only inserts this module's menus, role grants and two sys_job rows; idempotent; changes nothing else.
-- Run after deploying the Java build that contains EbayMonthlyProfitController and pythonEbayMonthlyProfitTask,
-- and after 20261117_ebay_monthly_profit.sql has been applied to date-project. Re-login to refresh menus.
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='finance-center'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A8' USING utf8mb4),@finance_root,4,'ebay-monthly-profit','finance/ebayMonthlyProfit/index','EbayMonthlyProfit','C','0','0',1,1,
  'finance:ebayMonthlyProfit:list','money','SYSTEM',NOW(),
  CONVERT(X'65426179E7AB99E782B9E6B187E680BBE38081E4B8AAE4BABAE588A9E6B6A6E38081E5BA97E993BAE588A9E6B6A6EFBC88E4BABAE6B091E5B881EFBC8CE4BAA4E69893E68C89E5A4AAE5B9B3E6B48BE697B6E997B4E58887E69C88EFBC89EFBC8CE6AF8FE69C8837E697A5E887AAE58AA8E68B89E58F9665426179E4BAA4E69893E6B581E6B0B4E4B88EE8B0B7E4BB93E8B4A6E58D95' USING utf8mb4)
WHERE @finance_root IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:ebayMonthlyProfit:list');
SET @page := (SELECT menu_id FROM sys_menu WHERE perms='finance:ebayMonthlyProfit:list' ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A8E5AFBCE587BA' USING utf8mb4),@page,1,'#','F','0','0',1,0,'finance:ebayMonthlyProfit:export','#','SYSTEM',NOW()
WHERE @page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:ebayMonthlyProfit:export');
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A8E6B187E78E87E4B88EE8A1A5E58585E8B4B9E794A8E7BBB4E68AA4' USING utf8mb4),@page,2,'#','F','0','0',1,0,'finance:ebayMonthlyProfit:edit','#','SYSTEM',NOW()
WHERE @page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:ebayMonthlyProfit:edit');
SET @export_btn := (SELECT menu_id FROM sys_menu WHERE perms='finance:ebayMonthlyProfit:export' ORDER BY menu_id LIMIT 1);
SET @edit_btn := (SELECT menu_id FROM sys_menu WHERE perms='finance:ebayMonthlyProfit:edit' ORDER BY menu_id LIMIT 1);

-- Admin role only, same as the AMZ monthly profit statement.
INSERT INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_menu m ON m.menu_id IN (@finance_root,@page,@export_btn,@edit_btn)
WHERE r.role_key='admin' AND r.del_flag='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id);

INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A82DE8B0B7E4BB93E8B4A6E58D95E68B89E58F96' USING utf8mb4),'DATA_CENTER','pythonEbayMonthlyProfitTask.syncGoodcangBillPreviousMonth()','0 0 5 7 * ?',
  '2','1','0','SYSTEM',NOW(),CONVERT(X'E6AF8FE69C8837E697A530353A3030E68B89E58F96E4B88AE4B8AAE69C88E8B0B7E4BB9365426179E8B4A6E688B7284143473130363435303229E8B4A6E58D95E8B4B9E794A8E6988EE7BB86EFBC8CE695B4E69C88E69BBFE68DA2EFBC9BE9878DE587BAE69F90E69C88E794A820707974686F6E456261794D6F6E74686C7950726F6669745461736B2E73796E63476F6F6463616E6742696C6C4D6F6E74682827323032362D31302729' USING utf8mb4)
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonEbayMonthlyProfitTask.syncGoodcangBillPreviousMonth()');
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A82DE4BAA4E69893E6B581E6B0B4E68B89E58F96' USING utf8mb4),'DATA_CENTER','pythonEbayMonthlyProfitTask.syncEbayFinancePreviousMonth()','0 30 5 7 * ?',
  '2','1','0','SYSTEM',NOW(),CONVERT(X'E6AF8FE69C8837E697A530353A3330E68B89E58F96E4B88AE4B8AAE69C88E585A8E983A865426179E5BA97E993BA46696E616E636573E4BAA4E69893E6B581E6B0B4EFBC88E5A4AAE5B9B3E6B48BE697B6E997B4E58887E69C88EFBC89EFBC8CE68C89E5BA97E695B4E69C88E69BBFE68DA2EFBC9BE9878DE587BAE69F90E69C88E794A820707974686F6E456261794D6F6E74686C7950726F6669745461736B2E73796E634562617946696E616E63654D6F6E74682827323032362D31302729' USING utf8mb4)
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonEbayMonthlyProfitTask.syncEbayFinancePreviousMonth()');
COMMIT;

SELECT menu_id,perms FROM sys_menu WHERE perms LIKE 'finance:ebayMonthlyProfit:%' ORDER BY menu_id;
SELECT job_id,invoke_target,cron_expression,status FROM sys_job WHERE invoke_target LIKE 'pythonEbayMonthlyProfitTask.%';
