-- 目标库：Java ERP 的 jmh_data_platform；不建/改任何 Python 业务数据表。
-- 新页面直接位于“运营中心 / eBay”，与“店铺分析 / eBay补货2.0”独立。
-- 只授予 leiyongyu 当前有效角色本页、导入、导出及必要祖先；不做全库授权。
-- 请勿使用 mysql --force 忽略错误。父目录缺失/重复或页面权限重复时明确中止。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

-- M 类型目录没有功能 perms，按实际目录路径寻找；新页面和按钮一律按 perms 查找。
SET @inventory_operations_count := (
  SELECT COUNT(*) FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND path='operations'
);
SET @inventory_operations_id := (
  SELECT MIN(menu_id) FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND path='operations'
);
SET @inventory_ebay_count := (
  SELECT COUNT(*) FROM sys_menu
  WHERE parent_id=@inventory_operations_id AND menu_type='M' AND LOWER(path)='ebay'
);
SET @inventory_ebay_id := (
  SELECT MIN(menu_id) FROM sys_menu
  WHERE parent_id=@inventory_operations_id AND menu_type='M' AND LOWER(path)='ebay'
);
SET @inventory_permissions_valid := (
  SELECT COUNT(*)=0 FROM (
    SELECT perms FROM sys_menu
    WHERE perms IN ('operations:ebayInventoryDetail:list',
                   'operations:ebayInventoryDetail:export',
                   'operations:ebayInventoryDetail:import')
    GROUP BY perms HAVING COUNT(*)>1
  ) duplicate_permissions
);

SELECT CASE
  WHEN @inventory_operations_count<>1 THEN 'ERROR: 运营中心根目录 path=operations 缺失或重复，禁止继续'
  WHEN @inventory_ebay_count<>1 THEN 'ERROR: 运营中心下 eBay 目录缺失或重复，禁止继续'
  WHEN NOT @inventory_permissions_valid THEN 'ERROR: 库存明细权限重复，请先处理重复菜单'
  ELSE 'OK: 父目录唯一、权限无重复，可以新增库存明细页面'
END AS deployment_precheck;

-- 使用临时表 NOT NULL 约束作部署断言，不创建持久化辅助表/过程。
DROP TEMPORARY TABLE IF EXISTS `_ebay_inventory_detail_menu_guard`;
CREATE TEMPORARY TABLE `_ebay_inventory_detail_menu_guard` (
  `required_unique_operations_ebay_parent_and_permissions` BIGINT NOT NULL,
  CHECK (`required_unique_operations_ebay_parent_and_permissions`>0)
);
INSERT INTO `_ebay_inventory_detail_menu_guard`
SELECT IF(@inventory_operations_count=1 AND @inventory_ebay_count=1
          AND @inventory_permissions_valid, @inventory_ebay_id, NULL);
DROP TEMPORARY TABLE `_ebay_inventory_detail_menu_guard`;

START TRANSACTION;
INSERT INTO sys_menu
  (menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,
   menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'Ebay库存明细',@inventory_ebay_id,30,'inventory-detail',
       'operations/ebay/inventoryDetail/index',NULL,'EbayInventoryDetail',1,0,
       'C','0','0','operations:ebayInventoryDetail:list','list','SYSTEM',NOW(),
       '站点SKU实时库存、产品等级、负责人及谷仓30天仓租；支持筛选、选中/全量导出'
WHERE @inventory_operations_count=1 AND @inventory_ebay_count=1
  AND @inventory_permissions_valid
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:ebayInventoryDetail:list');

SET @inventory_page_id := (
  SELECT MIN(menu_id) FROM sys_menu WHERE perms='operations:ebayInventoryDetail:list'
);
-- 若已部署本页，只修正它的挂载/组件；不改其他菜单，也不恢复人工禁用状态。
UPDATE sys_menu
SET menu_name='Ebay库存明细',parent_id=@inventory_ebay_id,
    path='inventory-detail',component='operations/ebay/inventoryDetail/index',
    route_name='EbayInventoryDetail',menu_type='C',is_frame=1,
    update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@inventory_page_id
  AND @inventory_operations_count=1 AND @inventory_ebay_count=1
  AND @inventory_permissions_valid;

INSERT INTO sys_menu
  (menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,
   menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '导出库存明细',@inventory_page_id,1,'',NULL,NULL,'',1,0,
       'F','0','0','operations:ebayInventoryDetail:export','#','SYSTEM',NOW(),
       '导出勾选的站点SKU；未勾选时导出当前筛选条件下全部数据'
WHERE @inventory_page_id IS NOT NULL AND @inventory_ebay_count=1
  AND @inventory_operations_count=1 AND @inventory_permissions_valid
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:ebayInventoryDetail:export');

INSERT INTO sys_menu
  (menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,
   menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '导入产品等级',@inventory_page_id,2,'',NULL,NULL,'',1,0,
       'F','0','0','operations:ebayInventoryDetail:import','#','SYSTEM',NOW(),
       '按站点和完整SKU导入本库存页面的产品等级，不改补货2.0产品等级规则'
WHERE @inventory_page_id IS NOT NULL AND @inventory_ebay_count=1
  AND @inventory_operations_count=1 AND @inventory_permissions_valid
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:ebayInventoryDetail:import');

UPDATE sys_menu SET parent_id=@inventory_page_id,menu_type='F',update_by='SYSTEM',update_time=NOW()
WHERE perms IN ('operations:ebayInventoryDetail:export','operations:ebayInventoryDetail:import')
  AND @inventory_page_id IS NOT NULL AND @inventory_ebay_count=1
  AND @inventory_operations_count=1 AND @inventory_permissions_valid;

INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_menu m ON (
  m.menu_id IN (@inventory_operations_id,@inventory_ebay_id)
  OR m.perms IN ('operations:ebayInventoryDetail:list',
                 'operations:ebayInventoryDetail:export',
                 'operations:ebayInventoryDetail:import')
)
WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0'
  AND @inventory_operations_count=1 AND @inventory_ebay_count=1
  AND @inventory_permissions_valid;
COMMIT;

SELECT menu_id,parent_id,menu_name,component,route_name,menu_type,visible,status,perms
FROM sys_menu WHERE perms IN ('operations:ebayInventoryDetail:list',
                             'operations:ebayInventoryDetail:export',
                             'operations:ebayInventoryDetail:import')
ORDER BY menu_type,order_num,menu_id;

SELECT u.user_name,r.role_id,r.role_name,m.menu_name,m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0'
  AND m.perms IN ('operations:ebayInventoryDetail:list',
                  'operations:ebayInventoryDetail:export',
                  'operations:ebayInventoryDetail:import')
ORDER BY r.role_id,m.menu_id;
-- 授权完成后退出重新登录，以刷新用户权限和动态路由。
