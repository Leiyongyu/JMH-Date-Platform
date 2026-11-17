-- 目标库：jmh_data_platform。
-- 滞销清货已改为直接读取上一个自然月的库龄快照成本，不再保留人工导入权限。

DELETE rm
FROM sys_role_menu rm
INNER JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.perms = 'finance:slowMovingClearance:import';

DELETE FROM sys_menu
WHERE perms = 'finance:slowMovingClearance:import';

SELECT menu_id, menu_name, perms
FROM sys_menu
WHERE perms IN (
    'finance:slowMovingClearance:list',
    'finance:slowMovingClearance:import'
)
ORDER BY menu_id;
