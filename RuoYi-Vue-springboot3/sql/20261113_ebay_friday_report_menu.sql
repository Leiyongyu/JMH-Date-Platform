-- Target DB: jmh_data_platform (Java ERP). Pure ASCII: Chinese text is written as UTF-8 hex literals.
-- Adds the page "Operations / eBay / Data report / Friday data" (two weekly sheets: listing stock check and
-- overseas stock) with its export and edit buttons, and the Friday 06:00 Quartz job
-- (pull eBay listings -> pull GoodCang stock -> generate the report).
-- Depends on 20261113_ebay_data_report_menu.sql (the Data report directory) and on the Java build that contains
-- EbayFridayReportController / pythonEbayFridayReportTask; date-project migration 20261113_ebay_friday_report.sql
-- must run first. Grants go to every role that can see the Data report directory.
-- Idempotent: menus are located by component / perms, the job by invoke_target. Writes only sys_menu,
-- sys_role_menu and sys_job; nothing is deleted. Restart Java so Quartz loads the job; users re-login for the menu.
USE jmh_data_platform;
SET NAMES utf8mb4;

SET @operations_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='operations' ORDER BY menu_id LIMIT 1);
SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(path)='ebay'
  ORDER BY menu_id LIMIT 1);
SET @report_dir_id := (
  SELECT menu_id FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND path='data-report'
  ORDER BY menu_id LIMIT 1);

-- 1. Page (order 3, after eBay replenishment 2.0 and eBay inventory detail).
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E591A8E4BA94E695B0E68DAE' USING utf8mb4),@report_dir_id,3,'friday-report','operations/ebay/fridayReport/index',NULL,'EbayFridayReport',
       1,0,'C','0','0','operations:ebayFridayReport:list','chart','SYSTEM',NOW(),CONVERT(X'E6AF8FE591A8E4BA94E697A9E4B88AE887AAE58AA8E7949FE68890EFBC9AE69C89E8B4A7E697A0E8B4A7EFBC88E6AF8FE69DA1E59CA8E7BABF6C697374696E67E79A84E7AB99E782B9E38081E8B49FE8B4A3E4BABAE38081E6B5B7E5A496E4BB93E5AE9EE99985E5BA93E5AD98E38081E8A784E58892E7AB99E782B9E588A4E696ADEFBC89E4B88EE6B5B7E5A496E4BB93E5BA93E5AD98EFBC88E8B0B7E4BB93E889AFE59381E58FAFE594AEE58F8AE59084E5BA97E993BAE993BEE68EA5EFBC89' USING utf8mb4)
WHERE @report_dir_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='operations/ebay/fridayReport/index');
SET @page_id := (SELECT menu_id FROM sys_menu WHERE component='operations/ebay/fridayReport/index' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@report_dir_id,update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@page_id AND @report_dir_id IS NOT NULL AND parent_id<>@report_dir_id;

-- 2. Buttons: export; edit = maintain store main sites and regenerate from the current snapshots.
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E5AFBCE587BA' USING utf8mb4),@page_id,1,'',NULL,NULL,'',1,0,'F','0','0','operations:ebayFridayReport:export','#','SYSTEM',NOW(),NULL
WHERE @page_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='operations:ebayFridayReport:export');
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E7BBB4E68AA4E5BA97E993BAE4B8BBE7AB99E782B9E4B88EE9878DE696B0E7949FE68890' USING utf8mb4),@page_id,2,'',NULL,NULL,'',1,0,'F','0','0','operations:ebayFridayReport:edit','#',
       'SYSTEM',NOW(),NULL
WHERE @page_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='operations:ebayFridayReport:edit');
SET @export_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayFridayReport:export' ORDER BY menu_id LIMIT 1);
SET @edit_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayFridayReport:edit' ORDER BY menu_id LIMIT 1);

-- 3. Grants: every role that can see the Data report directory gets the page and both buttons.
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT d.role_id,target.menu_id
FROM sys_role_menu d
JOIN (SELECT @page_id AS menu_id UNION ALL SELECT @export_id UNION ALL SELECT @edit_id) target
  ON target.menu_id IS NOT NULL
WHERE d.menu_id=@report_dir_id;

-- 4. Quartz job: every Friday 06:00 Beijing time.
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT CONVERT(X'65426179E591A8E4BA94E695B0E68DAEE6AF8FE591A8E7949FE68890' USING utf8mb4),'DATA_CENTER','pythonEbayFridayReportTask.runWeekly()','0 0 6 ? * FRI','3','1','0','SYSTEM',NOW(),
       CONVERT(X'E6AF8FE591A8E4BA94E58C97E4BAACE697B6E997B430363A3030EFBC9AE4BE9DE6ACA1E68B8965426179E59CA8E594AEE5888AE799BBE38081E8B0B7E4BB93E58CBAE59F9FE4BB93E5BA93E5AD98EFBC8CE5868DE7949FE68890E591A8E4BA94E695B0E68DAEE4B8A4E5BCA0E8A1A8E79A84E5BD93E591A8E5BFABE785A7E380826C697374696E67E5A4B1E8B4A5E695B4E4BBBBE58AA1E5A4B1E8B4A5EFBC9BE8B0B7E4BB93E5A4B1E8B4A5E58D95E78BACE5918AE8ADA6E38081E694B9E794A8E4B88AE4B880E4BBBDE8B0B7E4BB93E5BFABE785A7E38082E99C80E8A681E7AB8BE58DB3E9878DE7AE97E697B6E5AFB9E69CACE4BBBBE58AA1E689A7E8A18CE4B880E6ACA1E38082' USING utf8mb4)
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target='pythonEbayFridayReportTask.runWeekly()');

-- 5. Checks.
-- Expect 3 rows: the page (parent = Data report directory) and two buttons.
SELECT menu_id,parent_id,menu_name,order_num,path,component,menu_type,perms
FROM sys_menu WHERE menu_id IN (@page_id,@export_id,@edit_id) ORDER BY menu_type,order_num;
-- Expect 0: roles that see the directory but not the page.
SELECT COUNT(*) AS roles_missing_page FROM sys_role_menu d
LEFT JOIN sys_role_menu p ON p.role_id=d.role_id AND p.menu_id=@page_id
WHERE d.menu_id=@report_dir_id AND p.role_id IS NULL;
-- Expect 1 row, status 0.
SELECT job_id,job_name,invoke_target,cron_expression,status FROM sys_job
WHERE invoke_target='pythonEbayFridayReportTask.runWeekly()';
