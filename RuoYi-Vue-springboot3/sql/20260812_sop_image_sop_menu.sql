-- SOP > 图片SOP 菜单及权限。
-- 在 jmh_data_platform 库执行；脚本幂等，不删除或修改业务数据。
USE jmh_data_platform;
SET NAMES utf8mb4;

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND (path='sop' OR menu_name='SOP')
  ORDER BY CASE WHEN path='sop' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'SOP',0,5,'sop',NULL,NULL,'Sop',1,0,'M','0','0',NULL,'guide',
       'SYSTEM',NOW(),'标准作业流程与业务数据处理'
WHERE @sop_menu_id IS NULL;

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND (path='sop' OR menu_name='SOP')
  ORDER BY CASE WHEN path='sop' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @image_sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id
    AND (path='image-sop' OR component='sop/imageSop/index' OR perms='sop:imageSop:use')
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '图片SOP',@sop_menu_id,4,'image-sop','sop/imageSop/index',NULL,'SopImageSop',
       1,0,'C','0','0','sop:imageSop:use','picture',
       'SYSTEM',NOW(),'领星/eBay商品信息、AI图片需求生成与Excel导出'
WHERE @sop_menu_id IS NOT NULL AND @image_sop_menu_id IS NULL;

SET @image_sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id
    AND (path='image-sop' OR component='sop/imageSop/index' OR perms='sop:imageSop:use')
  ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name='图片SOP',parent_id=@sop_menu_id,order_num=4,
    path='image-sop',component='sop/imageSop/index',route_name='SopImageSop',
    is_frame=1,is_cache=0,menu_type='C',visible='0',status='0',
    perms='sop:imageSop:use',icon='picture',
    update_by='SYSTEM',update_time=NOW(),
    remark='领星/eBay商品信息、AI图片需求生成与Excel导出'
WHERE menu_id=@image_sop_menu_id;

-- 管理员角色和 leiyongyu 账户关联的全部角色均获得菜单及使用权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,@sop_menu_id
FROM sys_role r
WHERE r.role_key='admin' AND r.status='0' AND @sop_menu_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,@image_sop_menu_id
FROM sys_role r
WHERE r.role_key='admin' AND r.status='0' AND @image_sop_menu_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@sop_menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
WHERE u.user_name='leiyongyu' AND @sop_menu_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@image_sop_menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
WHERE u.user_name='leiyongyu' AND @image_sop_menu_id IS NOT NULL;

SELECT menu_id,parent_id,menu_name,order_num,path,component,menu_type,perms,status
FROM sys_menu
WHERE menu_id IN (@sop_menu_id,@image_sop_menu_id)
ORDER BY parent_id,order_num,menu_id;
