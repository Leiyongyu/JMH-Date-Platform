-- STA 发货链路定时任务
-- 依赖表结构脚本：20260727_lingxing_sta_inbound_plan.sql
-- 执行策略：
--   1. lingxing_sta_inbound_plan 为空：同步今天起最近一年；
--   2. 表中已有数据：同步今天及前两天（最近3个自然日）；
--   3. 每天凌晨03:00执行，禁止并发，默认启用。

UPDATE `sys_job`
SET `job_name` = 'STA发货链路同步',
    `job_group` = 'OPERATION',
    `invoke_target` = 'operationSyncTask.runStaShipmentChain()',
    `cron_expression` = '0 0 3 * * ?',
    `misfire_policy` = '1',
    `concurrent` = '1',
    `status` = '0',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = 'STA发货链路：空表同步最近一年，非空同步最近3个自然日；每天03:00执行'
WHERE `invoke_target` IN (
  'operationSyncTask.runStaShipmentChain',
  'operationSyncTask.runStaShipmentChain()',
  'chainSyncTask.runStaShipmentChain',
  'chainSyncTask.runStaShipmentChain()'
);

INSERT INTO `sys_job` (
  `job_name`, `job_group`, `invoke_target`, `cron_expression`,
  `misfire_policy`, `concurrent`, `status`,
  `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
  'STA发货链路同步',
  'OPERATION',
  'operationSyncTask.runStaShipmentChain()',
  '0 0 3 * * ?',
  '1',
  '1',
  '0',
  'SYSTEM',
  NOW(),
  'SYSTEM',
  NOW(),
  'STA发货链路：空表同步最近一年，非空同步最近3个自然日；每天03:00执行'
WHERE NOT EXISTS (
  SELECT 1
  FROM `sys_job`
  WHERE `invoke_target` IN (
    'operationSyncTask.runStaShipmentChain',
    'operationSyncTask.runStaShipmentChain()',
    'chainSyncTask.runStaShipmentChain',
    'chainSyncTask.runStaShipmentChain()'
  )
);

SELECT
  `job_id`, `job_name`, `invoke_target`, `cron_expression`,
  `concurrent`, `status`, `remark`
FROM `sys_job`
WHERE `invoke_target` = 'operationSyncTask.runStaShipmentChain()';
