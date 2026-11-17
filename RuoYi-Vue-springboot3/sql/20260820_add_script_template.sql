-- ============================================================================
-- 新增脚本模板（勿直接整段执行，按注释替换占位符后再执行）
-- 用途：给「SOP > 脚本菜单」新增一个脚本按钮权限，控制哪些角色/用户可见。
-- 执行库：jmh_data_platform（仅 ERP 菜单库，不影响 Date-Project 库）
--
-- 新增一个脚本需要三步（详见 Date-Project/docs/脚本菜单-新增脚本指南.md）：
--   1) 编写并挂载 Python 脚本页面（FastAPI 路由或静态页）；
--   2) 在 Date-Project/frontend/src/scripts.js 注册表加一条（permission 字段与下面 perms 一致）；
--   3) 执行下面的 SQL 新增按钮权限并授权（perms 与注册表 permission 一致）。
-- ============================================================================

USE `jmh_data_platform`;
SET NAMES utf8mb4;

-- 1. 找到「脚本菜单」目录的 menu_id（本模板自动查找，无需手填）
SET @script_tools_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'sop:scriptTools:view' AND menu_type = 'C'
    LIMIT 1
);

-- 2. 新增脚本按钮权限（占位符按需替换）
--    @NEW_PERMS   例如 'sop:myScript:use'（必须与 scripts.js 的 permission 一致）
--    @NEW_NAME    例如 '使用我的脚本'
--    @NEW_ORDER   显示排序，例如 2
SET @NEW_PERMS := 'sop:myScript:use';
SET @NEW_NAME  := '使用我的脚本';
SET @NEW_ORDER := 2;

INSERT INTO sys_menu (
    menu_name, parent_id, order_num, path, component, query, route_name,
    is_frame, is_cache, menu_type, visible, status, perms, icon,
    create_by, create_time, update_by, update_time, remark
) VALUES (
    @NEW_NAME, @script_tools_menu_id, @NEW_ORDER, '', NULL, NULL, '',
    1, 0, 'F', '0', '0', @NEW_PERMS, '#',
    'SYSTEM', NOW(), 'SYSTEM', NOW(), 'Python 脚本工作台按钮权限'
);

-- 3. 给指定角色授权（把 @ROLE_ID 替换为目标角色 ID；重复执行不会重复插入）
SET @ROLE_ID := 2;  -- 例如普通运营角色
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT @ROLE_ID, menu_id FROM sys_menu WHERE perms = @NEW_PERMS;

-- 4. 核对结果
SELECT menu_id, parent_id, menu_name, menu_type, perms, order_num, status
FROM sys_menu
WHERE menu_id = @script_tools_menu_id OR perms = @NEW_PERMS
ORDER BY parent_id, order_num, menu_id;
