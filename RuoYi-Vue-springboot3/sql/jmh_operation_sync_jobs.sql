-- ============================================================
-- JMH 运营同步定时任务 —— 直接写入 sys_job 表，18 条任务
-- 执行前提：若依系统已初始化，OPERATION 分组字典已存在
-- ============================================================

-- 确保 OPERATION 分组字典存在
INSERT IGNORE INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, remark)
VALUES (3, '运营同步', 'OPERATION', 'sys_job_group', '', '', 'N', '0', 'admin', NOW(), '运营数据同步任务分组');

-- 确保 quartz 相关 job_id 序列从足够大的值开始
-- (默认从 100 开始，这里手动指定 ID 避免冲突)

-- ==================== 低频基础同步（每周一凌晨） ====================

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (200, '谷仓-仓库信息', 'OPERATION', 'operationSyncTask.syncGoodcangWarehouse', '0 0 0 ? * 1', '3', '1', '0', 'admin', NOW(), '每周一00:00');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (201, '领星-仓库信息', 'OPERATION', 'operationSyncTask.syncLingxingWarehouse', '0 10 0 ? * 1', '3', '1', '0', 'admin', NOW(), '每周一00:10');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (202, '领星-店铺列表', 'OPERATION', 'operationSyncTask.syncLingxingShop', '0 15 0 ? * 1', '3', '1', '0', 'admin', NOW(), '每周一00:15');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (203, '领星-eBay商品刊登', 'OPERATION', 'operationSyncTask.syncEbayListing', '0 20 0 ? * 1', '3', '1', '0', 'admin', NOW(), '每周一00:20');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (204, '谷仓-商品信息', 'OPERATION', 'operationSyncTask.syncGoodcangProduct', '0 30 0 ? * 1', '3', '1', '0', 'admin', NOW(), '每周一00:30');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (205, '领星-Amazon商品刊登', 'OPERATION', 'operationSyncTask.syncAmzListing', '0 40 0 ? * 1', '3', '1', '0', 'admin', NOW(), '每周一00:40');

-- ==================== 每日高频同步 ====================

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (206, '领星-库存明细', 'OPERATION', 'operationSyncTask.syncLingxingInventory', '0 50 0 * * ?', '3', '1', '0', 'admin', NOW(), '每天00:50');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (207, '谷仓-入库单', 'OPERATION', 'operationSyncTask.syncGoodcangGrnList', '0 7 1 * * ?', '3', '1', '0', 'admin', NOW(), '每天01:07');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (208, '谷仓-入库单详情', 'OPERATION', 'operationSyncTask.syncGoodcangGrnDetail', '0 24 1 * * ?', '3', '1', '0', 'admin', NOW(), '每天01:24');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (209, '领星-库存流水', 'OPERATION', 'operationSyncTask.syncLingxingStatement', '0 41 1 * * ?', '3', '1', '0', 'admin', NOW(), '每天01:41');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (210, '领星-采购单', 'OPERATION', 'operationSyncTask.syncLingxingPurchaseOrder', '0 58 1 * * ?', '3', '1', '0', 'admin', NOW(), '每天01:58');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (211, '领星-采购计划', 'OPERATION', 'operationSyncTask.syncLingxingPurchasePlan', '0 15 2 * * ?', '3', '1', '0', 'admin', NOW(), '每天02:15');

-- ==================== 快照刷新 ====================

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (212, '刷新eBay补货快照', 'OPERATION', 'operationSyncTask.refreshEbayReplenishmentSnapshot', '0 32 2 * * ?', '3', '1', '0', 'admin', NOW(), '每天02:32');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (213, '刷新eBay跟价表', 'OPERATION', 'operationSyncTask.refreshEbayPriceTrackingSnapshot', '0 49 2 * * ?', '3', '1', '0', 'admin', NOW(), '每天02:49');

-- ==================== Amazon 同步 ====================

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (214, '领星-Amazon订单利润', 'OPERATION', 'operationSyncTask.syncAmzOrderProfit', '0 6 3 * * ?', '3', '1', '0', 'admin', NOW(), '每天03:06');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (215, '领星-Amazon补货建议', 'OPERATION', 'operationSyncTask.syncAmzRestockSummary', '0 23 3 * * ?', '3', '1', '0', 'admin', NOW(), '每天03:23');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (216, '领星-Amazon库存明细', 'OPERATION', 'operationSyncTask.syncAmzWarehouseInventory', '0 40 3 * * ?', '3', '1', '0', 'admin', NOW(), '每天03:40');

INSERT IGNORE INTO sys_job (job_id, job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, create_by, create_time, remark)
VALUES (217, '刷新Amazon补货快照', 'OPERATION', 'operationSyncTask.refreshAmzReplenishmentSnapshot', '0 57 3 * * ?', '3', '1', '0', 'admin', NOW(), '每天03:57');
