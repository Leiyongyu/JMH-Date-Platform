-- Java 数据库；不修改已有任务设置。Python迁移先执行，再部署前后端。
USE jmh_data_platform;
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '月度库存采购在途同步','DEFAULT','pythonInventoryPurchaseOrderTask.sync()',
 '0 30 8 * * ?','3','1','1','SYSTEM',NOW(),
 '每天北京时间08:30；首次全量、以后增量、每7天全量校准；只更新当前报表。首次手动核验后启用'
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonInventoryPurchaseOrderTask.sync()');
