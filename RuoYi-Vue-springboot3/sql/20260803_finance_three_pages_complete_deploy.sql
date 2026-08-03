-- ============================================================================
-- 财务中心三个页面完整部署脚本（仅 jmh_data_platform）
-- 日期：2026-08-03
--
-- 页面与数据链路：
-- 1. 绩效排名
--    前端页面：finance/performanceRanking/index
--    ERP接口：/finance/performance-ranking/**
--      GET  /months、/list、/owner-rules/summary、/ebay/list、/ebay/owner-rules/summary
--      POST /refresh、/owner-rules/import、/ebay/refresh、/ebay/profit/import、
--           /ebay/owner-rules/import
--    Python接口前缀：http://Date-Project/api/v1/finance
--    数据源：Python绩效 ODS/DWD/DWS；Java只做鉴权和REST代理。
--    Quartz：pythonPerformanceTask.syncPreviousMonth()
--    调度接口：POST /api/v1/internal/scheduler/tasks/amz_monthly_order_profit_sync/run
--    时间：每月4日22:00，处理上一个自然月。
--
-- 2. 滞销清货
--    前端页面：finance/slowMovingClearance/index
--    ERP接口：/finance/slow-moving-clearance/**
--      GET /list、/summary、/months
--    Python接口前缀：http://Date-Project/api/v1/finance
--    数据源：领星FBA库存 -> Python ODS/DWD/DWS库龄分组；Java只做鉴权和REST代理。
--    Quartz：pythonFbaInventoryTask.syncCurrentMonth()
--    调度接口：POST /api/v1/internal/scheduler/tasks/amz_fba_inventory_snapshot_sync/run
--    时间：每月1日22:30。
--
-- 3. 外汇退税
--    前端页面：finance/exportTaxRefund/index
--    ERP接口：/finance/export-tax-refund/**
--      POST /imports/customs-folder、/imports/purchase-invoice-summary、
--           /imports/foreign-exchange-receipts、/declaration-batches、/packages
--      GET  /import-jobs/{jobId}、/customs-declarations、/packages/latest/file、/inventory
--    Python服务地址：http://Date-Project（默认 http://127.0.0.1:8010）
--    数据源：用户上传报关资料、采购发票汇总、外汇回款文件；Java只做鉴权和REST代理。
--    该页面是人工导入、生成、下载流程，没有Quartz数据拉取任务。
--
-- Java部署环境变量（不是数据库字段）：
-- PERFORMANCE_PYTHON_BASE_URL=http://127.0.0.1:8010/api/v1/finance
-- PYTHON_PERFORMANCE_BASE_URL=http://127.0.0.1:8010
-- TAX_REFUND_DATA_PROJECT_BASE_URL=http://127.0.0.1:8010
-- PYTHON_PERFORMANCE_INTERNAL_TOKEN=与Date-Project一致的内部令牌（如启用）
--
-- 安全边界：
-- * 只操作 sys_menu、sys_role_menu、sys_job 三张若依系统配置表；
-- * 不创建、不修改、不删除、不清空任何业务数据表；
-- * 不处理 Date-Project 数据库；
-- * 可重复执行；已有菜单和任务只规范当前三个页面及对应任务的配置；
-- * 执行后需重启Java服务，或在若依任务管理中保存一次任务，使Quartz重新装载。
-- ============================================================================

USE `jmh_data_platform`;

START TRANSACTION;

-- ----------------------------------------------------------------------------
-- 一、财务中心目录
-- ----------------------------------------------------------------------------
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '财务中心', 0, 1, 'finance', NULL, NULL, 'Finance',
  1, 0, 'M', '0', '0', '', 'money',
  'SYSTEM', NOW(), '财务中心功能目录'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu
  WHERE parent_id = 0 AND path = 'finance' AND menu_type = 'M'
);

SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = 0 AND path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id LIMIT 1
);

-- 只规范精确匹配的财务目录，不处理其他顶级菜单。
UPDATE sys_menu
SET menu_name = '财务中心',
    component = NULL,
    route_name = 'Finance',
    visible = '0',
    status = '0',
    icon = 'money',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE menu_id = @finance_menu_id;

-- ----------------------------------------------------------------------------
-- 二、绩效排名菜单及权限
-- ----------------------------------------------------------------------------
SET @performance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND (path = 'performance-ranking'
         OR component = 'finance/performanceRanking/index')
  ORDER BY CASE WHEN path = 'performance-ranking' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '绩效排名', @finance_menu_id, 3, 'performance-ranking',
  'finance/performanceRanking/index', NULL, 'PerformanceRanking',
  1, 0, 'C', '0', '0', 'finance:performanceRanking:list', 'ranking',
  'SYSTEM', NOW(), 'Java REST代理Python绩效排名数据'
WHERE @finance_menu_id IS NOT NULL
  AND @performance_menu_id IS NULL;

SET @performance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND (path = 'performance-ranking'
         OR component = 'finance/performanceRanking/index')
  ORDER BY CASE WHEN path = 'performance-ranking' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = '绩效排名',
    parent_id = @finance_menu_id,
    order_num = 3,
    path = 'performance-ranking',
    component = 'finance/performanceRanking/index',
    route_name = 'PerformanceRanking',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'finance:performanceRanking:list',
    icon = 'ranking',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java REST代理Python绩效排名数据'
WHERE menu_id = @performance_menu_id;

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '绩效排名查询', @performance_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:performanceRanking:list', '#',
  'SYSTEM', NOW(), '查看月份、排名和负责人规则摘要'
WHERE @performance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @performance_menu_id
      AND perms = 'finance:performanceRanking:list'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '绩效排名编辑', @performance_menu_id, 2, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:performanceRanking:edit', '#',
  'SYSTEM', NOW(), '刷新排名及导入负责人、eBay利润规则'
WHERE @performance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @performance_menu_id
      AND perms = 'finance:performanceRanking:edit'
  );

UPDATE sys_menu
SET menu_name = CASE perms
      WHEN 'finance:performanceRanking:list' THEN '绩效排名查询'
      WHEN 'finance:performanceRanking:edit' THEN '绩效排名编辑'
      ELSE menu_name END,
    order_num = CASE perms
      WHEN 'finance:performanceRanking:list' THEN 1
      WHEN 'finance:performanceRanking:edit' THEN 2
      ELSE order_num END,
    visible = '0',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE parent_id = @performance_menu_id
  AND perms IN (
    'finance:performanceRanking:list',
    'finance:performanceRanking:edit'
  );

-- ----------------------------------------------------------------------------
-- 三、滞销清货菜单及权限（页面没有“立即拉取”按钮和edit权限）
-- ----------------------------------------------------------------------------
SET @clearance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND (path = 'slow-moving-clearance'
         OR component = 'finance/slowMovingClearance/index')
  ORDER BY CASE WHEN path = 'slow-moving-clearance' THEN 0 ELSE 1 END, menu_id
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
  1, 0, 'C', '0', '0', 'finance:slowMovingClearance:list', 'shopping',
  'SYSTEM', NOW(), 'Java REST代理Python FBA库存库龄DWS数据'
WHERE @finance_menu_id IS NOT NULL
  AND @clearance_menu_id IS NULL;

SET @clearance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND (path = 'slow-moving-clearance'
         OR component = 'finance/slowMovingClearance/index')
  ORDER BY CASE WHEN path = 'slow-moving-clearance' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = '滞销清货',
    parent_id = @finance_menu_id,
    order_num = 4,
    path = 'slow-moving-clearance',
    component = 'finance/slowMovingClearance/index',
    route_name = 'SlowMovingClearance',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'finance:slowMovingClearance:list',
    icon = 'shopping',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java REST代理Python FBA库存库龄DWS数据'
WHERE menu_id = @clearance_menu_id;

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '滞销清货查询', @clearance_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:slowMovingClearance:list', '#',
  'SYSTEM', NOW(), '查看EU、US1、US2、US3库龄汇总'
WHERE @clearance_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @clearance_menu_id
      AND perms = 'finance:slowMovingClearance:list'
  );

UPDATE sys_menu
SET menu_name = '滞销清货查询',
    order_num = 1,
    visible = '0',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE parent_id = @clearance_menu_id
  AND perms = 'finance:slowMovingClearance:list';

-- ----------------------------------------------------------------------------
-- 四、外汇退税菜单及全部按钮权限
-- ----------------------------------------------------------------------------
SET @tax_refund_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND (path = 'export-tax-refund'
         OR component = 'finance/exportTaxRefund/index')
  ORDER BY CASE WHEN path = 'export-tax-refund' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '外汇退税', @finance_menu_id, 1, 'export-tax-refund',
  'finance/exportTaxRefund/index', NULL, 'ExportTaxRefund',
  1, 0, 'C', '0', '0', 'finance:exportTaxRefund:list', 'chart',
  'SYSTEM', NOW(), 'Java REST代理Date-Project外汇退税流程'
WHERE @finance_menu_id IS NOT NULL
  AND @tax_refund_menu_id IS NULL;

SET @tax_refund_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id
    AND (path = 'export-tax-refund'
         OR component = 'finance/exportTaxRefund/index')
  ORDER BY CASE WHEN path = 'export-tax-refund' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = '外汇退税',
    parent_id = @finance_menu_id,
    order_num = 1,
    path = 'export-tax-refund',
    component = 'finance/exportTaxRefund/index',
    route_name = 'ExportTaxRefund',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'finance:exportTaxRefund:list',
    icon = 'chart',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = 'Java REST代理Date-Project外汇退税流程'
WHERE menu_id = @tax_refund_menu_id;

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT '外汇退税查询', @tax_refund_menu_id, 1, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:exportTaxRefund:query', '#',
       'SYSTEM', NOW(), '查询任务、报关单和库存'
WHERE @tax_refund_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @tax_refund_menu_id
      AND perms = 'finance:exportTaxRefund:query'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT '外汇退税导入', @tax_refund_menu_id, 2, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:exportTaxRefund:import', '#',
       'SYSTEM', NOW(), '导入报关、采购发票和外汇回款文件'
WHERE @tax_refund_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @tax_refund_menu_id
      AND perms = 'finance:exportTaxRefund:import'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT '外汇退税生成', @tax_refund_menu_id, 3, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:exportTaxRefund:generate', '#',
       'SYSTEM', NOW(), '生成申报批次和最终资料包'
WHERE @tax_refund_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @tax_refund_menu_id
      AND perms = 'finance:exportTaxRefund:generate'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT '外汇退税导出', @tax_refund_menu_id, 4, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'finance:exportTaxRefund:export', '#',
       'SYSTEM', NOW(), '下载最新外汇退税资料包'
WHERE @tax_refund_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @tax_refund_menu_id
      AND perms = 'finance:exportTaxRefund:export'
  );

UPDATE sys_menu
SET menu_name = CASE perms
      WHEN 'finance:exportTaxRefund:query' THEN '外汇退税查询'
      WHEN 'finance:exportTaxRefund:import' THEN '外汇退税导入'
      WHEN 'finance:exportTaxRefund:generate' THEN '外汇退税生成'
      WHEN 'finance:exportTaxRefund:export' THEN '外汇退税导出'
      ELSE menu_name END,
    order_num = CASE perms
      WHEN 'finance:exportTaxRefund:query' THEN 1
      WHEN 'finance:exportTaxRefund:import' THEN 2
      WHEN 'finance:exportTaxRefund:generate' THEN 3
      WHEN 'finance:exportTaxRefund:export' THEN 4
      ELSE order_num END,
    visible = '0',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE parent_id = @tax_refund_menu_id
  AND perms IN (
    'finance:exportTaxRefund:query',
    'finance:exportTaxRefund:import',
    'finance:exportTaxRefund:generate',
    'finance:exportTaxRefund:export'
  );

-- ----------------------------------------------------------------------------
-- 五、给 leiyongyu 当前拥有的全部角色授权三个页面的全部当前权限
-- 不新增用户、不修改角色、不影响其他用户和其他角色权限。
-- ----------------------------------------------------------------------------
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m ON (
     m.menu_id IN (
       @finance_menu_id,
       @performance_menu_id,
       @clearance_menu_id,
       @tax_refund_menu_id
     )
     OR (m.parent_id = @performance_menu_id
         AND m.perms IN (
           'finance:performanceRanking:list',
           'finance:performanceRanking:edit'
         ))
     OR (m.parent_id = @clearance_menu_id
         AND m.perms = 'finance:slowMovingClearance:list')
     OR (m.parent_id = @tax_refund_menu_id
         AND m.perms IN (
           'finance:exportTaxRefund:query',
           'finance:exportTaxRefund:import',
           'finance:exportTaxRefund:generate',
           'finance:exportTaxRefund:export'
         ))
)
WHERE u.user_name = 'leiyongyu';

-- ----------------------------------------------------------------------------
-- 六、绩效排名数据源任务：每月4日22:00同步上月数据
-- ----------------------------------------------------------------------------
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
    remark = '财务中心-绩效排名；Java Quartz调度，Python执行上月AMZ利润ODS/DWD/DWS及排名'
WHERE invoke_target IN (
        'operationSyncTask.syncAmzMonthlyOrderProfit',
        'operationSyncTask.syncAmzMonthlyOrderProfit()',
        'pythonPerformanceTask.syncPreviousMonth',
        'pythonPerformanceTask.syncPreviousMonth()'
      )
   OR (job_id = 240
       AND job_name IN (
         'Amazon月度完整订单利润同步',
         '领星-Amazon月度完整订单利润同步'
       ));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status,
  create_by, create_time, remark
)
SELECT
  'Amazon月度完整订单利润同步', 'FINANCE',
  'pythonPerformanceTask.syncPreviousMonth()', '0 0 22 4 * ?',
  '2', '1', '0', 'SYSTEM', NOW(),
  '财务中心-绩效排名；Java Quartz调度，Python执行上月AMZ利润ODS/DWD/DWS及排名'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target IN (
    'pythonPerformanceTask.syncPreviousMonth',
    'pythonPerformanceTask.syncPreviousMonth()'
  )
);

-- ----------------------------------------------------------------------------
-- 七、滞销清货数据源任务：每月1日22:30同步当月FBA库存库龄
-- ----------------------------------------------------------------------------
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
    remark = '财务中心-滞销清货；Java Quartz调度，Python执行FBA库存ODS/DWD/DWS库龄分组'
WHERE invoke_target IN (
        'operationSyncTask.syncAmzFbaInventorySnapshot',
        'operationSyncTask.syncAmzFbaInventorySnapshot()',
        'pythonFbaInventoryTask.syncCurrentMonth',
        'pythonFbaInventoryTask.syncCurrentMonth()'
      )
   OR (job_id = 241
       AND job_name IN (
         '领星-Amazon FBA库存库龄同步',
         '领星-Amazon FBA库存月度快照'
       ));

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status,
  create_by, create_time, remark
)
SELECT
  '领星-Amazon FBA库存库龄同步', 'FINANCE',
  'pythonFbaInventoryTask.syncCurrentMonth()', '0 30 22 1 * ?',
  '2', '1', '0', 'SYSTEM', NOW(),
  '财务中心-滞销清货；Java Quartz调度，Python执行FBA库存ODS/DWD/DWS库龄分组'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target IN (
    'pythonFbaInventoryTask.syncCurrentMonth',
    'pythonFbaInventoryTask.syncCurrentMonth()'
  )
);

COMMIT;

-- ----------------------------------------------------------------------------
-- 八、执行结果核验（只读）
-- ----------------------------------------------------------------------------
SELECT
  m.menu_id, m.menu_name, m.parent_id, m.order_num,
  m.path, m.component, m.menu_type, m.perms, m.visible, m.status
FROM sys_menu m
WHERE m.menu_id IN (
        @finance_menu_id,
        @performance_menu_id,
        @clearance_menu_id,
        @tax_refund_menu_id
      )
   OR m.parent_id IN (
        @performance_menu_id,
        @clearance_menu_id,
        @tax_refund_menu_id
      )
ORDER BY m.parent_id, m.order_num, m.menu_id;

SELECT
  u.user_name, r.role_id, r.role_name,
  m.menu_id, m.menu_name, m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = ur.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND (
    m.menu_id IN (
      @finance_menu_id,
      @performance_menu_id,
      @clearance_menu_id,
      @tax_refund_menu_id
    )
    OR m.perms IN (
      'finance:performanceRanking:list',
      'finance:performanceRanking:edit',
      'finance:slowMovingClearance:list',
      'finance:exportTaxRefund:query',
      'finance:exportTaxRefund:import',
      'finance:exportTaxRefund:generate',
      'finance:exportTaxRefund:export'
    )
  )
ORDER BY r.role_id, m.parent_id, m.order_num, m.menu_id;

SELECT
  job_id, job_name, job_group, invoke_target,
  cron_expression, misfire_policy, concurrent, status, remark
FROM sys_job
WHERE invoke_target IN (
  'pythonPerformanceTask.syncPreviousMonth()',
  'pythonFbaInventoryTask.syncCurrentMonth()'
)
ORDER BY job_id;
