-- 清理报表中心菜单及角色权限。可重复执行。

DELETE rm
FROM sys_role_menu rm
JOIN (
  SELECT menu_id FROM (
    SELECT p.menu_id
    FROM sys_menu p
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT c.menu_id
    FROM sys_menu c
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT g.menu_id
    FROM sys_menu g
    JOIN sys_menu c ON g.parent_id = c.menu_id
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
  ) ids
) t ON t.menu_id = rm.menu_id;

DELETE m
FROM sys_menu m
JOIN (
  SELECT menu_id FROM (
    SELECT p.menu_id
    FROM sys_menu p
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT c.menu_id
    FROM sys_menu c
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
    UNION
    SELECT g.menu_id
    FROM sys_menu g
    JOIN sys_menu c ON g.parent_id = c.menu_id
    JOIN sys_menu p ON c.parent_id = p.menu_id
    WHERE p.path = 'report'
       OR p.component LIKE 'report/%'
       OR p.perms LIKE 'report:%'
       OR p.menu_name = '报表中心'
  ) ids
) t ON t.menu_id = m.menu_id;

SELECT COUNT(*) AS remaining_report_menu_count
FROM sys_menu
WHERE path = 'report'
   OR component LIKE 'report/%'
   OR perms LIKE 'report:%'
   OR menu_name = '报表中心';
