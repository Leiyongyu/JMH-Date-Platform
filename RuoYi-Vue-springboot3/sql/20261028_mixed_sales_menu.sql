-- Java ERP数据库。只新增菜单及角色关联，不新建/修改业务表。
USE jmh_data_platform;
SET NAMES utf8mb4;

SET @mixed_ops_count := (SELECT COUNT(*) FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND (path='operations' OR menu_name='运营中心'));
SET @mixed_ops_id := (SELECT MIN(menu_id) FROM sys_menu WHERE parent_id=0 AND menu_type='M' AND (path='operations' OR menu_name='运营中心'));
SET @mixed_page_count := (SELECT COUNT(*) FROM sys_menu WHERE perms='operations:mixedSales:list');
SET @mixed_route_conflicts := (SELECT COUNT(*) FROM sys_menu WHERE parent_id=@mixed_ops_id AND path='mixed-sales' AND COALESCE(perms,'')!='operations:mixedSales:list');

CREATE TEMPORARY TABLE `_mixed_sales_menu_guard` (unique_operations_and_menu BIGINT NOT NULL);
INSERT INTO `_mixed_sales_menu_guard`
SELECT IF(@mixed_ops_count=1 AND @mixed_page_count<=1 AND @mixed_route_conflicts=0,@mixed_ops_id,NULL);
DROP TEMPORARY TABLE `_mixed_sales_menu_guard`;

START TRANSACTION;
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '混销',@mixed_ops_id,50,'mixed-sales','operations/mixedSales/index',NULL,'MixedSales',
    1,0,'C','0','0','operations:mixedSales:list','shopping','SYSTEM',NOW(),
    '混销：Amazon仓库SKU库存销量及店铺MSKU明细；eBay复用补货2.0库存销量及站点明细'
WHERE NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:mixedSales:list');

SET @mixed_page_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:mixedSales:list');
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_menu m ON m.menu_id IN (@mixed_ops_id,@mixed_page_id)
WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';
COMMIT;

SELECT menu_id,parent_id,menu_name,component,perms FROM sys_menu WHERE menu_id=@mixed_page_id;
SELECT DISTINCT r.role_id,r.role_name FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id AND rm.menu_id=@mixed_page_id
WHERE u.user_name='leiyongyu' AND r.status='0' AND r.del_flag='0';
-- 退出重新登录后加载新权限及菜单。同角色用户均获得查看权限。
