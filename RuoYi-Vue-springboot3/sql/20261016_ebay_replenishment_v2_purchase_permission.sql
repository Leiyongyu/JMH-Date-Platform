-- eBay补货2.0最后操作列的独立采购权限。可重复执行；仅新增，不撤销任何既有权限。
-- 目标库：jmh_data_platform。先部署补货2.0主菜单；执行后授权账号退出重新登录。
-- 同一角色的所有用户共享权限。系统内置全权限超级管理员保持原有行为。
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;
SET @replenishment_page_id := (
  SELECT menu_id FROM sys_menu
  WHERE perms='operations:ebayReplenishmentV2:list' AND menu_type='C' AND status='0'
  ORDER BY menu_id LIMIT 1
);
INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark
)
SELECT '采购',@replenishment_page_id,30,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:purchase','#','SYSTEM',NOW(),
       '仅控制eBay补货2.0最后操作列采购按钮及对应提交接口，不授予采购中心其他权限'
WHERE @replenishment_page_id IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:ebayReplenishmentV2:purchase');

INSERT INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_menu m ON m.perms='operations:ebayReplenishmentV2:purchase'
  AND m.parent_id=@replenishment_page_id AND m.menu_type='F' AND m.status='0'
WHERE u.user_name='leiyongyu' AND u.del_flag='0' AND u.status='0'
  AND r.del_flag='0' AND r.status='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=r.role_id AND rm.menu_id=m.menu_id);
COMMIT;

SELECT m.menu_id,m.menu_name,m.parent_id,m.perms,r.role_id,r.role_name
FROM sys_menu m LEFT JOIN sys_role_menu rm ON rm.menu_id=m.menu_id
LEFT JOIN sys_role r ON r.role_id=rm.role_id
WHERE m.perms='operations:ebayReplenishmentV2:purchase';
-- 最后应返回补货2.0下的“采购”按钮及leiyongyu对应有效角色。无结果时先检查补货2.0主菜单是否已部署。
