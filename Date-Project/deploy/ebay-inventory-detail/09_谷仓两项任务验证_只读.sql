-- 仅查询；应有两个不同入口，各1行。不核对固定job_id，部署机编号允许不同。
SET NAMES utf8mb4;
SELECT job_id,job_name,job_group,invoke_target,cron_expression,status,misfire_policy,concurrent
FROM jmh_data_platform.sys_job
WHERE invoke_target IN ('operationSyncTask.syncGoodcangInventoryAgeLatest()',
 'operationSyncTask.syncGoodcangInventoryAgeLatest','pythonGoodcangStorageTask.runWeekly()',
 'pythonGoodcangStorageTask.runWeekly');
SELECT task_code,task_name,enabled,cron_expression,last_run_at FROM `date-project`.scheduler_task
WHERE task_code='goodcang_wh_inventory_storage_sync';
-- 库龄latest无数据时为0行计数、时间NULL；仅执行建表SQL不会自动拉取。
SELECT COUNT(*) AS row_count,COUNT(DISTINCT sync_batch_id) AS batch_count,MAX(sync_batch_id) AS batch_id,MAX(pulled_at) AS latest_pulled_at
FROM jmh_data_platform.ods_goodcang_inventory_age_latest;
SELECT COUNT(*) AS row_count,COUNT(DISTINCT sync_batch_id) AS batch_count,MAX(sync_batch_id) AS batch_id,MAX(pulled_at) AS latest_pulled_at
FROM `date-project`.ods_goodcang_wh_inventory_storage;
SELECT COUNT(*) AS row_count,COUNT(DISTINCT sync_batch_id) AS batch_count,MAX(sync_batch_id) AS batch_id,MAX(pulled_at) AS latest_pulled_at
FROM `date-project`.ods_goodcang_wh_inventory_storage_detail;
-- 原月度任务只读对照，本补充包不会修改。
SELECT job_id,job_name,invoke_target,cron_expression,status FROM jmh_data_platform.sys_job
WHERE invoke_target IN ('operationSyncTask.syncGoodcangInventoryAge()',
 'operationSyncTask.syncGoodcangInventoryAge','pythonFbaInventoryTask.syncCurrentMonth()');
