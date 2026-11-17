-- Execute after deploying the Java task class. Repeated execution preserves job enabled/paused state.
USE `jmh_data_platform`;
START TRANSACTION;
UPDATE sys_job SET job_name='eBay店铺商品信息每月同步',
 cron_expression='0 0 5 5 * ?',invoke_target='pythonEbayStoreListingTask.runMonthly()',
 misfire_policy='2',concurrent='1',update_by='SYSTEM',update_time=NOW(),
 remark='每月5日北京时间05:00；服务器时区Asia/Shanghai；按账号隔离Python原始表；所有账号校验成功后事务发布；不修改领星源表。'
WHERE invoke_target IN ('pythonEbayStoreListingTask.runMonthly','pythonEbayStoreListingTask.runMonthly()');
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'eBay店铺商品信息每月同步','DEFAULT','pythonEbayStoreListingTask.runMonthly()',
 '0 0 5 5 * ?','2','1','0','SYSTEM',NOW(),
 '每月5日北京时间05:00；服务器时区Asia/Shanghai；官方Trading在售商品；按配置账号覆盖，完整校验失败保留旧数据。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('pythonEbayStoreListingTask.runMonthly','pythonEbayStoreListingTask.runMonthly()'));
COMMIT;
SELECT job_id,job_name,invoke_target,cron_expression,status FROM sys_job
WHERE invoke_target IN ('pythonEbayStoreListingTask.runMonthly','pythonEbayStoreListingTask.runMonthly()');
