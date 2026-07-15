-- 将部署机 sys_job 替换为当前最新调度方案。
-- 执行建议：停止后端 -> 执行本脚本 -> 启动后端，让 Quartz 从数据库重新加载任务。
-- 规则：旧 operationSyncTask 单接口任务保留但暂停；新 chainSyncTask 六条链路任务启用。

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1) 执行前自动备份一次。若重复执行，不覆盖第一次备份。
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.TABLES
   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sys_job_backup_before_chain') = 0,
  'CREATE TABLE sys_job_backup_before_chain AS SELECT * FROM sys_job',
  'SELECT ''skip backup sys_job_backup_before_chain'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2) 暂停旧的单接口运营同步任务，保留页面手动补跑能力。
UPDATE sys_job
SET status = '1',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = CONCAT(IFNULL(remark, ''), IF(INSTR(IFNULL(remark, ''), '；已切换为链路调度，自动任务暂停') > 0, '', '；已切换为链路调度，自动任务暂停'))
WHERE job_group = 'OPERATION'
  AND invoke_target LIKE 'operationSyncTask.%';

-- 3) 清理错误格式/重复链路任务，只保留带 () 的标准格式。
DELETE FROM sys_job
WHERE invoke_target IN (
  'operationSyncTask.runBaseChain',
  'operationSyncTask.runEbayChain',
  'operationSyncTask.runAmzChain',
  'operationSyncTask.runFbaChain',
  'operationSyncTask.runStockOrderChain',
  'operationSyncTask.runGoodcangChain'
);

-- 4) 插入/更新 6 条最新链路任务。
INSERT INTO sys_job (
  job_id, job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, update_by, update_time, remark
)
VALUES
  (225, '基础链路同步', 'OPERATION', 'operationSyncTask.runBaseChain()', '0 0 0 * * ?', '1', '0', '0', 'SYSTEM', NOW(), 'SYSTEM', NOW(), '每天00:00 店铺→仓库→产品管理'),
  (226, 'eBay链路同步', 'OPERATION', 'operationSyncTask.runEbayChain()', '0 30 0 * * ?', '1', '0', '0', 'SYSTEM', NOW(), 'SYSTEM', NOW(), '每天00:30 刊登→库存→流水→补货→跟价'),
  (227, 'AMZ补货链路同步', 'OPERATION', 'operationSyncTask.runAmzChain()', '0 0 1 * * ?', '1', '0', '0', 'SYSTEM', NOW(), 'SYSTEM', NOW(), '每天01:00 刊登→利润→补货建议→库存→快照'),
  (228, 'FBA链路同步', 'OPERATION', 'operationSyncTask.runFbaChain()', '0 30 1 * * ?', '1', '0', '0', 'SYSTEM', NOW(), 'SYSTEM', NOW(), '每天01:30 货件→装箱信息'),
  (229, '备货单链路同步', 'OPERATION', 'operationSyncTask.runStockOrderChain()', '0 0 2 * * ?', '1', '0', '0', 'SYSTEM', NOW(), 'SYSTEM', NOW(), '每天02:00 备货单号→备货单详情'),
  (230, '谷仓链路同步', 'OPERATION', 'operationSyncTask.runGoodcangChain()', '0 30 2 * * ?', '1', '0', '0', 'SYSTEM', NOW(), 'SYSTEM', NOW(), '每天02:30 仓库→商品→入库单→入库详情')
ON DUPLICATE KEY UPDATE
  job_name = VALUES(job_name),
  job_group = VALUES(job_group),
  invoke_target = VALUES(invoke_target),
  cron_expression = VALUES(cron_expression),
  misfire_policy = VALUES(misfire_policy),
  concurrent = VALUES(concurrent),
  status = VALUES(status),
  update_by = VALUES(update_by),
  update_time = VALUES(update_time),
  remark = VALUES(remark);

-- 5) 如果部署库里已存在同 invoke_target 但 job_id 不同的重复链路任务，保留 225-230，删除重复项。
DELETE j
FROM sys_job j
JOIN sys_job k
  ON j.invoke_target = k.invoke_target
 AND j.job_id > k.job_id
WHERE j.invoke_target LIKE 'operationSyncTask.%';

SET FOREIGN_KEY_CHECKS = 1;

-- 6) 验证结果。
SELECT job_id, job_name, job_group, invoke_target, cron_expression, concurrent, status, remark
FROM sys_job
WHERE job_group = 'OPERATION'
ORDER BY job_id;

