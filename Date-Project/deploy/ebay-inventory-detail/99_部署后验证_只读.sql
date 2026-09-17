-- 全部只读；请先完成01—06，默认MySQL8。
SET NAMES utf8mb4;
SELECT TABLE_SCHEMA,TABLE_NAME FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME IN
('ebay_inventory_detail_grade','ebay_inventory_pivot_snapshot','ebay_inventory_pivot_owner',
 'ebay_inventory_detail_history','ebay_inventory_detail_price') ORDER BY TABLE_NAME;
-- 应为5张表；record_key存在且新唯一索引依次包含4列，旧索引应不存在。
SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT
FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='date-project'
 AND TABLE_NAME='ebay_inventory_detail_history' AND COLUMN_NAME='record_key';
SELECT INDEX_NAME,NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='date-project'
 AND TABLE_NAME='ebay_inventory_detail_history'
GROUP BY INDEX_NAME,NON_UNIQUE;
SELECT 'grade' AS data_set,COUNT(*) AS row_count FROM `date-project`.ebay_inventory_detail_grade
UNION ALL SELECT 'price',COUNT(*) FROM `date-project`.ebay_inventory_detail_price
UNION ALL SELECT 'snapshot',COUNT(*) FROM `date-project`.ebay_inventory_pivot_snapshot
UNION ALL SELECT 'owner',COUNT(*) FROM `date-project`.ebay_inventory_pivot_owner
UNION ALL SELECT 'detail',COUNT(*) FROM `date-project`.ebay_inventory_detail_history;
-- 必须0行：同日期多个主批次。
SELECT stat_date,COUNT(*) FROM `date-project`.ebay_inventory_pivot_snapshot
GROUP BY stat_date HAVING COUNT(*)>1;
-- 应为0：无主批次明细。
SELECT COUNT(*) AS orphan_detail_rows FROM `date-project`.ebay_inventory_detail_history d
LEFT JOIN `date-project`.ebay_inventory_pivot_snapshot s ON s.id=d.snapshot_id WHERE s.id IS NULL;
SELECT s.stat_date,s.trigger_type,s.item_count,s.group_count,
 (SELECT COUNT(*) FROM `date-project`.ebay_inventory_detail_history d WHERE d.snapshot_id=s.id) AS actual_detail_rows,
 (SELECT COUNT(*) FROM `date-project`.ebay_inventory_pivot_owner o WHERE o.snapshot_id=s.id) AS actual_owner_rows
FROM `date-project`.ebay_inventory_pivot_snapshot s ORDER BY s.stat_date DESC LIMIT 20;
-- EXCEL_IMPORT只填明细，owner行数为0正常；旧的仅透视批次可能无明细，不能据此补造历史。
SELECT m.menu_id,m.parent_id,m.menu_name,m.component,m.menu_type,m.status,m.visible,m.perms,
 p.menu_name AS parent_name,p.status AS parent_status,p.visible AS parent_visible
FROM jmh_data_platform.sys_menu m LEFT JOIN jmh_data_platform.sys_menu p ON p.menu_id=m.parent_id
WHERE m.perms IN ('operations:ebayInventoryDetail:list','operations:ebayInventoryDetail:import','operations:ebayInventoryDetail:export');
-- 每项应OK；任一有效角色授权即可。账号停用/不存在也会显示缺权限。
WITH expected AS (
 SELECT 'operations:ebayInventoryDetail:list' AS perms
 UNION ALL SELECT 'operations:ebayInventoryDetail:import'
 UNION ALL SELECT 'operations:ebayInventoryDetail:export'
)
SELECT e.perms,CASE WHEN EXISTS (
 SELECT 1 FROM jmh_data_platform.sys_user u
 JOIN jmh_data_platform.sys_user_role ur ON ur.user_id=u.user_id
 JOIN jmh_data_platform.sys_role r ON r.role_id=ur.role_id
 JOIN jmh_data_platform.sys_role_menu rm ON rm.role_id=r.role_id
 JOIN jmh_data_platform.sys_menu m ON m.menu_id=rm.menu_id
 WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0'
 AND r.status='0' AND r.del_flag='0' AND m.status='0' AND m.perms=e.perms
) THEN 'OK' ELSE 'MISSING_OR_DISABLED' END AS effective_permission FROM expected e;
SELECT u.user_name,r.role_id,r.role_name,m.menu_name,m.perms
FROM jmh_data_platform.sys_user u
JOIN jmh_data_platform.sys_user_role ur ON ur.user_id=u.user_id
JOIN jmh_data_platform.sys_role r ON r.role_id=ur.role_id
JOIN jmh_data_platform.sys_role_menu rm ON rm.role_id=r.role_id
JOIN jmh_data_platform.sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0'
AND r.status='0' AND r.del_flag='0'
AND m.perms IN ('operations:ebayInventoryDetail:list','operations:ebayInventoryDetail:import','operations:ebayInventoryDetail:export')
ORDER BY r.role_id,m.menu_id;
