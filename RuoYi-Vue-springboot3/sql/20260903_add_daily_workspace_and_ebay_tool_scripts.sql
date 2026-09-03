-- ============================================================================
-- Python脚本工作台：每日工作台 + eBay价格查询权限
-- 执行库：jmh_data_platform
-- 可重复执行：仅新增或修正F类型权限，不删除业务数据与现有角色权限。
-- ============================================================================

USE `jmh_data_platform`;
SET NAMES utf8mb4;

SET @script_tools_menu_id := (
    SELECT menu_id
    FROM sys_menu
    WHERE perms = 'sop:scriptTools:view'
      AND menu_type = 'C'
    ORDER BY menu_id
    LIMIT 1
);

INSERT INTO sys_menu (
    menu_name, parent_id, order_num, path, component, query, route_name,
    is_frame, is_cache, menu_type, visible, status, perms, icon,
    create_by, create_time, update_by, update_time, remark
)
SELECT
    '每日工作台', @script_tools_menu_id, 2, '', NULL, NULL, '',
    1, 0, 'F', '0', '0', 'sop:dailyWorkspace:use', '#',
    'SYSTEM', NOW(), 'SYSTEM', NOW(), 'Python脚本工作台：每日工作台使用权限'
WHERE @script_tools_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu WHERE perms = 'sop:dailyWorkspace:use'
  );

INSERT INTO sys_menu (
    menu_name, parent_id, order_num, path, component, query, route_name,
    is_frame, is_cache, menu_type, visible, status, perms, icon,
    create_by, create_time, update_by, update_time, remark
)
SELECT
    'eBay价格查询', @script_tools_menu_id, 3, '', NULL, NULL, '',
    1, 0, 'F', '0', '0', 'sop:ebayTool:use', '#',
    'SYSTEM', NOW(), 'SYSTEM', NOW(), 'Python脚本工作台：eBay价格查询使用权限'
WHERE @script_tools_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu WHERE perms = 'sop:ebayTool:use'
  );

SET @daily_workspace_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'sop:dailyWorkspace:use'
    ORDER BY menu_id LIMIT 1
);
SET @ebay_tool_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'sop:ebayTool:use'
    ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name = '每日工作台', parent_id = @script_tools_menu_id,
    order_num = 2, path = '', component = NULL, query = NULL, route_name = '',
    is_frame = 1, is_cache = 0, menu_type = 'F', visible = '0', status = '0',
    icon = '#', update_by = 'SYSTEM', update_time = NOW(),
    remark = 'Python脚本工作台：每日工作台使用权限'
WHERE menu_id = @daily_workspace_menu_id
  AND @script_tools_menu_id IS NOT NULL;

UPDATE sys_menu
SET menu_name = 'eBay价格查询', parent_id = @script_tools_menu_id,
    order_num = 3, path = '', component = NULL, query = NULL, route_name = '',
    is_frame = 1, is_cache = 0, menu_type = 'F', visible = '0', status = '0',
    icon = '#', update_by = 'SYSTEM', update_time = NOW(),
    remark = 'Python脚本工作台：eBay价格查询使用权限'
WHERE menu_id = @ebay_tool_menu_id
  AND @script_tools_menu_id IS NOT NULL;

-- leiyongyu当前关联的所有有效角色获得脚本菜单及两个组件权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT user_role.role_id, menu_info.menu_id
FROM sys_user user_info
JOIN sys_user_role user_role ON user_role.user_id = user_info.user_id
JOIN sys_role role_info ON role_info.role_id = user_role.role_id
JOIN sys_menu menu_info
  ON menu_info.menu_id IN (
      @script_tools_menu_id, @daily_workspace_menu_id, @ebay_tool_menu_id
  )
WHERE user_info.user_name = 'leiyongyu'
  AND user_info.status = '0'
  AND user_info.del_flag = '0'
  AND role_info.status = '0'
  AND role_info.del_flag = '0'
  AND menu_info.menu_id IS NOT NULL;

SELECT menu_id, parent_id, menu_name, menu_type, perms, order_num, status, visible
FROM sys_menu
WHERE menu_id IN (
    @script_tools_menu_id, @daily_workspace_menu_id, @ebay_tool_menu_id
)
ORDER BY parent_id, order_num, menu_id;
