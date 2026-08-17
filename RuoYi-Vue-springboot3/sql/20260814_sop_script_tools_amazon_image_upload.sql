-- SOP > 脚本菜单 > 亚马逊主图批量上传。
-- 仅在 Java ERP 数据库 jmh_data_platform 执行；Python任务表不在本脚本创建。
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
       'SYSTEM',NOW(),'标准作业流程与自动化工具'
WHERE @sop_menu_id IS NULL;

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND (path='sop' OR menu_name='SOP')
  ORDER BY CASE WHEN path='sop' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @script_tools_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id
    AND (path='script-tools' OR component='sop/scriptTools/index'
         OR perms='sop:scriptTools:view')
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '脚本菜单',@sop_menu_id,5,'script-tools','sop/scriptTools/index',NULL,
       'SopScriptTools',1,0,'C','0','0','sop:scriptTools:view','code',
       'SYSTEM',NOW(),'集中打开通过ERP鉴权的本机自动化工具'
WHERE @sop_menu_id IS NOT NULL AND @script_tools_menu_id IS NULL;

SET @script_tools_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id
    AND (path='script-tools' OR component='sop/scriptTools/index'
         OR perms='sop:scriptTools:view')
  ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name='脚本菜单',parent_id=@sop_menu_id,order_num=5,
    path='script-tools',component='sop/scriptTools/index',route_name='SopScriptTools',
    is_frame=1,is_cache=0,menu_type='C',visible='0',status='0',
    perms='sop:scriptTools:view',icon='code',
    update_by='SYSTEM',update_time=NOW(),
    remark='集中打开通过ERP鉴权的本机自动化工具'
WHERE menu_id=@script_tools_menu_id;

SET @amazon_image_upload_perm_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:amazonImageUpload:use'
  ORDER BY CASE WHEN parent_id=@script_tools_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '使用亚马逊主图批量上传',@script_tools_menu_id,1,'',NULL,NULL,'',
       1,0,'F','0','0','sop:amazonImageUpload:use','#',
       'SYSTEM',NOW(),'管理当前用户紫鸟配置并打开Amazon主图上传工具'
WHERE @script_tools_menu_id IS NOT NULL AND @amazon_image_upload_perm_id IS NULL;

SET @amazon_image_upload_perm_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:amazonImageUpload:use'
  ORDER BY CASE WHEN parent_id=@script_tools_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name='使用亚马逊主图批量上传',parent_id=@script_tools_menu_id,
    order_num=1,menu_type='F',visible='0',status='0',
    perms='sop:amazonImageUpload:use',icon='#',
    update_by='SYSTEM',update_time=NOW(),
    remark='管理当前用户紫鸟配置并打开Amazon主图上传工具'
WHERE menu_id=@amazon_image_upload_perm_id;

-- 使用独立角色，避免把高风险桌面自动化权限扩散给 leiyongyu 的其他角色成员。
INSERT INTO sys_role (
  role_name,role_key,role_sort,data_scope,menu_check_strictly,dept_check_strictly,
  status,del_flag,create_by,create_time,remark
)
SELECT '亚马逊主图上传操作员','amazon_image_upload_operator',
       COALESCE((SELECT MAX(role_sort) FROM sys_role),0)+1,'2',1,1,'0','0','SYSTEM',NOW(),
       '仅允许进入SOP脚本菜单，管理本人紫鸟配置并使用主图上传工具'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role WHERE role_key='amazon_image_upload_operator' AND del_flag='0'
);

SET @tool_role_id := (
  SELECT role_id FROM sys_role
  WHERE role_key='amazon_image_upload_operator' AND del_flag='0'
  ORDER BY role_id LIMIT 1
);

INSERT IGNORE INTO sys_user_role (user_id,role_id)
SELECT u.user_id,@tool_role_id FROM sys_user u
WHERE u.user_name='leiyongyu' AND u.del_flag='0' AND @tool_role_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN (
  SELECT @sop_menu_id AS menu_id
  UNION ALL SELECT @script_tools_menu_id
  UNION ALL SELECT @amazon_image_upload_perm_id
) m ON m.menu_id IS NOT NULL
WHERE r.role_key IN ('admin','amazon_image_upload_operator')
  AND r.status='0' AND r.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,menu_type,perms,status
FROM sys_menu
WHERE menu_id IN (@sop_menu_id,@script_tools_menu_id,@amazon_image_upload_perm_id)
ORDER BY parent_id,order_num,menu_id;
