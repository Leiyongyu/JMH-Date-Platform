-- 只读；专用表缺失可继续01—06；共享表缺失按部署说明处理；基础表缺失先部署主系统。
SET NAMES utf8mb4;
SELECT @@version AS mysql_version,@@session.time_zone AS db_session_time_zone;
WITH expected AS (
SELECT 'date-project' AS db_name,'ods_lingxing_inventory_detail_weekly' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'ods_lingxing_inventory_age_bucket_weekly' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'ods_lingxing_inventory_bin_detail_weekly' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'ods_lingxing_product_info_weekly' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'ops_weekly_export_file' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'ods_goodcang_wh_inventory_storage' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'ods_goodcang_wh_inventory_storage_detail' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'dim_lingxing_currency_month' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'dwd_performance_owner_rule' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project' AS db_name,'dwd_ebay_sku_analysis_order' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'jmh_data_platform' AS db_name,'ods_goodcang_inventory_age_latest' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'jmh_data_platform' AS db_name,'ods_lingxing_product_procurement_monthly' AS table_name,'共享源表' AS purpose
UNION ALL
SELECT 'date-project','ebay_inventory_detail_grade','页面专用表'
UNION ALL
SELECT 'date-project','ebay_inventory_pivot_snapshot','页面专用表'
UNION ALL
SELECT 'date-project','ebay_inventory_pivot_owner','页面专用表'
UNION ALL
SELECT 'date-project','ebay_inventory_detail_history','页面专用表'
UNION ALL
SELECT 'date-project','ebay_inventory_detail_price','页面专用表'
UNION ALL
SELECT 'jmh_data_platform','sys_user','既有ERP基础表'
UNION ALL
SELECT 'jmh_data_platform','sys_role','既有ERP基础表'
UNION ALL
SELECT 'jmh_data_platform','sys_menu','既有ERP基础表'
UNION ALL
SELECT 'jmh_data_platform','sys_user_role','既有ERP基础表'
UNION ALL
SELECT 'jmh_data_platform','sys_role_menu','既有ERP基础表'
UNION ALL
SELECT 'jmh_data_platform','sys_job','既有ERP基础表'
UNION ALL
SELECT 'date-project','scheduler_task','既有Python基础表'
)
SELECT e.db_name,e.table_name,e.purpose,CASE WHEN t.TABLE_NAME IS NULL THEN 'MISSING' ELSE 'EXISTS' END AS table_status
FROM expected e LEFT JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=e.db_name AND t.TABLE_NAME=e.table_name
ORDER BY e.purpose,e.db_name,e.table_name;
-- 以下依赖现有ERP基础表；上面若显示缺失，请停止。
SELECT u.user_name,u.status AS user_status,u.del_flag AS user_deleted,r.role_id,r.role_key,r.role_name,r.status AS role_status,r.del_flag AS role_deleted
FROM jmh_data_platform.sys_user u
LEFT JOIN jmh_data_platform.sys_user_role ur ON ur.user_id=u.user_id
LEFT JOIN jmh_data_platform.sys_role r ON r.role_id=ur.role_id WHERE u.user_name='leiyongyu';
SELECT m.menu_id,m.parent_id,m.path,m.menu_name,m.menu_type,m.status,m.visible,m.perms,p.menu_name AS parent_name
FROM jmh_data_platform.sys_menu m LEFT JOIN jmh_data_platform.sys_menu p ON p.menu_id=m.parent_id
WHERE (m.menu_type='M' AND (m.path='operations' OR LOWER(m.path)='ebay'))
OR m.perms IN ('operations:ebayInventoryDetail:list','operations:ebayInventoryDetail:import','operations:ebayInventoryDetail:export');
SELECT job_id,job_name,invoke_target,cron_expression,status
FROM jmh_data_platform.sys_job
WHERE invoke_target IN ('pythonWeeklyInventoryTask.runWeekly()','pythonWeeklyInventoryTask.runWeekly',
'pythonGoodcangStorageTask.runWeekly()','pythonGoodcangStorageTask.runWeekly',
'operationSyncTask.syncGoodcangInventoryAgeLatest()','operationSyncTask.syncGoodcangInventoryAgeLatest');
-- RuoYi sys_job: status=0正常、1暂停；缺行意味着未注册任务，不能只补空源表。
