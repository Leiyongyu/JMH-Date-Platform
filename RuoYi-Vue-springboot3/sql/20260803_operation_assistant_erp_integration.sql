-- 运营中心 / 运营助手菜单、接口权限及 leiyongyu 授权。
-- 仅操作 sys_menu、sys_role_menu，不创建或修改任何业务表，可重复执行。

SET @operations_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE menu_type = 'M'
    AND (
      path = 'operations'
      OR menu_name = '运营中心'
    )
  ORDER BY CASE WHEN path = 'operations' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '运营助手', @operations_menu_id, 99, 'operation-assistant',
  'operations/assistant/index', NULL, 'OperationAssistant',
  1, 0, 'C', '0', '0',
  'operations:assistant:view', 'tool',
  'SYSTEM', NOW(), 'ERP统一鉴权入口；业务由OperationAssistant服务提供'
WHERE @operations_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM sys_menu
    WHERE parent_id = @operations_menu_id
      AND path = 'operation-assistant'
  );

SET @assistant_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @operations_menu_id
    AND path = 'operation-assistant'
  ORDER BY menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = '运营助手',
    order_num = 99,
    component = 'operations/assistant/index',
    route_name = 'OperationAssistant',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'operations:assistant:view',
    icon = 'tool',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'ERP统一鉴权入口；业务由OperationAssistant服务提供'
WHERE menu_id = @assistant_menu_id;

-- 管理员角色显式获得菜单，避免不同环境中 admin 角色菜单关系不完整。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT r.role_id, permission_menu.menu_id
FROM sys_role r
JOIN (
  SELECT @operations_menu_id AS menu_id
  UNION ALL
  SELECT @assistant_menu_id
) permission_menu ON permission_menu.menu_id IS NOT NULL
WHERE r.role_key = 'admin'
  AND r.status = '0';

-- leiyongyu 当前拥有的全部角色获得运营中心和运营助手权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT ur.role_id, permission_menu.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN (
  SELECT @operations_menu_id AS menu_id
  UNION ALL
  SELECT @assistant_menu_id
) permission_menu ON permission_menu.menu_id IS NOT NULL
WHERE u.user_name = 'leiyongyu';

-- 部署检查：第一条结果为空表示当前库没有“运营中心”目录，需要先部署基础菜单。
SELECT menu_id, parent_id, menu_name, order_num, path, component,
       route_name, menu_type, perms, visible, status
FROM sys_menu
WHERE menu_id IN (@operations_menu_id, @assistant_menu_id)
ORDER BY parent_id, order_num, menu_id;

SELECT DISTINCT u.user_name, r.role_id, r.role_name,
       m.menu_id, m.menu_name, m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = r.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND m.menu_id IN (@operations_menu_id, @assistant_menu_id)
ORDER BY r.role_id, m.menu_id;
