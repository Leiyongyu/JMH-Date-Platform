-- 仅USE/SELECT；不拉数、不改表、不修改数据。
USE `date-project`;
-- 1. 新索引必须完整匹配，并且无前缀索引。期望OK。
SELECT CASE WHEN GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)=
 'snapshot_date,sync_batch_id,wid,whb_id,product_id,bin_identity_key'
 AND MAX(NON_UNIQUE)=0 AND SUM(SUB_PART IS NOT NULL)=0 THEN 'OK' ELSE 'ERROR' END AS index_check,
 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly' AND INDEX_NAME='uk_bin_week';
-- 2. 辅助列需为STORED GENERATED VARBINARY(1600)，业务字段/raw_json保持原样。
SELECT COLUMN_TYPE,EXTRA,COLUMN_COMMENT,GENERATION_EXPRESSION
FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly' AND COLUMN_NAME='bin_identity_key';
SELECT COUNT(*) AS bin_column_count FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly';
-- 列数由22变23；技术辅助列由数据库自动生成，不计入接口原字段。
-- 3. 完整业务键重复应返回0行。不同快照批次不算重复。
SELECT snapshot_date,sync_batch_id,wid,whb_id,product_id,HEX(bin_identity_key) identity_hex,COUNT(*) n
FROM ods_lingxing_inventory_bin_detail_weekly
GROUP BY snapshot_date,sync_batch_id,wid,whb_id,product_id,bin_identity_key HAVING COUNT(*)>1;
-- 4. 原来的三字段有多行是合法的，查看不同store_id/MSKU/FNSKU，不应自动去重。
SELECT snapshot_date,sync_batch_id,wid,whb_id,product_id,COUNT(*) detail_rows
FROM ods_lingxing_inventory_bin_detail_weekly
GROUP BY snapshot_date,sync_batch_id,wid,whb_id,product_id HAVING COUNT(*)>1
ORDER BY snapshot_date DESC LIMIT 20;
-- 5. 核验出错样例所在批次；没有新快照时0行正常。不要拿旧失败任务当新结果。
SELECT snapshot_date,sync_batch_id,wid,whb_id,product_id,store_id,msku,fnsku,total,lock_num,valid_num
FROM ods_lingxing_inventory_bin_detail_weekly WHERE wid=18678 AND whb_id=59911 AND product_id=403591
ORDER BY snapshot_date DESC,sync_batch_id,store_id LIMIT 30;
SELECT run_id,status,request_id,started_at,completed_at,error_message FROM scheduler_task_run
WHERE task_code='weekly_inventory_bin_export' ORDER BY started_at DESC LIMIT 5;
