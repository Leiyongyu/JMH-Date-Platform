-- 仓位库存明细周报：菜单权限 + Quartz。只插缺失配置，不覆盖人工调度/授权。
-- 先执行 Date-Project/migrations/20260909_weekly_inventory.sql。
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;
SET @weekly_parent := (SELECT menu_id FROM sys_menu
  WHERE perms='sop:scriptTools:view' AND menu_type='C' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu
 (menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,
  menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '仓位库存明细周报',@weekly_parent,5,'',NULL,NULL,'',1,0,
 'F','0','0','sop:weeklyInventory:use','#','SYSTEM',NOW(),'周报列表、生成、下载；Java代理逐次鉴权'
WHERE @weekly_parent IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='sop:weeklyInventory:use');
-- 不自动给所有角色授权。在系统管理-角色管理勾选本按钮及脚本菜单权限。
INSERT INTO sys_job
 (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,
  create_by,create_time,remark)
SELECT '仓位库存明细周报','DEFAULT','pythonWeeklyInventoryTask.runWeekly()',
 '0 30 7 ? * MON','2','1','0','SYSTEM',NOW(),
 '全仓实时周快照；周一07:30；旧文件及旧批次永久保留；运行可能超过十分钟'
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonWeeklyInventoryTask.runWeekly()');
COMMIT;
SELECT IF(@weekly_parent IS NULL,'错误：未找到脚本菜单，需先部署脚本工作台再重跑本脚本','脚本菜单父级已找到') AS result;
SELECT menu_id,parent_id,menu_name,perms FROM sys_menu WHERE perms='sop:weeklyInventory:use';
SELECT job_id,job_name,invoke_target,cron_expression,status FROM sys_job WHERE invoke_target='pythonWeeklyInventoryTask.runWeekly()';

-- 第二个库单独提交，避免跨库缺表导致第一段未提交。
USE `date-project`;
START TRANSACTION;
INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
VALUES ('weekly_inventory_bin_export','仓位库存明细周报','0 30 7 ? * MON',0,
 '由Java Quartz调度，Python登记默认禁用以避免双调度；支持手动执行；只拉实时数据，不补历史日期')
ON DUPLICATE KEY UPDATE task_code=VALUES(task_code);
COMMIT;
SELECT task_code,task_name,enabled,last_run_at FROM scheduler_task WHERE task_code='weekly_inventory_bin_export';
