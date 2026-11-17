-- ============================================================
-- 【本脚本含 DELETE 与 DROP TABLE，需用户审批后执行】
-- ============================================================
-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：下线「运营中心 > eBay」下的每日跟价、品牌负责人、eBay链接模版三个页面，
--       以及只为每日跟价服务的 eBay补货1.0 计算（旧补货快照与旧补货公式）。
-- 先保住共用权限：跟价页面下还挂着别的功能在用的按钮权限，例如「eBay同步拉取」
--       (operations:ebayReplenishment:sync，导航栏「数据校准」与 eBay 手动同步)、「领星Token测试」
--       (operations:lingxing:test) 和「领星接口调用」(operations:lingxing:call，领星开放接口调试)。
--       凡是挂在三个待删页面下、又不在下面「待删按钮清单」里的按钮，一律先移到 eBay 目录下，
--       角色授权保持不变，再删页面，避免连带删掉。
-- 删除内容：
--   1. sys_menu / sys_role_menu：三个页面、品牌负责人增改删按钮、跟价兼容权限
--      (operations:ebayReplenishment:list/import/export)、已停用的旧补货公式按钮
--      (operations:ebayReplenishment:formula:edit)。按 component / perms 精确定位，不写死 menu_id；
--      补货2.0 的权限前缀是 operations:ebayReplenishmentV2，不受影响。
--   2. sys_job：跟价历史补货量刷新、刷新eBay跟价表两个任务（按 invoke_target 定位）。
--   3. DROP TABLE：ebay_price_tracking_snapshot、brand_owner、ebay_link_template、
--      ebay_replenishment_snapshot、ebay_replenish_formula、operation_import_task（跟价页导入日志）。
-- 保留不动：ebay_sales（月度库存报表的 eBay 销量回退来源）、ebay_product_dedup、
--       goodcang_product_info、dwd_performance_owner_rule（绩效/补货2.0 用的负责人规则）、
--       补货2.0 全部表与菜单、eBay链路同步任务（只是代码里去掉了两个刷新步骤）。
-- 幂等：可重复执行；已删除的内容再执行时删除 0 行、DROP 不报错。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

-- ------------------------------------------------------------
-- 1. 菜单与授权
-- ------------------------------------------------------------
SET @ebay_dir_id := (
  SELECT parent_id FROM sys_menu
  WHERE menu_type='C' AND component IN ('operations/ebay/priceTracking/index',
                                         'operations/brandOwner/index',
                                         'operations/linkTemplate/index')
  ORDER BY CASE component WHEN 'operations/ebay/priceTracking/index' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

DROP TEMPORARY TABLE IF EXISTS tmp_retired_ebay_pages;
CREATE TEMPORARY TABLE tmp_retired_ebay_pages (menu_id BIGINT PRIMARY KEY);
INSERT IGNORE INTO tmp_retired_ebay_pages (menu_id)
SELECT menu_id FROM sys_menu
WHERE menu_type='C' AND component IN ('operations/ebay/priceTracking/index',
                                       'operations/brandOwner/index',
                                       'operations/linkTemplate/index');

START TRANSACTION;

-- 1.1 挂在待删页面下、但不在待删按钮清单里的按钮（别的功能还在用的权限）移到 eBay 目录下，授权不变。
UPDATE sys_menu m
JOIN tmp_retired_ebay_pages p ON m.parent_id=p.menu_id
SET m.parent_id=@ebay_dir_id, m.update_by='SYSTEM', m.update_time=NOW(),
    m.remark=CONCAT('原挂在已下线的 eBay 每日跟价/品牌负责人/链接模版页面下，下线时移到 eBay 目录；',
                    COALESCE(m.remark,''))
WHERE m.menu_type='F' AND @ebay_dir_id IS NOT NULL
  AND COALESCE(m.perms,'') NOT IN (
  'operations:ebayReplenishment:list',
  'operations:ebayReplenishment:import',
  'operations:ebayReplenishment:export',
  'operations:ebayReplenishment:formula:edit',
  'operations:brandOwner:list',
  'operations:brandOwner:add',
  'operations:brandOwner:edit',
  'operations:brandOwner:remove',
  'operations:ebayPriceTracking:list'
  );

-- 1.2 待删清单：三个页面本身，以及按 perms 精确定位的待删按钮（不按「页面下的全部按钮」删）。
DROP TEMPORARY TABLE IF EXISTS tmp_retired_ebay_menus;
CREATE TEMPORARY TABLE tmp_retired_ebay_menus (menu_id BIGINT PRIMARY KEY);
INSERT IGNORE INTO tmp_retired_ebay_menus (menu_id) SELECT menu_id FROM tmp_retired_ebay_pages;
INSERT IGNORE INTO tmp_retired_ebay_menus (menu_id)
SELECT menu_id FROM sys_menu
WHERE menu_type='F' AND perms IN (
  'operations:ebayReplenishment:list',
  'operations:ebayReplenishment:import',
  'operations:ebayReplenishment:export',
  'operations:ebayReplenishment:formula:edit',
  'operations:brandOwner:list',
  'operations:brandOwner:add',
  'operations:brandOwner:edit',
  'operations:brandOwner:remove',
  'operations:ebayPriceTracking:list'
);

DELETE rm FROM sys_role_menu rm JOIN tmp_retired_ebay_menus t ON t.menu_id=rm.menu_id;
DELETE m FROM sys_menu m JOIN tmp_retired_ebay_menus t ON t.menu_id=m.menu_id;

-- ------------------------------------------------------------
-- 2. 定时任务（Java 里对应的方法已删除，任务留着会每次执行都报错）
-- ------------------------------------------------------------
DELETE FROM sys_job
WHERE invoke_target IN (
  'operationSyncTask.refreshEbayReplenishmentSnapshot',
  'operationSyncTask.refreshEbayReplenishmentSnapshot()',
  'operationSyncTask.refreshEbayPriceTrackingSnapshot',
  'operationSyncTask.refreshEbayPriceTrackingSnapshot()'
);

COMMIT;

-- ------------------------------------------------------------
-- 3. 数据表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS ebay_price_tracking_snapshot;
DROP TABLE IF EXISTS brand_owner;
DROP TABLE IF EXISTS ebay_link_template;
DROP TABLE IF EXISTS ebay_replenishment_snapshot;
DROP TABLE IF EXISTS ebay_replenish_formula;
DROP TABLE IF EXISTS operation_import_task;

-- ------------------------------------------------------------
-- 4. 校验
-- ------------------------------------------------------------
-- 应为 0：三个页面与被删按钮都不在了。
SELECT COUNT(*) AS retired_menus_left FROM sys_menu
WHERE component IN ('operations/ebay/priceTracking/index','operations/brandOwner/index','operations/linkTemplate/index')
   OR perms IN ('operations:ebayReplenishment:list','operations:ebayReplenishment:import',
                'operations:ebayReplenishment:export','operations:ebayReplenishment:formula:edit',
                'operations:brandOwner:list','operations:brandOwner:add','operations:brandOwner:edit',
                'operations:brandOwner:remove','operations:ebayPriceTracking:list');
-- 应为 3 行，且 parent_id 都是 eBay 目录：共用权限保住了，授权角色数与执行前一致。
SELECT m.menu_id, m.parent_id, m.menu_name, m.perms,
       (SELECT COUNT(*) FROM sys_role_menu rm WHERE rm.menu_id=m.menu_id) AS role_grants
FROM sys_menu m WHERE m.perms IN ('operations:ebayReplenishment:sync',
                                  'operations:lingxing:test','operations:lingxing:call');
-- 应为 0：两个旧任务已删。
SELECT COUNT(*) AS retired_jobs_left FROM sys_job
WHERE invoke_target LIKE 'operationSyncTask.refreshEbayReplenishmentSnapshot%'
   OR invoke_target LIKE 'operationSyncTask.refreshEbayPriceTrackingSnapshot%';
-- 应为 0：六张表已删；ebay_sales 等保留表不在此列。
SELECT COUNT(*) AS retired_tables_left FROM information_schema.tables
WHERE table_schema='jmh_data_platform' AND table_name IN (
  'ebay_price_tracking_snapshot','brand_owner','ebay_link_template',
  'ebay_replenishment_snapshot','ebay_replenish_formula','operation_import_task');

DROP TEMPORARY TABLE IF EXISTS tmp_retired_ebay_menus;
DROP TEMPORARY TABLE IF EXISTS tmp_retired_ebay_pages;
-- 执行后：重启 Java；角色权限有变化的账号退出重新登录。
