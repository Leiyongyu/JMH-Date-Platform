-- Current scheduler jobs seed.
-- Safe to run repeatedly: existing jobs with the same primary key are updated.
-- This script only writes sys_job rows, not business data.

INSERT INTO `sys_job`
(`job_id`, `job_name`, `job_group`, `invoke_target`, `cron_expression`, `misfire_policy`, `concurrent`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
VALUES
(200,'谷仓-仓库信息','OPERATION','operationSyncTask.syncGoodcangWarehouse','0 0 0 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天00:00'),
(201,'领星-仓库信息','OPERATION','operationSyncTask.syncLingxingWarehouse','0 20 0 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天00:20'),
(202,'领星-店铺列表','OPERATION','operationSyncTask.syncLingxingShop','0 40 0 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天00:40'),
(203,'领星-eBay商品刊登','OPERATION','operationSyncTask.syncEbayListing','0 0 1 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天01:00'),
(204,'谷仓-商品信息','OPERATION','operationSyncTask.syncGoodcangProduct','0 20 1 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天01:20'),
(205,'领星-Amazon商品刊登','OPERATION','operationSyncTask.syncAmzListing','0 40 1 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天01:40'),
(206,'领星-库存明细','OPERATION','operationSyncTask.syncLingxingInventory','0 0 2 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天02:00'),
(207,'谷仓-入库单','OPERATION','operationSyncTask.syncGoodcangGrnList','0 20 2 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天02:20'),
(208,'谷仓-入库单详情','OPERATION','operationSyncTask.syncGoodcangGrnDetail','0 40 2 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天02:40'),
(209,'领星-库存流水','OPERATION','operationSyncTask.syncLingxingStatement','0 0 3 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天03:00'),
(210,'领星-采购单','OPERATION','operationSyncTask.syncLingxingPurchaseOrder','0 20 3 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天03:20'),
(211,'领星-采购计划','OPERATION','operationSyncTask.syncLingxingPurchasePlan','0 40 3 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天03:40'),
(212,'刷新eBay补货快照','OPERATION','operationSyncTask.refreshEbayReplenishmentSnapshot','0 0 4 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天04:00'),
(213,'刷新eBay跟价表','OPERATION','operationSyncTask.refreshEbayPriceTrackingSnapshot','0 20 4 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天04:20'),
(214,'领星-Amazon订单利润','OPERATION','operationSyncTask.syncAmzOrderProfit','0 40 4 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天04:40'),
(215,'领星-Amazon补货建议','OPERATION','operationSyncTask.syncAmzRestockSummary','0 0 5 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天05:00'),
(216,'领星-Amazon库存明细','OPERATION','operationSyncTask.syncAmzWarehouseInventory','0 20 5 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天05:20'),
(217,'刷新Amazon补货快照','OPERATION','operationSyncTask.refreshAmzReplenishmentSnapshot','0 40 5 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天05:40'),
(218,'领星-FBA货件','OPERATION','operationSyncTask.syncAmzFbaShipment','0 0 6 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天06:00'),
(219,'领星-备货单号','OPERATION','operationSyncTask.syncOverseasStockOrder','0 15 06 * * ?','3','1','0','admin',NOW(),'leiyongyu',NOW(),'每10分钟拉取一次'),
(220,'领星-备货单详情','OPERATION','operationSyncTask.syncOverseasStockOrderDetail','0 20 06 * * ?','3','1','0','admin',NOW(),'leiyongyu',NOW(),'每2小时05分执行'),
(221,'报关产品库同步','OPERATION','operationSyncTask.syncCustomsProduct','0 30 6 * * ?','3','1','0','admin',NOW(),'',NOW(),'每天06:30执行'),
(222,'领星-FBA装箱信息','OPERATION','operationSyncTask.syncAmzFbaShipmentBox','0 00 06 * * ?','3','1','0','admin',NOW(),'leiyongyu',NOW(),'每天04:40执行')
ON DUPLICATE KEY UPDATE
  `invoke_target` = VALUES(`invoke_target`),
  `cron_expression` = VALUES(`cron_expression`),
  `misfire_policy` = VALUES(`misfire_policy`),
  `concurrent` = VALUES(`concurrent`),
  `status` = VALUES(`status`),
  `update_by` = VALUES(`update_by`),
  `update_time` = NOW(),
  `remark` = VALUES(`remark`);
