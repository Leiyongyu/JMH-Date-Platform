-- eBay SOP 三类文件上传权限；在 jmh_data_platform 执行。
USE jmh_data_platform;

SET @after_sales_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE perms='sop:afterSales:list'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导入eBay售后数据',@after_sales_menu_id,4,'',NULL,NULL,'',
       1,0,'F','0','0','sop:afterSales:import','#','SYSTEM',NOW(),
       'eBay月销量、一次性历史售后和后续售后文件上传'
WHERE @after_sales_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE perms='sop:afterSales:import'
  );

SET @after_sales_import_id := (
  SELECT menu_id FROM sys_menu
  WHERE perms='sop:afterSales:import'
  ORDER BY menu_id LIMIT 1
);

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT role_id,@after_sales_import_id
FROM sys_role
WHERE role_key='admin' AND status='0'
  AND @after_sales_import_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@after_sales_import_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
WHERE u.user_name='leiyongyu'
  AND @after_sales_import_id IS NOT NULL;

SELECT menu_id,menu_name,parent_id,perms,status
FROM sys_menu
WHERE perms='sop:afterSales:import';
