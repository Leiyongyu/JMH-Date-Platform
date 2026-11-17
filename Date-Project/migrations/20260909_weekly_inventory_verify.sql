-- 只读验收；本脚本不拉取、不修改任何业务数据。
USE `date-project`;
-- 1. 五张表、列数：34 / 10 / 23 / 39 / 14（执行10后仓位由22变23；含自动生成辅助键）。
SELECT TABLE_NAME,COUNT(*) column_count FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME IN
 ('ods_lingxing_inventory_detail_weekly','ods_lingxing_inventory_age_bucket_weekly',
  'ods_lingxing_inventory_bin_detail_weekly','ods_lingxing_product_info_weekly','ops_weekly_export_file')
GROUP BY TABLE_NAME;
-- 2. 四个唯一索引必须包含 sync_batch_id；旧日期唯一键会阻止同日重跑。
SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) index_columns
FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='date-project'
 AND INDEX_NAME IN ('uk_inv_week','uk_age_week','uk_bin_week','uk_prod_week')
GROUP BY TABLE_NAME,INDEX_NAME;
-- 3. 产品型号>=1000、仓位产品名存在。
SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='date-project'
 AND ((TABLE_NAME='ods_lingxing_product_info_weekly' AND COLUMN_NAME='model')
 OR (TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly' AND COLUMN_NAME='product_name'));
-- 4. 仓库字典可读取且 wid 唯一（第二条应0行）。
SELECT COUNT(*) warehouse_count FROM `jmh_data_platform`.warehouse;
SELECT wid,COUNT(*) n FROM `jmh_data_platform`.warehouse GROUP BY wid HAVING COUNT(*)>1;
-- 5. 文件状态与批次留底；RUNNING长时间不结束需查日志，不能只看文件是否存在。
SELECT id,snapshot_date,sync_batch_id,file_name,status,row_count,column_count,file_size,error_message
FROM ops_weekly_export_file WHERE export_code='weekly_inventory_bin' ORDER BY id DESC LIMIT 20;
-- 6. 各成功批次必须对应库存、产品快照；0行说明尚未生成，不代表失败。
SELECT f.sync_batch_id,f.row_count,
 (SELECT COUNT(*) FROM ods_lingxing_inventory_detail_weekly i WHERE i.sync_batch_id=f.sync_batch_id) inventory_rows,
 (SELECT COUNT(*) FROM ods_lingxing_product_info_weekly p WHERE p.sync_batch_id=f.sync_batch_id) product_rows
FROM ops_weekly_export_file f WHERE f.export_code='weekly_inventory_bin' AND f.status='SUCCESS'
ORDER BY f.id DESC LIMIT 10;
-- 7. 批次内库存主键重复：应0行。不要按日期分组把不同批次误判为重复。
SELECT sync_batch_id,wid,product_id,seller_id,COUNT(*) n
FROM ods_lingxing_inventory_detail_weekly GROUP BY sync_batch_id,wid,product_id,seller_id HAVING COUNT(*)>1;
-- 8. 两套任务登记：Java决定周一调度；Python enabled=0仍支持内部手动执行。
SELECT task_code,enabled,last_run_at FROM scheduler_task WHERE task_code='weekly_inventory_bin_export';
SELECT run_id,status,started_at,completed_at,error_message FROM scheduler_task_run
WHERE task_code='weekly_inventory_bin_export' ORDER BY started_at DESC LIMIT 10;
SELECT job_id,job_name,invoke_target,cron_expression,status FROM `jmh_data_platform`.sys_job
WHERE invoke_target='pythonWeeklyInventoryTask.runWeekly()';
SELECT menu_id,parent_id,menu_type,perms FROM `jmh_data_platform`.sys_menu WHERE perms='sop:weeklyInventory:use';
