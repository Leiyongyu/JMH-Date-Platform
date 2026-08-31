-- 在 jmh_data_platform 执行：运营中心 / eBay / 店铺分析三级菜单。
-- 可重复执行；保留原 SKU 分析菜单 ID 和功能权限，仅调整其父菜单。

SET @operations_id := (SELECT menu_id FROM sys_menu WHERE menu_type='M' AND (path='operations' OR menu_name='运营中心') ORDER BY menu_id LIMIT 1);
SET @ebay_dir_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(menu_name)='ebay' ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'eBay',@operations_id,2,'ebay',NULL,'',1,0,'M','0','0','','shopping','SYSTEM',NOW(),'运营中心eBay业务目录'
WHERE @operations_id IS NOT NULL AND @ebay_dir_id IS NULL;

SET @ebay_dir_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(menu_name)='ebay' ORDER BY menu_id LIMIT 1);
SET @store_analysis_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND (path='store-analysis' OR menu_name='店铺分析') ORDER BY menu_id LIMIT 1);

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '店铺分析',@ebay_dir_id,20,'store-analysis',NULL,'',1,0,'M','0','0','','shop','SYSTEM',NOW(),'eBay店铺分析业务目录'
WHERE @ebay_dir_id IS NOT NULL AND @store_analysis_id IS NULL;

SET @store_analysis_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@ebay_dir_id AND menu_type='M' AND (path='store-analysis' OR menu_name='店铺分析') ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@ebay_dir_id,menu_name='店铺分析',order_num=20,path='store-analysis',component=NULL,route_name='',menu_type='M',visible='0',status='0',perms='',icon='shop',update_by='SYSTEM',update_time=NOW(),remark='eBay店铺分析业务目录' WHERE menu_id=@store_analysis_id;

SET @sku_menu_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'SKU分析',@store_analysis_id,1,'sku-analysis','operations/ebay/skuAnalysis/index','EbaySkuAnalysis',1,0,'C','0','0','operations:ebaySkuAnalysis:list','chart','SYSTEM',NOW(),'上传数字酋长订单并按SKU分析'
WHERE @store_analysis_id IS NOT NULL AND @sku_menu_id IS NULL;
SET @sku_menu_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@store_analysis_id,menu_name='SKU分析',order_num=1,path='sku-analysis',component='operations/ebay/skuAnalysis/index',route_name='EbaySkuAnalysis',menu_type='C',visible='0',status='0',perms='operations:ebaySkuAnalysis:list',icon='chart',update_by='SYSTEM',update_time=NOW(),remark='上传数字酋长订单并按SKU分析' WHERE menu_id=@sku_menu_id;

SET @return_overview_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnOverview:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '退货概览',@store_analysis_id,2,'return-overview','operations/ebay/returnOverview/index','EbayReturnOverview',1,0,'C','0','0','operations:ebayReturnOverview:list','chart','SYSTEM',NOW(),'eBay退货概览演示页面'
WHERE @store_analysis_id IS NOT NULL AND @return_overview_id IS NULL;
SET @return_overview_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnOverview:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@store_analysis_id,menu_name='退货概览',order_num=2,path='return-overview',component='operations/ebay/returnOverview/index',route_name='EbayReturnOverview',menu_type='C',visible='0',status='0',icon='chart',update_by='SYSTEM',update_time=NOW(),remark='eBay退货概览演示页面' WHERE menu_id=@return_overview_id;

SET @return_detail_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnDetail:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '退货明细',@store_analysis_id,3,'return-detail','operations/ebay/returnDetail/index','EbayReturnDetail',1,0,'C','0','0','operations:ebayReturnDetail:list','list','SYSTEM',NOW(),'eBay退货明细演示页面'
WHERE @store_analysis_id IS NOT NULL AND @return_detail_id IS NULL;
SET @return_detail_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebayReturnDetail:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@store_analysis_id,menu_name='退货明细',order_num=3,path='return-detail',component='operations/ebay/returnDetail/index',route_name='EbayReturnDetail',menu_type='C',visible='0',status='0',icon='list',update_by='SYSTEM',update_time=NOW(),remark='eBay退货明细演示页面' WHERE menu_id=@return_detail_id;

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

SET @import_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:import' ORDER BY menu_id LIMIT 1);

DELETE role_menu
FROM sys_role_menu role_menu
INNER JOIN sys_menu menu ON menu.menu_id=role_menu.menu_id
WHERE menu.perms='operations:ebaySkuAnalysis:profitImport';
DELETE FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:profitImport';
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '上传eBay订单',@sku_menu_id,1,'',NULL,'',1,0,'F','0','0','operations:ebaySkuAnalysis:import','#','SYSTEM',NOW(),'上传数字酋长订单Excel'
WHERE @sku_menu_id IS NOT NULL AND @import_id IS NULL;
SET @import_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:import' ORDER BY menu_id LIMIT 1);

-- 仅为原本拥有 SKU 分析页面权限的角色补齐新的父目录，避免菜单移动后不可见。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT role_id,@store_analysis_id FROM sys_role_menu
WHERE menu_id=@sku_menu_id AND @store_analysis_id IS NOT NULL;

-- leiyongyu 当前拥有的全部角色获得店铺分析整棵菜单权限。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @operations_id,@ebay_dir_id,@store_analysis_id,@sku_menu_id,@import_id,
  @return_overview_id,@return_detail_id,@ebay_replenishment_v2_id
)
WHERE u.user_name='leiyongyu' AND m.menu_id IS NOT NULL;

SELECT menu_id,parent_id,menu_name,order_num,menu_type,perms,component
FROM sys_menu
WHERE menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@sku_menu_id,@import_id,@return_overview_id,@return_detail_id,@ebay_replenishment_v2_id)
ORDER BY parent_id,order_num,menu_id;
