-- Deploy the new Java Bean before enabling. JVM timezone must be Asia/Shanghai.
USE `jmh_data_platform`;
START TRANSACTION;
UPDATE sys_job SET job_name='eBay店铺密钥月末健康检查',cron_expression='0 0 9 L * ?',
 invoke_target='pythonEbayTokenHealthTask.runMonthly()',misfire_policy='3',concurrent='1',
 update_by='SYSTEM',update_time=NOW(),remark='每月最后一天北京时间09:00；逐店检查并发送完整企微群报告；不修改密钥及商品数据。'
WHERE invoke_target IN ('pythonEbayTokenHealthTask.runMonthly','pythonEbayTokenHealthTask.runMonthly()');
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'eBay店铺密钥月末健康检查','DEFAULT','pythonEbayTokenHealthTask.runMonthly()',
 '0 0 9 L * ?','3','1','0','SYSTEM',NOW(),'北京时间09:00，每月最后一天，错过跳过不补跑；完整健康报告发送既有企微告警群；无需提供邮件或密钥参数。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('pythonEbayTokenHealthTask.runMonthly','pythonEbayTokenHealthTask.runMonthly()'));
COMMIT;
SELECT job_id,job_name,cron_expression,invoke_target,status FROM sys_job
WHERE invoke_target='pythonEbayTokenHealthTask.runMonthly()';
