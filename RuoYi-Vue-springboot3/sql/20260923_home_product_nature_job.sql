-- ERP库执行。沿用原月末任务，不新建第二个重复采集任务。
-- 必须先部署新Python、Java代码，并建好Python库两张新表及原SKU月合计表。
-- 已有任务的启停、cron等管理员配置全部保留。
USE jmh_data_platform;
INSERT INTO sys_job
  (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '首页在售SKU月度快照','SYSTEM','homeInventorySkuTask.captureMonthly()',
       '0 50 23 L * ?','3','1','0','SYSTEM',NOW(),
       '月末23:50发布新老品汇总明细及原SKU合计；AMZ覆盖当月，eBay首次成功冻结；不拉外部接口、不补历史'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target IN ('homeInventorySkuTask.captureMonthly()', 'homeInventorySkuTask.captureMonthly')
);

SELECT job_id,job_name,invoke_target,cron_expression,status,misfire_policy,concurrent
FROM sys_job
WHERE invoke_target IN ('homeInventorySkuTask.captureMonthly()', 'homeInventorySkuTask.captureMonthly');
