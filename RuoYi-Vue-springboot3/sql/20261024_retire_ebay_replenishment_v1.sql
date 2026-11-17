-- 下线eBay补货1.0独立页面；保留跟价/同步复用的权限ID、角色授权、计算和数据。
-- 仅在Java ERP库执行。无需修改Python补货2.0的表、菜单或权限。
USE `jmh_data_platform`;

DROP TEMPORARY TABLE IF EXISTS tmp_retired_ebay_replenishment_v1;
CREATE TEMPORARY TABLE tmp_retired_ebay_replenishment_v1 (
    menu_id BIGINT PRIMARY KEY,
    original_parent_id BIGINT,
    is_formula TINYINT NOT NULL
);

START TRANSACTION;
INSERT INTO tmp_retired_ebay_replenishment_v1(menu_id,original_parent_id,is_formula)
SELECT menu_id,parent_id,
       CASE WHEN component='operations/ebay/formula/index'
                  OR perms='operations:ebayReplenishment:formula:edit' THEN 1 ELSE 0 END
FROM sys_menu
WHERE component IN ('operations/ebay/replenishment/index','operations/ebay/formula/index')
   OR (menu_type='C' AND perms='operations:ebayReplenishment:list'
       AND (route_name='EbayReplenishment' OR path='replenishment'))
   OR (menu_type='C' AND perms='operations:ebayReplenishment:formula:edit');

SET @ebay_tracking_page := (
    SELECT menu_id FROM sys_menu
    WHERE component='operations/ebay/priceTracking/index' AND menu_type='C'
    ORDER BY menu_id LIMIT 1
);

-- 子权限移到跟价页面；未部署跟价菜单时留在原目录。原role_id/menu_id授权保持不变。
UPDATE sys_menu m
JOIN tmp_retired_ebay_replenishment_v1 retired ON m.parent_id=retired.menu_id
SET m.parent_id=COALESCE(@ebay_tracking_page,retired.original_parent_id),
    m.update_by='SYSTEM',m.update_time=NOW()
WHERE retired.is_formula=0 AND m.menu_type='F';

-- 旧页面ID改为权限节点：不再生成路由，同时继续提供跟价读取所需的旧权限。
UPDATE sys_menu m
JOIN tmp_retired_ebay_replenishment_v1 retired ON m.menu_id=retired.menu_id
SET m.parent_id=COALESCE(@ebay_tracking_page,retired.original_parent_id),
    m.menu_name='跟价查看（兼容权限）',m.menu_type='F',
    m.path='#',m.component=NULL,m.route_name='',m.query=NULL,
    m.visible='1',m.status='0',
    m.remark='补货1.0页面已下线；保留原权限ID和角色授权供跟价使用',
    m.update_by='SYSTEM',m.update_time=NOW()
WHERE retired.is_formula=0;

-- 独立旧公式编辑页面已移除。规则表仍被跟价补货量计算使用，不删除规则数据。
UPDATE sys_menu m
JOIN tmp_retired_ebay_replenishment_v1 retired ON m.menu_id=retired.menu_id
SET m.menu_name='旧补货公式（已下线）',m.menu_type='F',
    m.path='#',m.component=NULL,m.route_name='',m.query=NULL,
    m.visible='1',m.status='1',m.update_by='SYSTEM',m.update_time=NOW()
WHERE retired.is_formula=1;

UPDATE sys_menu
SET visible='1',status='1',update_by='SYSTEM',update_time=NOW()
WHERE perms='operations:ebayReplenishment:formula:edit';

-- 仅调整旧计算任务的显示名称；保留执行方式、启停状态和时间，以维护跟价依赖。
UPDATE sys_job
SET job_name='跟价历史补货量刷新',update_by='SYSTEM',update_time=NOW()
WHERE invoke_target IN ('operationSyncTask.refreshEbayReplenishmentSnapshot',
                        'operationSyncTask.refreshEbayReplenishmentSnapshot()');
COMMIT;

SELECT menu_id,menu_name,parent_id,menu_type,status,perms
FROM sys_menu WHERE menu_id IN (SELECT menu_id FROM tmp_retired_ebay_replenishment_v1);
DROP TEMPORARY TABLE tmp_retired_ebay_replenishment_v1;
