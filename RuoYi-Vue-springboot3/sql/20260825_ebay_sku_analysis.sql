-- 在jmh_data_platform执行：运营中心 / eBay / SKU分析菜单与权限。
SET @operations_id := (SELECT menu_id FROM sys_menu WHERE menu_type='M' AND (path='operations' OR menu_name='运营中心') ORDER BY menu_id LIMIT 1);
SET @ebay_dir_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(menu_name)='ebay' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'eBay',@operations_id,2,'ebay',NULL,'',1,0,'M','0','0','','shopping','SYSTEM',NOW(),'运营中心eBay业务目录'
WHERE @operations_id IS NOT NULL AND @ebay_dir_id IS NULL;
SET @ebay_dir_id := (SELECT menu_id FROM sys_menu WHERE parent_id=@operations_id AND menu_type='M' AND LOWER(menu_name)='ebay' ORDER BY menu_id LIMIT 1);
SET @sku_menu_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT 'SKU分析',@ebay_dir_id,20,'sku-analysis','operations/ebay/skuAnalysis/index','EbaySkuAnalysis',1,0,'C','0','0','operations:ebaySkuAnalysis:list','chart','SYSTEM',NOW(),'上传数字酋长订单并按SKU分析'
WHERE @ebay_dir_id IS NOT NULL AND @sku_menu_id IS NULL;
SET @sku_menu_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET parent_id=@ebay_dir_id,menu_name='SKU分析',path='sku-analysis',component='operations/ebay/skuAnalysis/index',route_name='EbaySkuAnalysis',visible='0',status='0' WHERE menu_id=@sku_menu_id;
SET @import_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:import' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '上传eBay订单',@sku_menu_id,1,'',NULL,'',1,0,'F','0','0','operations:ebaySkuAnalysis:import','#','SYSTEM',NOW(),'上传数字酋长订单Excel'
WHERE @sku_menu_id IS NOT NULL AND @import_id IS NULL;
SET @import_id := (SELECT menu_id FROM sys_menu WHERE perms='operations:ebaySkuAnalysis:import' ORDER BY menu_id LIMIT 1);
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_menu m ON m.menu_id IN (@operations_id,@ebay_dir_id,@sku_menu_id,@import_id)
WHERE u.user_name='leiyongyu' AND m.menu_id IS NOT NULL;

-- 部署检查
SELECT menu_id,parent_id,menu_name,menu_type,perms,component FROM sys_menu WHERE menu_id IN (@ebay_dir_id,@sku_menu_id,@import_id) ORDER BY menu_id;
