-- Execute after deploying the Java task class. Repeated execution preserves job enabled/paused state.
USE `jmh_data_platform`;
START TRANSACTION;
UPDATE sys_job SET job_name='领星-AMZ刊登原始数据每周同步',
 cron_expression='0 0 10 ? * THU',invoke_target='pythonAmzListingRawTask.runWeekly()',
 misfire_policy='2',concurrent='1',update_by='SYSTEM',update_time=NOW(),
 remark='每周四北京时间10:00；服务器时区Asia/Shanghai；独立Python原始表；完整校验后原子替换，不修改旧amz_product_listing。'
WHERE invoke_target IN ('pythonAmzListingRawTask.runWeekly','pythonAmzListingRawTask.runWeekly()');
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '领星-AMZ刊登原始数据每周同步','DEFAULT','pythonAmzListingRawTask.runWeekly()',
 '0 0 10 ? * THU','2','1','0','SYSTEM',NOW(),
 '每周四北京时间10:00；服务器时区Asia/Shanghai；仅sid及分页；全量覆盖Python独立表，失败保留上批。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('pythonAmzListingRawTask.runWeekly','pythonAmzListingRawTask.runWeekly()'));
COMMIT;
SELECT job_id,job_name,invoke_target,cron_expression,status FROM sys_job
WHERE invoke_target IN ('pythonAmzListingRawTask.runWeekly','pythonAmzListingRawTask.runWeekly()');
