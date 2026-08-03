-- 2026-08-01
-- AMZ补货链路作为产品表现库存的唯一主调度入口：
-- 1. 停用原每天22:00独立拉取任务，避免同一接口每天重复执行；
-- 2. 保持AMZ补货链路启用；
-- 3. 不删除任务记录和任何业务数据，必要时可在任务管理页面重新启用。

UPDATE sys_job
SET status = '1',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = CONCAT(
        CASE WHEN remark IS NULL OR remark = '' THEN '' ELSE CONCAT(remark, '；') END,
        '2026-08-01停用：产品表现库存统一由AMZ补货链路执行'
    )
WHERE job_id = 224
   OR invoke_target IN (
       'operationSyncTask.syncAmzProductPerformanceInventory',
       'operationSyncTask.syncAmzProductPerformanceInventory()'
   );

UPDATE sys_job
SET status = '0',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE job_id = 227
   OR invoke_target IN (
       'operationSyncTask.runAmzChain',
       'operationSyncTask.runAmzChain()',
       'chainSyncTask.runAmzChain',
       'chainSyncTask.runAmzChain()'
   );

SELECT job_id, job_name, invoke_target, cron_expression, status
FROM sys_job
WHERE job_id IN (224, 227)
   OR invoke_target LIKE '%syncAmzProductPerformanceInventory%'
   OR invoke_target LIKE '%runAmzChain%'
ORDER BY job_id;
