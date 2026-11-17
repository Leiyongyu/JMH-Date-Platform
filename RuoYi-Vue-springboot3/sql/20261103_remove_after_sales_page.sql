-- 下线「数据中心 > 售后数据」页面（AMZ/eBay 售后查询、导入、导出、AMZ售后链路）。
-- 删除菜单（页面 + 4 个按钮）、角色授权和每周日 22:30 的「AMZ-SOP售后链路」定时任务。
-- 需在部署不含售后代码的新版 Java 后执行；执行后重启 Java，并让用户重新登录刷新菜单。
-- 定时任务执行日志 sys_job_log 作为历史保留，不删除。

DELETE rm FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.component = 'sop/afterSales/index'
   OR m.perms LIKE 'sop:afterSales:%';

DELETE FROM sys_menu
WHERE component = 'sop/afterSales/index'
   OR perms LIKE 'sop:afterSales:%';

DELETE FROM sys_job
WHERE invoke_target LIKE 'amzSopAfterSalesTask.%';
