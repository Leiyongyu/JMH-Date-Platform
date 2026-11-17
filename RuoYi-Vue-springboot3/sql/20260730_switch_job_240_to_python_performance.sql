-- 执行前置条件：
-- 1. Python迁移 20260730_scheduler_etl_observability.sql 已执行；
-- 2. Python服务和Java桥接器均已部署；
-- 3. 已手工补跑并核对同一月份的数据量及排名结果。

START TRANSACTION;

UPDATE sys_job
SET status = '1',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE job_id = 240;

UPDATE sys_job
SET job_name = 'Amazon月度完整订单利润同步',
    job_group = 'FINANCE',
    invoke_target = 'pythonPerformanceTask.syncPreviousMonth()',
    cron_expression = '0 0 22 4 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java Quartz统一调度，Python执行AMZ月利润ODS/DWD/DWS及综合排名'
WHERE job_id = 240
  AND invoke_target IN (
      'operationSyncTask.syncAmzMonthlyOrderProfit',
      'operationSyncTask.syncAmzMonthlyOrderProfit()',
      'pythonPerformanceTask.syncPreviousMonth',
      'pythonPerformanceTask.syncPreviousMonth()'
  );

COMMIT;

SELECT job_id, job_name, job_group, invoke_target, cron_expression,
       misfire_policy, concurrent, status
FROM sys_job
WHERE job_id = 240;

-- 旧 Java 本地 ETL 已移除，故障时暂停任务并在修复 Python 服务后按月补跑，
-- 不得再将 invoke_target 恢复为 operationSyncTask 旧方法。
--
-- 直接执行SQL后需重启Java服务，或在若依任务管理页面对该任务执行一次
-- “修改并保存”，使Quartz运行时配置与sys_job保持一致。
