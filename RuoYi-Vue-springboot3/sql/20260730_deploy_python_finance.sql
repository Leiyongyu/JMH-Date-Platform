-- Java 库（通常为 jmh_data_platform）部署脚本。
-- 作用：
-- 1. 保持绩效排名和滞销清货菜单/权限可见；
-- 2. 将 job_id=240 的绩效任务切换到 Python ETL；
-- 3. 将原 FBA 库存任务切换到 Python ODS/DWD/DWS ETL。
-- 可重复执行。执行后需重启 Java 服务，让 Quartz 重新装载任务。

START TRANSACTION;

SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '滞销清货', @finance_menu_id, 4, 'slow-moving-clearance',
  'finance/slowMovingClearance/index', NULL, 'SlowMovingClearance',
  1, 0, 'C', '0', '0', 'finance:slowMovingClearance:list', 'shopping',
  'SYSTEM', NOW(), 'Python DWS展示EU、US1、US2、US3库龄汇总'
WHERE @finance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @finance_menu_id AND path = 'slow-moving-clearance'
  );

SET @clearance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id AND path = 'slow-moving-clearance'
  ORDER BY menu_id LIMIT 1
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
    remark = 'Python DWS展示EU、US1、US2、US3库龄汇总'
WHERE menu_id = @clearance_menu_id;

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '滞销清货查询', @clearance_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:slowMovingClearance:list', '#',
  'SYSTEM', NOW(), '查询Python滞销清货DWS数据'
WHERE @clearance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @clearance_menu_id
      AND perms = 'finance:slowMovingClearance:list'
  );

-- 页面禁止立即拉取，清理可能遗留的编辑/手工拉取按钮。
DELETE rm
FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.parent_id = @clearance_menu_id
  AND m.perms = 'finance:slowMovingClearance:edit';

DELETE FROM sys_menu
WHERE parent_id = @clearance_menu_id
  AND perms = 'finance:slowMovingClearance:edit';

-- leiyongyu 获得绩效排名和滞销清货现有菜单权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m
  ON m.menu_id IN (@finance_menu_id, @clearance_menu_id)
  OR m.parent_id = @clearance_menu_id
  OR m.perms IN (
    'finance:performanceRanking:list',
    'finance:performanceRanking:edit'
  )
WHERE u.user_name = 'leiyongyu';

UPDATE sys_job
SET job_name = 'Amazon月度完整订单利润同步',
    job_group = 'FINANCE',
    invoke_target = 'pythonPerformanceTask.syncPreviousMonth()',
    cron_expression = '0 0 22 4 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java Quartz调度；Python执行AMZ利润ODS/DWD/DWS及绩效排名'
WHERE job_id = 240
   OR invoke_target IN (
     'operationSyncTask.syncAmzMonthlyOrderProfit',
     'operationSyncTask.syncAmzMonthlyOrderProfit()',
     'pythonPerformanceTask.syncPreviousMonth',
     'pythonPerformanceTask.syncPreviousMonth()'
   );

UPDATE sys_job
SET job_name = '领星-Amazon FBA库存库龄同步',
    job_group = 'FINANCE',
    invoke_target = 'pythonFbaInventoryTask.syncCurrentMonth()',
    cron_expression = '0 30 22 1 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java Quartz调度；Python执行FBA库存ODS/DWD/DWS，每月1日22:30'
WHERE job_id = 241
   OR invoke_target IN (
     'operationSyncTask.syncAmzFbaInventorySnapshot',
     'operationSyncTask.syncAmzFbaInventorySnapshot()',
     'pythonFbaInventoryTask.syncCurrentMonth',
     'pythonFbaInventoryTask.syncCurrentMonth()'
   );

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status,
  create_by, create_time, remark
)
SELECT
  '领星-Amazon FBA库存库龄同步', 'FINANCE',
  'pythonFbaInventoryTask.syncCurrentMonth()', '0 30 22 1 * ?',
  '2', '1', '0', 'SYSTEM', NOW(),
  'Java Quartz调度；Python执行FBA库存ODS/DWD/DWS，每月1日22:30'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target IN (
    'pythonFbaInventoryTask.syncCurrentMonth',
    'pythonFbaInventoryTask.syncCurrentMonth()'
  )
);

COMMIT;

SELECT job_id, job_name, invoke_target, cron_expression, status
FROM sys_job
WHERE invoke_target IN (
  'pythonPerformanceTask.syncPreviousMonth()',
  'pythonFbaInventoryTask.syncCurrentMonth()'
)
ORDER BY job_id;
