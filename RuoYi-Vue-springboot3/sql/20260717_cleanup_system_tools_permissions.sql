-- ============================================================
-- ERP菜单与权限清理：删除系统工具/若依官网，保留系统监控，限制超级管理员人数
-- 目标库：jmh_data_platform
-- 可重复执行。
-- ============================================================

USE `jmh_data_platform`;

-- 1. 删除系统工具菜单及其子菜单、按钮权限；删除若依官网外链菜单。
DELETE rm
FROM sys_role_menu rm
JOIN (
    SELECT menu_id FROM (
        SELECT p.menu_id
        FROM sys_menu p
        WHERE p.path = 'tool'
           OR p.component LIKE 'tool/%'
           OR p.perms LIKE 'tool:%'
           OR p.menu_name = '系统工具'
           OR p.menu_name IN ('若依官网', '若依文档')
           OR p.path LIKE 'http%ruoyi%'
        UNION
        SELECT c.menu_id
        FROM sys_menu c
        JOIN sys_menu p ON c.parent_id = p.menu_id
        WHERE p.path = 'tool'
           OR p.component LIKE 'tool/%'
           OR p.perms LIKE 'tool:%'
           OR p.menu_name = '系统工具'
           OR p.menu_name IN ('若依官网', '若依文档')
           OR p.path LIKE 'http%ruoyi%'
        UNION
        SELECT g.menu_id
        FROM sys_menu g
        JOIN sys_menu c ON g.parent_id = c.menu_id
        JOIN sys_menu p ON c.parent_id = p.menu_id
        WHERE p.path = 'tool'
           OR p.component LIKE 'tool/%'
           OR p.perms LIKE 'tool:%'
           OR p.menu_name = '系统工具'
           OR p.menu_name IN ('若依官网', '若依文档')
           OR p.path LIKE 'http%ruoyi%'
    ) ids
) t ON t.menu_id = rm.menu_id;

DELETE m
FROM sys_menu m
JOIN (
    SELECT menu_id FROM (
        SELECT p.menu_id
        FROM sys_menu p
        WHERE p.path = 'tool'
           OR p.component LIKE 'tool/%'
           OR p.perms LIKE 'tool:%'
           OR p.menu_name = '系统工具'
           OR p.menu_name IN ('若依官网', '若依文档')
           OR p.path LIKE 'http%ruoyi%'
        UNION
        SELECT c.menu_id
        FROM sys_menu c
        JOIN sys_menu p ON c.parent_id = p.menu_id
        WHERE p.path = 'tool'
           OR p.component LIKE 'tool/%'
           OR p.perms LIKE 'tool:%'
           OR p.menu_name = '系统工具'
           OR p.menu_name IN ('若依官网', '若依文档')
           OR p.path LIKE 'http%ruoyi%'
        UNION
        SELECT g.menu_id
        FROM sys_menu g
        JOIN sys_menu c ON g.parent_id = c.menu_id
        JOIN sys_menu p ON c.parent_id = p.menu_id
        WHERE p.path = 'tool'
           OR p.component LIKE 'tool/%'
           OR p.perms LIKE 'tool:%'
           OR p.menu_name = '系统工具'
           OR p.menu_name IN ('若依官网', '若依文档')
           OR p.path LIKE 'http%ruoyi%'
    ) ids
) t ON t.menu_id = m.menu_id;

-- 2. 保留系统监控菜单并确保可见可用。
UPDATE sys_menu
SET visible = '0',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE path = 'monitor' OR menu_name = '系统监控';

UPDATE sys_menu c
JOIN sys_menu p ON c.parent_id = p.menu_id
SET c.visible = '0',
    c.status = '0',
    c.update_by = 'SYSTEM',
    c.update_time = NOW()
WHERE p.path = 'monitor'
  AND c.menu_name IN ('数据监控', '服务监控', '缓存监控', '缓存列表');

-- 3. 字段管理、参数设置保留，但仅给管理员/运维角色。
-- 说明：字段管理通常是 sys_user_column_config/列配置能力；参数设置是 sys_config。
SET @ops_role_id := (
    SELECT role_id
    FROM sys_role
    WHERE role_key IN ('admin', 'ops', 'operation_admin', 'yunwei')
       OR role_name IN ('超级管理员', '系统管理员', '运维管理员', '管理员')
    ORDER BY CASE WHEN role_key = 'admin' THEN 0 ELSE 1 END, role_id
    LIMIT 1
);

DELETE rm
FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE (
        m.perms LIKE 'system:config:%'
     OR m.path = 'config'
     OR m.menu_name IN ('参数设置', '字段管理')
     OR m.perms LIKE 'system:columnConfig:%'
      )
  AND rm.role_id <> IFNULL(@ops_role_id, -1);

INSERT IGNORE INTO sys_role_menu(role_id, menu_id)
SELECT @ops_role_id, m.menu_id
FROM sys_menu m
WHERE @ops_role_id IS NOT NULL
  AND (
        m.perms LIKE 'system:config:%'
     OR m.path = 'config'
     OR m.menu_name IN ('参数设置', '字段管理')
     OR m.perms LIKE 'system:columnConfig:%'
      );

-- 4. 超级管理员保留，但最多只保留 3 个用户绑定。
-- 保留规则：按 user_id 从小到大保留前 3 个，其余解绑当前 role_key=admin 的角色。
SET @admin_role_id := (
    SELECT role_id
    FROM sys_role
    WHERE role_key = 'admin'
      AND del_flag = '0'
    ORDER BY role_id
    LIMIT 1
);

DELETE ur
FROM sys_user_role ur
JOIN (
    SELECT user_id
    FROM (
        SELECT user_id,
               ROW_NUMBER() OVER (ORDER BY user_id) AS rn
        FROM sys_user_role
        WHERE role_id = @admin_role_id
    ) x
    WHERE x.rn > 3
) extra ON extra.user_id = ur.user_id
WHERE ur.role_id = @admin_role_id;

-- 5. 验证结果。
SELECT 'system_tool_menu_remaining' AS check_item, COUNT(*) AS value
FROM sys_menu
WHERE path = 'tool'
   OR component LIKE 'tool/%'
   OR perms LIKE 'tool:%'
   OR menu_name = '系统工具'
   OR menu_name IN ('若依官网', '若依文档')
   OR path LIKE 'http%ruoyi%';

SELECT 'super_admin_user_count' AS check_item, COUNT(*) AS value
FROM sys_user_role
WHERE role_id = @admin_role_id;

SELECT 'monitor_menu_count' AS check_item, COUNT(*) AS value
FROM sys_menu
WHERE path = 'monitor'
   OR menu_name IN ('系统监控', '数据监控', '服务监控', '缓存监控', '缓存列表');
