-- 将“SOP > 图片SOP”独立菜单迁移为“脚本菜单”页面内的按钮权限。
-- 仅在 Java ERP 数据库 jmh_data_platform 执行；不修改 date-project 数据表。
-- 脚本幂等，可重复执行。

USE `jmh_data_platform`;
SET NAMES utf8mb4;

SET @sop_menu_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE parent_id=0
      AND menu_type='M'
      AND (path='sop' OR menu_name='SOP')
    ORDER BY CASE WHEN path='sop' THEN 0 ELSE 1 END,menu_id
    LIMIT 1
);

SET @script_tools_menu_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE parent_id=@sop_menu_id
      AND (
          path='script-tools'
          OR component='sop/scriptTools/index'
          OR perms='sop:scriptTools:view'
      )
    ORDER BY menu_id
    LIMIT 1
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '脚本菜单',@sop_menu_id,5,'script-tools','sop/scriptTools/index',NULL,
    'SopScriptTools',1,0,'C','0','0','sop:scriptTools:view','code',
    'SYSTEM',NOW(),'集中打开Python自动化工具'
WHERE @sop_menu_id IS NOT NULL
  AND @script_tools_menu_id IS NULL;

SET @script_tools_menu_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE parent_id=@sop_menu_id
      AND (
          path='script-tools'
          OR component='sop/scriptTools/index'
          OR perms='sop:scriptTools:view'
      )
    ORDER BY menu_id
    LIMIT 1
);

SET @image_sop_permission_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE path='image-sop'
       OR component='sop/imageSop/index'
       OR perms='sop:imageSop:use'
    ORDER BY CASE WHEN perms='sop:imageSop:use' THEN 0 ELSE 1 END,menu_id
    LIMIT 1
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '使用图片SOP',@script_tools_menu_id,2,'',NULL,NULL,'',
    1,0,'F','0','0','sop:imageSop:use','#',
    'SYSTEM',NOW(),'从脚本菜单新窗口直连Python图片SOP页面'
WHERE @script_tools_menu_id IS NOT NULL
  AND @image_sop_permission_id IS NULL;

SET @image_sop_permission_id := COALESCE(
    @image_sop_permission_id,
    (
        SELECT menu_id
        FROM sys_menu
        WHERE parent_id=@script_tools_menu_id
          AND perms='sop:imageSop:use'
        ORDER BY menu_id DESC
        LIMIT 1
    )
);

-- 原独立菜单转换为按钮权限后，不再出现在左侧菜单中。
UPDATE sys_menu
SET menu_name='使用图片SOP',
    parent_id=@script_tools_menu_id,
    order_num=2,
    path='',
    component=NULL,
    query=NULL,
    route_name='',
    is_frame=1,
    is_cache=0,
    menu_type='F',
    visible='0',
    status='0',
    perms='sop:imageSop:use',
    icon='#',
    update_by='SYSTEM',
    update_time=NOW(),
    remark='从脚本菜单新窗口直连Python图片SOP页面，不经过Java代理'
WHERE menu_id=@image_sop_permission_id;

-- 已有图片SOP权限的角色补齐SOP目录及脚本菜单权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT rm.role_id,@sop_menu_id
FROM sys_role_menu rm
WHERE rm.menu_id=@image_sop_permission_id
  AND @sop_menu_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT rm.role_id,@script_tools_menu_id
FROM sys_role_menu rm
WHERE rm.menu_id=@image_sop_permission_id
  AND @script_tools_menu_id IS NOT NULL;

-- 所有admin角色以及leiyongyu当前关联角色获得全部已启用菜单和按钮权限。
-- 若要控制普通用户能看到、使用哪些脚本，只需给其角色分配：
-- 1. SOP目录；2. 脚本菜单；3. 对应脚本的F类型按钮权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT role_info.role_id,menu_info.menu_id
FROM sys_role role_info
JOIN sys_menu menu_info ON menu_info.status='0'
WHERE role_info.role_key='admin'
  AND role_info.status='0'
  AND role_info.del_flag='0';

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT user_role.role_id,menu_info.menu_id
FROM sys_user user_info
JOIN sys_user_role user_role ON user_role.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=user_role.role_id
JOIN sys_menu menu_info ON menu_info.status='0'
WHERE user_info.user_name='leiyongyu'
  AND user_info.status='0'
  AND user_info.del_flag='0'
  AND role_info.status='0'
  AND role_info.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,
       menu_type,perms,status,visible,remark
FROM sys_menu
WHERE menu_id IN (
    @sop_menu_id,
    @script_tools_menu_id,
    @image_sop_permission_id
)
ORDER BY parent_id,order_num,menu_id;
