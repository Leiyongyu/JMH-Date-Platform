-- 目标库：jmh_data_platform（Java ERP 数据库）。
-- 新增“运营中心 / eBay / 店铺分析 / eBay补货2.0”菜单。
-- 可重复执行；不创建业务表，并给 leiyongyu 的有效角色补齐完整祖先链。
USE jmh_data_platform;
SET NAMES utf8mb4;

SET @operations_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M'
    AND (path='operations' OR menu_name='运营中心')
  ORDER BY CASE WHEN path='operations' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay',@operations_id,2,'ebay',NULL,NULL,'',
       1,0,'M','0','0','','shopping','SYSTEM',NOW(),'运营中心eBay业务目录'
WHERE @operations_id IS NOT NULL AND @ebay_dir_id IS NULL;
SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '店铺分析',@ebay_dir_id,20,'store-analysis',NULL,NULL,'',
       1,0,'M','0','0','','shop','SYSTEM',NOW(),'eBay店铺分析业务目录'
WHERE @ebay_dir_id IS NOT NULL AND @store_analysis_id IS NULL;
SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_dir_id,menu_name='店铺分析',order_num=20,
    path='store-analysis',component=NULL,query=NULL,route_name='',
    is_frame=1,is_cache=0,menu_type='M',visible='0',status='0',
    perms='',icon='shop',update_by='SYSTEM',update_time=NOW(),
    remark='eBay店铺分析业务目录'
WHERE menu_id=@store_analysis_id;

SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay补货2.0',@store_analysis_id,4,'replenishment-v2',
       'operations/ebay/replenishmentV2/index',NULL,'EbayReplenishmentV2',
       1,0,'C','0','0','operations:ebayReplenishmentV2:list','shopping',
       'SYSTEM',NOW(),'eBay补货2.0前端展示入口，后端逻辑待建设'
WHERE @store_analysis_id IS NOT NULL AND @ebay_replenishment_v2_id IS NULL;
SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@store_analysis_id,menu_name='eBay补货2.0',order_num=4,
    path='replenishment-v2',component='operations/ebay/replenishmentV2/index',
    query=NULL,route_name='EbayReplenishmentV2',is_frame=1,is_cache=0,
    menu_type='C',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:list',icon='shopping',
    update_by='SYSTEM',update_time=NOW(),
    remark='eBay补货2.0前端展示入口，后端逻辑待建设'
WHERE menu_id=@ebay_replenishment_v2_id AND @store_analysis_id IS NOT NULL;

-- 非管理员动态路由从根节点递归构建，四级菜单必须全部授权。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,target.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN (
  SELECT @operations_id AS menu_id
  UNION ALL SELECT @ebay_dir_id
  UNION ALL SELECT @store_analysis_id
  UNION ALL SELECT @ebay_replenishment_v2_id
) target ON target.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,route_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@ebay_replenishment_v2_id)
ORDER BY parent_id,order_num,menu_id;

SELECT u.user_name,r.role_id,r.role_name,m.menu_id,m.parent_id,m.menu_name,m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu'
  AND m.menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@ebay_replenishment_v2_id)
ORDER BY r.role_id,m.parent_id,m.order_num,m.menu_id;
