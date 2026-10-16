-- 仅新增负责人导出字段权限，无业务表结构变更。
-- 执行已有导出字段/导出总开关脚本后执行本脚本；页面负责人列不需要该导出权限。
USE jmh_data_platform;
START TRANSACTION;
SET @owner_export_parent = (SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:export' AND menu_type='F' ORDER BY menu_id LIMIT 1);
SET @owner_export_new = NOT EXISTS (SELECT 1 FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:exportColumn:principal_name');
INSERT INTO sys_menu (menu_name,parent_id,order_num,path,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time)
SELECT '导出字段-负责人',@owner_export_parent,142,'',1,0,'F','0','0',
       'operations:ebayReplenishmentV2:exportColumn:principal_name','#','SYSTEM',NOW()
WHERE @owner_export_parent IS NOT NULL AND @owner_export_new=1;
-- 仅首次创建时给已拥有导出权限的系统管理员角色默认启用；其他角色按需勾选。
INSERT INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,m.menu_id FROM sys_role r
JOIN sys_role_menu allowed ON allowed.role_id=r.role_id AND allowed.menu_id=@owner_export_parent
JOIN sys_menu m ON m.perms='operations:ebayReplenishmentV2:exportColumn:principal_name'
WHERE @owner_export_new=1 AND r.role_key='admin' AND r.status='0' AND r.del_flag='0'
AND NOT EXISTS (SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id);
COMMIT;
