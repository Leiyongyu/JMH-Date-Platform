-- 财务中心“滞销清货”菜单、查询权限及 leiyongyu 授权。
-- 可重复执行。

SET @finance_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '滞销清货', @finance_menu_id, 4, 'slow-moving-clearance',
  'finance/slowMovingClearance/index', NULL, 'SlowMovingClearance',
  1, 0, 'C', '0', '0',
  'finance:slowMovingClearance:list', 'shopping',
  'SYSTEM', NOW(), '展示领星FBA库存月度快照全部库龄字段'
WHERE @finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_menu
    WHERE parent_id = @finance_menu_id
      AND path = 'slow-moving-clearance'
  );

SET @clearance_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND path = 'slow-moving-clearance'
  ORDER BY menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = '滞销清货',
    order_num = 4,
    component = 'finance/slowMovingClearance/index',
    route_name = 'SlowMovingClearance',
    visible = '0',
    status = '0',
    perms = 'finance:slowMovingClearance:list',
    icon = 'shopping',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '展示领星FBA库存月度快照全部库龄字段'
WHERE menu_id = @clearance_menu_id;

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '滞销清货查询', @clearance_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0',
  'finance:slowMovingClearance:list', '#',
  'SYSTEM', NOW(), '查看滞销清货库存与库龄'
WHERE @clearance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_menu
    WHERE parent_id = @clearance_menu_id
      AND perms = 'finance:slowMovingClearance:list'
  );

-- 清理旧版本的手动拉取权限；数据只能由 Quartz 定时任务同步。
DELETE rm
FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.parent_id = @clearance_menu_id
  AND m.perms = 'finance:slowMovingClearance:edit';

DELETE FROM sys_menu
WHERE parent_id = @clearance_menu_id
  AND perms = 'finance:slowMovingClearance:edit';

-- leiyongyu 所属的全部角色获得目录、页面和查询权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT ur.role_id, permission_menu.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN (
  SELECT @finance_menu_id AS menu_id
  UNION ALL
  SELECT @clearance_menu_id
  UNION ALL
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @clearance_menu_id
    AND perms = 'finance:slowMovingClearance:list'
) permission_menu ON permission_menu.menu_id IS NOT NULL
WHERE u.user_name = 'leiyongyu';

SELECT menu_id, parent_id, menu_name, path, component, menu_type, perms,
       visible, status
FROM sys_menu
WHERE menu_id = @clearance_menu_id
   OR parent_id = @clearance_menu_id
ORDER BY menu_id;

SELECT DISTINCT u.user_name, r.role_name, m.menu_id, m.menu_name, m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = r.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND (
    m.menu_id = @finance_menu_id
    OR m.menu_id = @clearance_menu_id
    OR m.parent_id = @clearance_menu_id
  )
ORDER BY r.role_name, m.menu_id;
