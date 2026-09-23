-- 在 Java 库 jmh_data_platform 执行。价格结构改以飞书「不良交易刊登」为主表后，
-- eBay 在售刊登的每月同步已无读取方，对应的 Quartz 任务一并下线。
--
-- 只动这一个任务：「eBay密钥健康检查」保留，它盯的是凭证有效期，与拉刊登无关。
--
-- 先暂停再删除，两步都写上是为了让你能只执行第一步观察一段时间。

USE `jmh_data_platform`;

-- 第1步【只读】看清楚要动的是哪一条
SELECT job_id, job_name, invoke_target, cron_expression, status
FROM sys_job
WHERE invoke_target LIKE 'pythonEbayStoreListingTask%'
   OR invoke_target LIKE 'pythonEbayTokenHealthTask%'
   OR invoke_target LIKE 'pythonFeishuBadTransactionTask%'
ORDER BY job_name;


-- 第2步 暂停（status=1）。只想先停不想删的话，执行到这里即可。
UPDATE sys_job SET status = '1', update_by = 'SYSTEM', update_time = NOW(),
       remark = CONCAT('已下线：价格结构改用飞书不良交易刊登表，本任务无读取方。', IFNULL(remark, ''))
WHERE invoke_target LIKE 'pythonEbayStoreListingTask%';


-- 第3步 删除。Java 侧的任务类已随代码删除，留着这条会在调度时报找不到 Bean。
DELETE FROM sys_job WHERE invoke_target LIKE 'pythonEbayStoreListingTask%';


-- 第4步【只读】确认：应只剩密钥健康检查与飞书不良交易刊登
SELECT job_id, job_name, invoke_target, cron_expression, status
FROM sys_job
WHERE invoke_target LIKE 'pythonEbay%' OR invoke_target LIKE 'pythonFeishu%'
ORDER BY job_name;
