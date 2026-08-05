-- 滞销清货“导入上月库存成本”按钮权限。
-- 可重复执行；执行库：jmh_data_platform。

SET @clearance_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE component = 'finance/slowMovingClearance/index'
     OR path = 'slow-moving-clearance'
  ORDER BY CASE WHEN component = 'finance/slowMovingClearance/index' THEN 0 ELSE 1 END,
           menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '库存成本导入', @clearance_menu_id, 2, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:slowMovingClearance:import', '#',
  'SYSTEM', NOW(), '导入每月部门海外仓库龄成本文件'
WHERE @clearance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @clearance_menu_id
      AND perms = 'finance:slowMovingClearance:import'
  );

SET @clearance_import_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @clearance_menu_id
    AND perms = 'finance:slowMovingClearance:import'
  ORDER BY menu_id
  LIMIT 1
);

-- 已有滞销清货页面权限的角色自动获得导入权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT rm.role_id, @clearance_import_menu_id
FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.perms = 'finance:slowMovingClearance:list'
  AND @clearance_import_menu_id IS NOT NULL;
