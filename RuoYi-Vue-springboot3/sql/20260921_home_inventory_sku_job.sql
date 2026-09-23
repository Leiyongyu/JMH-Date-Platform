-- 在ERP库执行：只新增缺失任务，不覆盖管理员已有配置，不修改业务数据。
USE jmh_data_platform;
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '首页在售SKU月度快照','SYSTEM','homeInventorySkuTask.captureMonthly()',
       '0 50 23 L * ?','3','1','0','SYSTEM',NOW(),
       '月末23:50按当月负责人规则记录AMZ+eBay在售SKU；同月更新跨月保留；错过不补跑；不拉外部接口'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('homeInventorySkuTask.captureMonthly()', 'homeInventorySkuTask.captureMonthly'));
