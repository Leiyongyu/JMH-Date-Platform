-- 用户明确授权：仅授予 leiyongyu 当前全部菜单/按钮和全部数据范围。
-- 不修改共享角色，不修改密码，不授予数据库账户权限，不删除业务数据。
-- 专用角色不允许绑定其他账号；前置检查失败时不写入，结果为 REFUSED。
-- 已停用菜单不会被启用；未来新增菜单须重新执行本脚本。执行后退出重新登录。
USE `jmh_data_platform`;
SET @grant_lock = GET_LOCK('grant_leiyongyu_all_permissions', 15);
START TRANSACTION;
SELECT user_id FROM sys_user WHERE user_name='leiyongyu' FOR UPDATE;
SELECT role_id FROM sys_role WHERE role_key='leiyongyu_all_permissions' FOR UPDATE;
SET @target_user = (SELECT MIN(user_id) FROM sys_user WHERE user_name='leiyongyu' AND status='0' AND del_flag='0');
SET @grant_ok = (
    @grant_lock = 1
    AND (SELECT COUNT(*) FROM sys_user WHERE user_name='leiyongyu') = 1
    AND @target_user IS NOT NULL AND @target_user <> 1
    AND (SELECT COUNT(*) FROM sys_role WHERE role_key='leiyongyu_all_permissions') <= 1
    AND NOT EXISTS (
        SELECT 1 FROM sys_role r WHERE r.role_key='leiyongyu_all_permissions'
        AND (r.role_id=1 OR r.status<>'0' OR r.del_flag<>'0')
    )
    AND NOT EXISTS (
        SELECT 1 FROM sys_role r JOIN sys_user_role ur ON ur.role_id=r.role_id
        WHERE r.role_key='leiyongyu_all_permissions' AND ur.user_id<>@target_user
    )
);
INSERT INTO sys_role
    (role_name,role_key,role_sort,data_scope,menu_check_strictly,dept_check_strictly,
     status,del_flag,create_by,create_time,remark)
SELECT 'leiyongyu全权限专用','leiyongyu_all_permissions',2,'1',1,1,
       '0','0','SYSTEM',NOW(),'仅leiyongyu使用；当前全部菜单按钮；新增菜单需重新授权'
WHERE @grant_ok=1
  AND NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key='leiyongyu_all_permissions');
SET @target_role = (SELECT MIN(role_id) FROM sys_role WHERE role_key='leiyongyu_all_permissions');
UPDATE sys_role SET data_scope='1',update_by='SYSTEM',update_time=NOW()
WHERE role_id=@target_role AND @grant_ok=1 AND NOT (data_scope <=> '1');
INSERT IGNORE INTO sys_user_role(user_id,role_id)
SELECT @target_user,@target_role WHERE @grant_ok=1;
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT @target_role,menu_id FROM sys_menu WHERE @grant_ok=1;
COMMIT;
SELECT IF(@grant_ok=1,'GRANTED','REFUSED: account/role/lock precondition failed') AS grant_status,
       @target_user AS user_id,@target_role AS role_id;
SELECT COUNT(*) AS granted_menus FROM sys_role_menu WHERE role_id=@target_role;
SELECT COUNT(*) AS missing_menus FROM sys_menu m
WHERE NOT EXISTS (SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=@target_role AND rm.menu_id=m.menu_id);
SELECT COUNT(DISTINCT m.perms) AS active_permission_codes
FROM sys_menu m JOIN sys_role_menu rm ON rm.menu_id=m.menu_id
WHERE rm.role_id=@target_role AND m.status='0' AND COALESCE(m.perms,'')<>'';
SELECT m.menu_id,m.perms FROM sys_menu m JOIN sys_role_menu rm ON rm.menu_id=m.menu_id
WHERE rm.role_id=@target_role AND m.perms='procurement:pendingPurchase:remove';
SELECT RELEASE_LOCK('grant_leiyongyu_all_permissions') AS lock_released;
