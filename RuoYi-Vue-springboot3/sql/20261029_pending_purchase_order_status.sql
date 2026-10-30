-- 待采购：近半年eBay采购单状态。仅新增表、权限和每天任务，不修改既有表结构。
-- 重启Java后加载Quartz任务；首次在待采购页手动同步。可重复执行。
USE `jmh_data_platform`;
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS procurement_pending_po_item (
  order_sn VARCHAR(100) NOT NULL,
  item_id VARCHAR(64) NOT NULL,
  sku VARCHAR(255) NOT NULL,
  site VARCHAR(16) NOT NULL COMMENT 'DE/UK/US；UNKNOWN为eBay组仓站点待核对',
  wid VARCHAR(32) NULL,
  warehouse_name VARCHAR(255) NULL,
  supplier_name VARCHAR(255) NULL,
  order_status VARCHAR(255) NULL,
  arrival_status VARCHAR(255) NULL,
  pay_status VARCHAR(255) NULL,
  quantity_real DECIMAL(20,4) NULL,
  quantity_entry DECIMAL(20,4) NULL,
  quantity_receive DECIMAL(20,4) NULL,
  source_created DATETIME NOT NULL,
  source_updated DATETIME NULL,
  raw_json JSON NOT NULL,
  synced_at DATETIME NOT NULL,
  PRIMARY KEY(order_sn,item_id),
  KEY idx_sku_site_created(sku,site,source_created)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待采购匹配的领星采购单完整商品状态快照';
CREATE TABLE IF NOT EXISTS procurement_pending_po_sync (
  id TINYINT NOT NULL PRIMARY KEY,
  state VARCHAR(16) NOT NULL DEFAULT 'NEVER',
  last_success DATETIME NULL,
  range_start DATE NULL,
  range_end DATE NULL,
  row_count INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待采购状态同步发布信息，失败保留上次成功范围';
INSERT IGNORE INTO procurement_pending_po_sync(id,updated_at) VALUES(1,NOW());

START TRANSACTION;
SET @pending_page := (SELECT menu_id FROM sys_menu WHERE perms='procurement:pendingPurchase:list' AND menu_type='C' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '同步采购单状态',@pending_page,40,'',1,0,'F','0','0','procurement:pendingPurchase:syncStatus','#','SYSTEM',NOW(),
       '手动更新最近半年eBay仓库待采购SKU的领星采购/到货/付款状态'
WHERE @pending_page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='procurement:pendingPurchase:syncStatus');
INSERT INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.user_id JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_menu m ON m.perms='procurement:pendingPurchase:syncStatus'
WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0' AND r.status='0' AND r.del_flag='0'
AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=r.role_id AND rm.menu_id=m.menu_id);
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '待采购-领星采购单状态','OPERATION','pendingPurchaseStatusTask.sync()','0 0 9 * * ?','3','1','0','SYSTEM',NOW(),
       '每天09:00拉取近半年采购单；仅保存待采购清单SKU的eBay仓明细，失败保留上次成功数据'
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target IN ('pendingPurchaseStatusTask.sync()','pendingPurchaseStatusTask.sync'));
COMMIT;
