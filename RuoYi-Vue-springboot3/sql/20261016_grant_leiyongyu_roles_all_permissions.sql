-- 按用户要求：为 leiyongyu 当前绑定的全部有效角色补齐现有有效菜单/按钮权限。
-- 注意：同角色的其他用户也会获得这些权限，并非只对 leiyongyu 单独生效。
-- 不更改角色数据范围，不自动授予未来新增权限，不删除或撤销任何已有授权。
-- 执行顺序：先执行 20261015_ebay_replenishment_v2_review.sql，
-- 再执行 20261016_ebay_replenishment_v2_purchase_permission.sql，最后执行本文件。
-- 本文件仅交付部署执行，开发过程中未执行该全量授权。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

-- 执行前核对目标角色和受影响的有效用户数；无结果时先核实账号/角色状态。
SELECT DISTINCT r.role_id, r.role_name, r.role_key,
       (SELECT COUNT(DISTINCT role_user.user_id)
          FROM sys_user_role member_role
          JOIN sys_user role_user ON role_user.user_id = member_role.user_id
         WHERE member_role.role_id = r.role_id
           AND role_user.del_flag = '0' AND role_user.status = '0') AS active_user_count
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
WHERE u.user_name = 'leiyongyu' AND u.del_flag = '0' AND u.status = '0'
  AND r.del_flag = '0' AND r.status = '0';

START TRANSACTION;
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT r.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
CROSS JOIN sys_menu m
WHERE u.user_name = 'leiyongyu' AND u.del_flag = '0' AND u.status = '0'
  AND r.del_flag = '0' AND r.status = '0'
  AND m.status = '0' AND m.menu_type IN ('M', 'C', 'F')
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu existing
      WHERE existing.role_id = r.role_id AND existing.menu_id = m.menu_id
  );
SELECT ROW_COUNT() AS added_role_menu_count;
COMMIT;

-- 执行后每个目标角色 missing_active_menu_count 应为 0；可重复执行。
SELECT r.role_id, r.role_name, COUNT(m.menu_id) AS missing_active_menu_count
FROM sys_role r
LEFT JOIN sys_menu m ON m.status = '0' AND m.menu_type IN ('M', 'C', 'F')
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu existing
      WHERE existing.role_id = r.role_id AND existing.menu_id = m.menu_id
  )
WHERE r.del_flag = '0' AND r.status = '0'
  AND EXISTS (
      SELECT 1 FROM sys_user u
      JOIN sys_user_role ur ON ur.user_id = u.user_id
      WHERE ur.role_id = r.role_id AND u.user_name = 'leiyongyu'
        AND u.del_flag = '0' AND u.status = '0'
  )
GROUP BY r.role_id, r.role_name;

-- 执行后授权账号退出重新登录，以刷新登录会话中的权限。
