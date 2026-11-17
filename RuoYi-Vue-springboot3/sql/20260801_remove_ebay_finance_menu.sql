-- 财务旧代码下线收尾：
-- 1. 确保绩效排名、滞销清货 Quartz 任务使用当前 Python 桥接器；
-- 2. 下线独立“eBay财务”页面，清理若依菜单和角色关联。
-- 不删除绩效排名中的 eBay 功能，也不删除任何业务数据表。
-- 可重复执行。

USE `jmh_data_platform`;

START TRANSACTION;

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
    remark = 'Java Quartz调度；Python执行AMZ利润ODS/DWD/DWS及绩效排名'
WHERE job_id = 240
  AND invoke_target IN (
    'operationSyncTask.syncAmzMonthlyOrderProfit',
    'operationSyncTask.syncAmzMonthlyOrderProfit()',
    'pythonPerformanceTask.syncPreviousMonth',
    'pythonPerformanceTask.syncPreviousMonth()'
  );

UPDATE sys_job
SET job_name = '领星-Amazon FBA库存库龄同步',
    job_group = 'FINANCE',
    invoke_target = 'pythonFbaInventoryTask.syncCurrentMonth()',
    cron_expression = '0 30 22 1 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java Quartz调度；Python执行FBA库存ODS/DWD/DWS，每月1日22:30'
WHERE job_id = 241
  AND invoke_target IN (
    'operationSyncTask.syncAmzFbaInventorySnapshot',
    'operationSyncTask.syncAmzFbaInventorySnapshot()',
    'pythonFbaInventoryTask.syncCurrentMonth',
    'pythonFbaInventoryTask.syncCurrentMonth()'
  );

CREATE TEMPORARY TABLE IF NOT EXISTS tmp_ebay_finance_menu_ids (
  menu_id BIGINT PRIMARY KEY
);
TRUNCATE TABLE tmp_ebay_finance_menu_ids;

INSERT IGNORE INTO tmp_ebay_finance_menu_ids (menu_id)
SELECT menu_id
FROM sys_menu
WHERE path = 'ebay-finance'
   OR component = 'finance/ebayFinance/index'
   OR perms LIKE 'finance:ebayFinance:%';

DELETE rm
FROM sys_role_menu rm
JOIN tmp_ebay_finance_menu_ids x ON x.menu_id = rm.menu_id;

DELETE m
FROM sys_menu m
JOIN tmp_ebay_finance_menu_ids x ON x.menu_id = m.menu_id;

DROP TEMPORARY TABLE tmp_ebay_finance_menu_ids;

COMMIT;

SELECT menu_id, menu_name, path, component, perms
FROM sys_menu
WHERE path = 'ebay-finance'
   OR component = 'finance/ebayFinance/index'
   OR perms LIKE 'finance:ebayFinance:%';
