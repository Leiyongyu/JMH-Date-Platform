-- 6 条同步链路 Quartz 任务。可重复执行：已存在 invoke_target 时跳过。
-- 旧的单接口任务建议在若依页面手动暂停，保留手动补跑入口。

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT '链路-基础数据同步', 'OPERATION', 'chainSyncTask.runBaseChain()', '0 0 0 * * ?',
       '1', '1', '0', 'SYSTEM', NOW(), '基础链路：shop_list → warehouse → product_weight'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('chainSyncTask.runBaseChain', 'chainSyncTask.runBaseChain()'));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT '链路-eBay数据同步', 'OPERATION', 'chainSyncTask.runEbayChain()', '0 30 0 * * ?',
       '1', '1', '0', 'SYSTEM', NOW(), 'eBay链路：listing → inventory → statement → replenish → tracking'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('chainSyncTask.runEbayChain', 'chainSyncTask.runEbayChain()'));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT '链路-AMZ补货数据同步', 'OPERATION', 'chainSyncTask.runAmzChain()', '0 0 1 * * ?',
       '1', '1', '0', 'SYSTEM', NOW(), 'AMZ链路：listing → profit → restock → product_inv → wh_inv → replenish'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('chainSyncTask.runAmzChain', 'chainSyncTask.runAmzChain()'));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT '链路-FBA货件数据同步', 'OPERATION', 'chainSyncTask.runFbaChain()', '0 30 1 * * ?',
       '1', '1', '0', 'SYSTEM', NOW(), 'FBA链路：shipment → box'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('chainSyncTask.runFbaChain', 'chainSyncTask.runFbaChain()'));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT '链路-备货单数据同步', 'OPERATION', 'chainSyncTask.runStockOrderChain()', '0 0 2 * * ?',
       '1', '1', '0', 'SYSTEM', NOW(), '备货单链路：stock_order → stock_order_detail'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('chainSyncTask.runStockOrderChain', 'chainSyncTask.runStockOrderChain()'));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT '链路-谷仓数据同步', 'OPERATION', 'chainSyncTask.runGoodcangChain()', '0 30 2 * * ?',
       '1', '1', '0', 'SYSTEM', NOW(), '谷仓链路：warehouse → product → grn_list → grn_detail'
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE invoke_target IN ('chainSyncTask.runGoodcangChain', 'chainSyncTask.runGoodcangChain()'));
