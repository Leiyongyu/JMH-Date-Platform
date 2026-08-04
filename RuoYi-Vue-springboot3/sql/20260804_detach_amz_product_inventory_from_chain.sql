-- 将“领星-Amazon产品表现库存”从 AMZ 补货链路拆分为独立 Quartz 任务。
-- 链路步骤由 Java 编排代码移除；本脚本只确保独立任务存在，不修改现有任务的状态和执行时间。
-- 新增任务默认暂停，由管理员在“系统监控 / 定时任务”中自行设置 Cron 后启用。

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT
  '领星-Amazon产品表现库存',
  'OPERATION',
  'operationSyncTask.syncAmzProductPerformanceInventory',
  '0 00 22 * * ?',
  '1',
  '1',
  '1',
  'SYSTEM',
  NOW(),
  '已从AMZ补货链路拆分；请单独设置执行时间并启用'
WHERE NOT EXISTS (
  SELECT 1
  FROM sys_job
  WHERE invoke_target IN (
    'operationSyncTask.syncAmzProductPerformanceInventory',
    'operationSyncTask.syncAmzProductPerformanceInventory()'
  )
);

UPDATE sys_job
SET remark = CASE
      WHEN remark LIKE '%已从AMZ补货链路拆分%'
        THEN remark
      WHEN remark IS NULL OR remark = ''
        THEN '已从AMZ补货链路拆分；请单独设置执行时间并启用'
      ELSE CONCAT(remark, '；已从AMZ补货链路拆分；请单独设置执行时间并启用')
    END,
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE invoke_target IN (
  'operationSyncTask.syncAmzProductPerformanceInventory',
  'operationSyncTask.syncAmzProductPerformanceInventory()'
);

SELECT job_id, job_name, job_group, invoke_target,
       cron_expression, status, concurrent, remark
FROM sys_job
WHERE invoke_target IN (
  'operationSyncTask.syncAmzProductPerformanceInventory',
  'operationSyncTask.syncAmzProductPerformanceInventory()'
)
ORDER BY job_id;
