-- 在 jmh_data_platform 库执行。
-- 为已存在的“SOP > 选竞品”页面补充批量导入链接和商品库导出权限。
-- 幂等脚本：只新增缺失权限，不删除或修改业务数据。

SET NAMES utf8mb4;

SET @competitor_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE menu_type='C'
    AND (component='sop/competitorLookup/index' OR perms='sop:competitor:list')
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '批量导入竞品链接',@competitor_menu_id,5,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:import','#','SYSTEM',NOW(),'解析Excel链接并逐条抓取eBay竞品'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:import');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导出竞品商品库',@competitor_menu_id,6,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:export','#','SYSTEM',NOW(),'导出选中或全部已保存竞品商品'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:export');

SET @competitor_import_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:import'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);
SET @competitor_export_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:export'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);

UPDATE sys_menu
SET parent_id=@competitor_menu_id,order_num=5,menu_type='F',visible='0',status='0',
    menu_name='批量导入竞品链接',remark='解析Excel链接并逐条抓取eBay竞品',
    update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@competitor_import_id;

UPDATE sys_menu
SET parent_id=@competitor_menu_id,order_num=6,menu_type='F',visible='0',status='0',
    menu_name='导出竞品商品库',remark='导出选中或全部已保存竞品商品',
    update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@competitor_export_id;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN (
  SELECT @competitor_import_id AS menu_id
  UNION ALL SELECT @competitor_export_id
) m ON m.menu_id IS NOT NULL
WHERE r.role_key='admin' AND r.status='0';

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN (
  SELECT @competitor_import_id AS menu_id
  UNION ALL SELECT @competitor_export_id
) m ON m.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu';

SELECT menu_id,parent_id,menu_name,order_num,menu_type,perms,status
FROM sys_menu
WHERE menu_id IN (@competitor_import_id,@competitor_export_id)
ORDER BY order_num,menu_id;
