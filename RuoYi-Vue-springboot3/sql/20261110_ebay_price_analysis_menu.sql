-- 目标库：jmh_data_platform（Java ERP 数据库）。
-- 功能：新增「运营中心 / eBay / 店铺分析 / 价格分析」页面及其功能权限、19 个导出列权限，
--       并登记 eBay 在售刊登的日级 Quartz 同步任务。
-- 幂等：全脚本可重复执行。菜单按 perms/component/route_name 定位后 UPDATE 到目标形态；
--       导出列权限只为本次新建的那些补初始授权，不会重新勾选管理员已取消的字段；
--       Quartz 任务按 invoke_target 判重，不重复插入。
-- 依赖：需部署包含 EbayPriceAnalysisController、EbayPriceAnalysisPythonClient、
--       PythonEbayStoreListingSyncTask 的新版 Java，以及 Python 侧的
--       /api/v1/finance/ebay-price-analysis/{overview,detail,export} 三个接口。
--       （原「刷新快照」按钮权限已取消；已执行过旧版本的环境另跑
--        20261110_ebay_price_analysis_drop_refresh.sql 清理。）
-- 安全性：只写 sys_menu / sys_role_menu / sys_job，不碰任何业务表，不删除任何菜单。
--       唯一会改动既有行的地方是把原「eBay店铺商品信息每月同步」任务置为暂停 ——
--       eBay 侧已改为日级，两个任务同时启用会重复拉取、白耗 API 额度。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

-- ============================================================
-- 1. 菜单：运营中心 -> eBay -> 店铺分析 -> 价格分析
-- ============================================================
SET @operations_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M'
    AND (path='operations' OR menu_name='运营中心')
  ORDER BY CASE WHEN path='operations' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

-- 价格分析页面本体。order_num=4 与同目录下 eBay补货2.0 并列。
SET @price_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayPriceAnalysis:list'
    OR component='operations/ebay/priceAnalysis/index'
    OR route_name='EbayPriceAnalysis'
    OR (parent_id=@store_analysis_id AND path='price-analysis')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayPriceAnalysis:list' THEN 0
    WHEN component='operations/ebay/priceAnalysis/index' THEN 1
    WHEN route_name='EbayPriceAnalysis' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '价格分析',@store_analysis_id,4,'price-analysis',
       'operations/ebay/priceAnalysis/index',NULL,'EbayPriceAnalysis',
       1,0,'C','0','0','operations:ebayPriceAnalysis:list','chart',
       'SYSTEM',NOW(),'eBay在售刊登售价与库存对比谷仓海外仓库存的BI看板'
WHERE @store_analysis_id IS NOT NULL AND @price_analysis_id IS NULL;
SET @price_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayPriceAnalysis:list'
    OR component='operations/ebay/priceAnalysis/index'
    OR route_name='EbayPriceAnalysis'
    OR (parent_id=@store_analysis_id AND path='price-analysis')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayPriceAnalysis:list' THEN 0
    WHEN component='operations/ebay/priceAnalysis/index' THEN 1
    WHEN route_name='EbayPriceAnalysis' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@store_analysis_id,menu_name='价格分析',order_num=4,
    path='price-analysis',component='operations/ebay/priceAnalysis/index',
    query=NULL,route_name='EbayPriceAnalysis',is_frame=1,is_cache=0,
    menu_type='C',visible='0',status='0',
    perms='operations:ebayPriceAnalysis:list',icon='chart',
    update_by='SYSTEM',update_time=NOW(),
    remark='eBay在售刊登售价与库存对比谷仓海外仓库存的BI看板'
WHERE menu_id=@price_analysis_id AND @store_analysis_id IS NOT NULL;

-- 导出总开关；19 个导出列权限挂在它下面（与补货2.0 的层级一致）。
SET @export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayPriceAnalysis:export'
    OR (parent_id=@price_analysis_id AND menu_name='导出')
  )
  ORDER BY CASE WHEN perms='operations:ebayPriceAnalysis:export' THEN 0 ELSE 1 END,
           menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导出',@price_analysis_id,2,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayPriceAnalysis:export','',
       'SYSTEM',NOW(),'价格分析导出总开关；具体导出列由下面的「导出字段-xxx」逐列控制'
WHERE @price_analysis_id IS NOT NULL AND @export_id IS NULL;
SET @export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayPriceAnalysis:export'
    OR (parent_id=@price_analysis_id AND menu_name='导出')
  )
  ORDER BY CASE WHEN perms='operations:ebayPriceAnalysis:export' THEN 0 ELSE 1 END,
           menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@price_analysis_id,menu_name='导出',order_num=2,
    path='',component=NULL,query=NULL,route_name='',is_frame=1,is_cache=0,
    menu_type='F',visible='0',status='0',
    perms='operations:ebayPriceAnalysis:export',icon='',
    update_by='SYSTEM',update_time=NOW(),
    remark='价格分析导出总开关；具体导出列由下面的「导出字段-xxx」逐列控制'
WHERE menu_id=@export_id AND @price_analysis_id IS NOT NULL;

-- ============================================================
-- 2. 导出列权限（19 项，只控制 Excel 导出列，不控制页面展示）
--    字段 key 与接口 detail 响应的字段名一致，顺序即导出顺序。
-- ============================================================
DROP TEMPORARY TABLE IF EXISTS tmp_ebay_price_analysis_export_columns;
CREATE TEMPORARY TABLE tmp_ebay_price_analysis_export_columns (
    field_key VARCHAR(64) PRIMARY KEY,
    field_title VARCHAR(40) NOT NULL,
    sort_order INT NOT NULL,
    is_new TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO tmp_ebay_price_analysis_export_columns (field_key,field_title,sort_order) VALUES
('seller_account','店铺',101),
('site_name','站点',102),
('sku','SKU',103),
('title','标题',104),
('currency','币种',105),
('current_price','原币售价',106),
('price_usd','售价USD',107),
('ebay_quantity_available','eBay可售',108),
('overseas_sellable','谷仓可售',109),
('overseas_in_transit','海外在途',110),
('chengdu_sellable','成都可售',111),
('pending_outbound','待出库',112),
('sales_qty_7d','近7日销量',113),
('sales_qty_30d','近30日销量',114),
('cover_days','覆盖天数',115),
('stock_gap','库存缺口',116),
('purchase_cost_cny','采购成本',117),
('status','状态',118),
('view_item_url','刊登链接',119);

START TRANSACTION;
UPDATE tmp_ebay_price_analysis_export_columns c
SET is_new = NOT EXISTS (
    SELECT 1 FROM sys_menu m
    WHERE m.perms=CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key)
          COLLATE utf8mb4_unicode_ci
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark
)
SELECT CONCAT('导出字段-',c.field_title),@export_id,c.sort_order,'',NULL,NULL,'',
       1,0,'F','0','0',CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key),
       '#','SYSTEM',NOW(),'只控制价格分析Excel导出列，不控制页面展示'
FROM tmp_ebay_price_analysis_export_columns c
WHERE c.is_new=1 AND @export_id IS NOT NULL;
COMMIT;

-- ============================================================
-- 3. 授权：非管理员的动态路由从根递归构建，四级菜单必须整条祖先链都授权。
--    沿用 20260831_ebay_replenishment_v2_menu.sql 的做法，给 leiyongyu 的有效角色补齐。
-- ============================================================
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,target.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN (
  SELECT @operations_id AS menu_id
  UNION ALL SELECT @ebay_dir_id
  UNION ALL SELECT @store_analysis_id
  UNION ALL SELECT @price_analysis_id
  UNION ALL SELECT @export_id
) target ON target.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';

-- 导出列：首次创建时，为已有页面查看权限的有效角色授予全部列；
-- 重复执行只处理本次新建的列，不会重新勾选管理员已取消的字段。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_role_menu page_grant
     ON page_grant.role_id=r.role_id AND page_grant.menu_id=@price_analysis_id
JOIN tmp_ebay_price_analysis_export_columns c ON c.is_new=1
JOIN sys_menu m ON m.parent_id=@export_id AND m.menu_type='F' AND m.status='0'
    AND m.perms=CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key)
        COLLATE utf8mb4_unicode_ci
WHERE r.status='0' AND r.del_flag='0' AND @price_analysis_id IS NOT NULL;

-- ============================================================
-- 4. Quartz：eBay 在售刊登日级同步
--    实测 37 个账号 / 18013 条 listing，一轮约 240 次 eBay Trading API 调用，
--    占默认 5000 calls/day 额度约 5%。04:30 执行，早于其他 05:00 的月度任务。
--    任务先调 Python 既有的 ebay_store_listing_sync（sync_ebay_store_listings），
--    成功后再登记价格分析刷表；刷表登记失败不会推翻已拉好的 listing，会单独发邮件告警。
-- ============================================================
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,
 concurrent,status,create_by,create_time,remark)
SELECT 'eBay在售刊登与价格分析每日同步','DEFAULT','pythonEbayStoreListingSyncTask.runDaily()',
 '0 30 4 * * ?','2','1','0','SYSTEM',NOW(),
 '每天北京时间04:30；复用Python既有全量同步逻辑覆盖 ods_ebay_store_listing_latest，随后登记价格分析DWS刷表；约240次eBay Trading API调用，占日额度5%。服务器时区须为Asia/Shanghai。'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job WHERE invoke_target='pythonEbayStoreListingSyncTask.runDaily()'
);

-- 排查用：只拉 listing 不刷表。默认暂停，需要时手动「执行一次」。
INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,
 concurrent,status,create_by,create_time,remark)
SELECT 'eBay在售刊登单独拉取（排查用）','DEFAULT','pythonEbayStoreListingSyncTask.syncListingOnly()',
 '0 30 4 * * ?','3','1','1','SYSTEM',NOW(),
 '默认暂停，只在排查上游问题时手动「执行一次」；只拉listing，不登记价格分析刷表。'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target='pythonEbayStoreListingSyncTask.syncListingOnly()'
);

-- eBay 侧已改日级，原每月任务置为暂停，避免重复拉取、白耗 API 额度。
-- 只动状态，不删除任务，必要时在定时任务页面重新启用即可。
UPDATE sys_job
SET status='1',update_by='SYSTEM',update_time=NOW(),
    remark=CONCAT(COALESCE(remark,''),
      ' 【2026-11-10 已暂停】eBay侧改为日级同步，由「eBay在售刊登与价格分析每日同步」接管。')
WHERE invoke_target='pythonEbayStoreListingTask.runMonthly()' AND status<>'1';

-- ============================================================
-- 5. 校验
-- ============================================================
-- 应返回 3 行：店铺分析目录、价格分析页面、导出。
SELECT menu_id,parent_id,menu_name,order_num,path,component,route_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@store_analysis_id,@price_analysis_id,@export_id)
ORDER BY parent_id,order_num,menu_id;

-- 应返回 19；返回 0 或小于 19 时检查价格分析页面与导出总开关是否已创建。
SELECT COUNT(*) AS export_field_permission_count
FROM sys_menu m
JOIN tmp_ebay_price_analysis_export_columns c
  ON m.perms=CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key)
     COLLATE utf8mb4_unicode_ci
WHERE m.parent_id=@export_id AND m.status='0' AND m.menu_type='F';

-- 应返回 3 行：每日同步（status=0 启用）、单独拉取（status=1 暂停）、原每月任务（status=1 暂停）。
SELECT job_id,job_name,invoke_target,cron_expression,status
FROM sys_job
WHERE invoke_target IN (
  'pythonEbayStoreListingSyncTask.runDaily()',
  'pythonEbayStoreListingSyncTask.syncListingOnly()',
  'pythonEbayStoreListingTask.runMonthly()'
)
ORDER BY job_id;

DROP TEMPORARY TABLE tmp_ebay_price_analysis_export_columns;
-- 角色配置后，账号需退出重新登录以刷新权限；无任何导出列权限时导出会提示联系管理员。
