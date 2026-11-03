-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：新增「财务中心 > AMZ利润报表」页面菜单及导出按钮，以及每月7日05:00的数据拉取 Quartz 任务。
-- 权限：页面和导出只授予 role_key='admin' 的管理员角色；本模块两个菜单上的其他角色授权会被移除。
-- 安全性：只插入/对齐本模块的菜单、授权和一条 sys_job，不改其他菜单、任务和业务数据；可重复执行。
-- 需在部署包含 AmzProfitReportController、pythonAmzProfitReportTask 的新版 Java 后执行；执行后重启 Java 并重新登录刷新菜单。
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND path='finance-center'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time,remark)
SELECT 'AMZ利润报表',@finance_root,2,'amz-profit-report','finance/amzProfitReport/index','AmzProfitReport','C','0','0',1,1,
  'finance:amzProfitReport:list','money','SYSTEM',NOW(),'AMZ店铺/个人维度结算利润、订单毛利润与业绩目标达成（USD）'
WHERE @finance_root IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:amzProfitReport:list');
SET @amz_profit_page := (
  SELECT menu_id FROM sys_menu WHERE perms='finance:amzProfitReport:list' ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT 'AMZ利润报表导出',@amz_profit_page,1,'#','F','0','0',1,0,'finance:amzProfitReport:export','#','SYSTEM',NOW()
WHERE @amz_profit_page IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:amzProfitReport:export');
SET @amz_profit_export := (
  SELECT menu_id FROM sys_menu WHERE perms='finance:amzProfitReport:export' ORDER BY menu_id LIMIT 1
);

-- 只有管理员角色可见：先清掉本模块菜单上非管理员的授权，再给管理员角色补齐财务中心目录、页面和导出。
DELETE rm FROM sys_role_menu rm
JOIN sys_role r ON r.role_id=rm.role_id
WHERE rm.menu_id IN (@amz_profit_page,@amz_profit_export) AND r.role_key<>'admin';

INSERT INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_menu m ON m.menu_id IN (@finance_root,@amz_profit_page,@amz_profit_export)
WHERE r.role_key='admin' AND r.del_flag='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id);

INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'AMZ利润报表数据拉取','DATA_CENTER','pythonAmzProfitReportTask.syncPreviousMonth()','0 0 5 7 * ?',
  '2','1','0','SYSTEM',NOW(),
  '每月7日05:00拉取上个完整自然月领星利润统计（店铺、MSKU，结算口径）与订单利润（MSKU，订单口径），USD；补跑用 pythonAmzProfitReportTask.syncMonth(''2026-09'')'
WHERE NOT EXISTS(
  SELECT 1 FROM sys_job WHERE invoke_target IN (
    'pythonAmzProfitReportTask.syncPreviousMonth','pythonAmzProfitReportTask.syncPreviousMonth()'
  )
);
COMMIT;
