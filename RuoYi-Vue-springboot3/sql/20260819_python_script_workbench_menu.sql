-- 将“SOP > 脚本菜单”改为 Java 鉴权后的 Python 统一脚本工作台网关。
-- 仅在 Java ERP 数据库 jmh_data_platform 执行；不修改 Date-Project 数据库。

USE `jmh_data_platform`;
SET NAMES utf8mb4;

SET @script_tools_menu_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE menu_type='C'
      AND (
          path='script-tools'
          OR component='sop/scriptTools/index'
          OR perms='sop:scriptTools:view'
      )
    ORDER BY CASE WHEN perms='sop:scriptTools:view' THEN 0 ELSE 1 END, menu_id
    LIMIT 1
);

UPDATE sys_menu
SET menu_name='脚本菜单',
    path='script-tools',
    component='sop/scriptTools/index',
    query=NULL,
    route_name='PythonScriptWorkbench',
    is_frame=1,
    is_cache=0,
    menu_type='C',
    visible='0',
    status='0',
    perms='sop:scriptTools:view',
    icon='code',
    update_by='SYSTEM',
    update_time=NOW(),
    remark='Java读取当前用户权限并签发会话后加载Python统一脚本工作台'
WHERE menu_id=@script_tools_menu_id;

-- 原“图片SOP”独立页面统一转换为脚本工作台下的按钮权限，避免加载已删除的ERP页面。
SET @image_sop_permission_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE perms='sop:imageSop:use'
       OR component='sop/imageSop/index'
       OR path='image-sop'
    ORDER BY CASE WHEN perms='sop:imageSop:use' THEN 0 ELSE 1 END, menu_id
    LIMIT 1
);

UPDATE sys_menu
SET menu_name='使用图片SOP',
    parent_id=@script_tools_menu_id,
    order_num=1,
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
    remark='控制Python脚本工作台中的图片SOP组件及Java安全代理访问权'
WHERE menu_id=@image_sop_permission_id
  AND @script_tools_menu_id IS NOT NULL;

-- 已有图片SOP权限的角色自动获得脚本菜单入口。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT role_menu.role_id, @script_tools_menu_id
FROM sys_role_menu role_menu
WHERE role_menu.menu_id=@image_sop_permission_id
  AND @script_tools_menu_id IS NOT NULL;

-- leiyongyu 当前关联的有效角色保留脚本菜单及图片 SOP 使用权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT user_role.role_id, menu_info.menu_id
FROM sys_user user_info
JOIN sys_user_role user_role ON user_role.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=user_role.role_id
JOIN sys_menu menu_info
  ON menu_info.menu_id=@script_tools_menu_id
  OR menu_info.perms='sop:imageSop:use'
WHERE user_info.user_name='leiyongyu'
  AND user_info.status='0'
  AND user_info.del_flag='0'
  AND role_info.status='0'
  AND role_info.del_flag='0';

SELECT menu_id,parent_id,menu_name,path,component,route_name,
       is_frame,menu_type,perms,status,visible,remark
FROM sys_menu
WHERE menu_id=@script_tools_menu_id
   OR perms='sop:imageSop:use'
ORDER BY parent_id,order_num,menu_id;
