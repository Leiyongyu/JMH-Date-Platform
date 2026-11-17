-- 历史脚本：库存分析看板已下线，请勿再执行本脚本。
-- 商品性质月末采集继续使用同一 Quartz 调用目标，部署请参考 20260923_home_product_nature_job.sql。
USE jmh_data_platform;
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '首页在售SKU月度快照','SYSTEM','homeInventorySkuTask.captureMonthly()',
       '0 50 23 L * ?','3','1','0','SYSTEM',NOW(),
       '月末23:50按当月负责人规则记录AMZ+eBay在售SKU；同月更新跨月保留；错过不补跑；不拉外部接口'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('homeInventorySkuTask.captureMonthly()', 'homeInventorySkuTask.captureMonthly'));
