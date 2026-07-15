-- 修复链路任务调用目标：使用已存在的 operationSyncTask，避免 chainSyncTask Bean 未注册导致任务失败。
UPDATE sys_job
SET invoke_target = REPLACE(invoke_target, 'chainSyncTask.', 'operationSyncTask.'),
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = CONCAT(IFNULL(remark, ''), '；已切换为operationSyncTask入口')
WHERE invoke_target LIKE 'chainSyncTask.%';

SELECT job_id, job_name, invoke_target, cron_expression, status
FROM sys_job
WHERE job_id BETWEEN 225 AND 230
ORDER BY job_id;
