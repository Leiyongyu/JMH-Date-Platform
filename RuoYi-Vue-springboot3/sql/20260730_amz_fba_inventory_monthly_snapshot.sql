-- 领星“查询FBA库存列表-v2”全量月度快照。
-- 每月1日22:30拉取当前年月；同年月整月覆盖，不同年月新增保留。

CREATE TABLE IF NOT EXISTS `amz_fba_inventory_monthly_snapshot` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `pull_month` char(7) NOT NULL COMMENT '拉取日期，格式YYYY-MM；同月重拉整月覆盖',
  `name` varchar(255) DEFAULT NULL COMMENT '仓库名',
  `storage_type_name` varchar(255) DEFAULT NULL COMMENT '仓储类型',
  `seller_group_name` varchar(255) DEFAULT NULL COMMENT '共享仓店铺名',
  `sid` bigint DEFAULT NULL COMMENT '店铺ID；共享仓可能为0',
  `asin` varchar(64) DEFAULT NULL COMMENT 'ASIN',
  `asin_principal_list_json` longtext COMMENT '负责人列表JSON',
  `product_name` varchar(1000) DEFAULT NULL COMMENT '品名',
  `small_image_url` varchar(2000) DEFAULT NULL COMMENT '预览图链接',
  `seller_sku` varchar(255) DEFAULT NULL COMMENT 'MSKU',
  `fnsku` varchar(255) DEFAULT NULL COMMENT 'FNSKU',
  `sku` varchar(255) DEFAULT NULL COMMENT 'SKU',
  `category_text` varchar(1000) DEFAULT NULL COMMENT '分类文本',
  `cid` bigint DEFAULT NULL COMMENT '分类ID',
  `product_brand_text` varchar(500) DEFAULT NULL COMMENT '品牌文本',
  `bid` bigint DEFAULT NULL COMMENT '品牌ID',
  `share_type` int DEFAULT NULL COMMENT '共享类型：0非共享、1北美共享、2欧洲共享',
  `total` decimal(24,6) DEFAULT NULL COMMENT '总数',
  `total_price` decimal(24,6) DEFAULT NULL COMMENT '总价',
  `available_total` decimal(24,6) DEFAULT NULL COMMENT '可用总数',
  `available_total_price` varchar(100) DEFAULT NULL COMMENT '可用总数成本价原值',
  `afn_fulfillable_quantity` decimal(24,6) DEFAULT NULL COMMENT 'FBA可售',
  `afn_fulfillable_quantity_price` varchar(100) DEFAULT NULL COMMENT 'FBA可售成本价原值',
  `afn_reserved_quantity` decimal(24,6) DEFAULT NULL COMMENT 'FBA预留',
  `afn_reserved_quantity_price` varchar(100) DEFAULT NULL COMMENT 'FBA预留成本原值',
  `reserved_fc_transfers` decimal(24,6) DEFAULT NULL COMMENT '待调仓',
  `reserved_fc_transfers_price` varchar(100) DEFAULT NULL COMMENT '待调仓成本价原值',
  `reserved_fc_processing` decimal(24,6) DEFAULT NULL COMMENT '调仓中',
  `reserved_fc_processing_price` varchar(100) DEFAULT NULL COMMENT '调仓中成本价原值',
  `reserved_customerorders` decimal(24,6) DEFAULT NULL COMMENT '待发货',
  `reserved_customerorders_price` varchar(100) DEFAULT NULL COMMENT '待发货成本价原值',
  `quantity` decimal(24,6) DEFAULT NULL COMMENT 'FBM可售',
  `quantity_price` varchar(100) DEFAULT NULL COMMENT 'FBM可售成本价原值',
  `afn_unsellable_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售',
  `afn_unsellable_quantity_price` varchar(100) DEFAULT NULL COMMENT '不可售成本价原值',
  `afn_inbound_working_quantity` decimal(24,6) DEFAULT NULL COMMENT '计划入库',
  `afn_inbound_working_quantity_price` varchar(100) DEFAULT NULL COMMENT '计划入库成本价原值',
  `afn_inbound_shipped_quantity` decimal(24,6) DEFAULT NULL COMMENT '在途',
  `afn_inbound_shipped_quantity_price` varchar(100) DEFAULT NULL COMMENT '在途成本价原值',
  `afn_inbound_receiving_quantity` decimal(24,6) DEFAULT NULL COMMENT '入库中',
  `afn_inbound_receiving_quantity_price` varchar(100) DEFAULT NULL COMMENT '入库中成本价原值',
  `stock_up_num` decimal(24,6) DEFAULT NULL COMMENT '实际在途',
  `stock_up_num_price` varchar(100) DEFAULT NULL COMMENT '实际在途成本价原值',
  `afn_researching_quantity` decimal(24,6) DEFAULT NULL COMMENT '调查中数量',
  `afn_researching_quantity_price` varchar(100) DEFAULT NULL COMMENT '调查中数量成本价原值',
  `total_fulfillable_quantity` decimal(24,6) DEFAULT NULL COMMENT '总可用库存',
  `inv_age_0_to_30_days` decimal(24,6) DEFAULT NULL COMMENT '0-1个月库龄',
  `inv_age_0_to_30_price` varchar(100) DEFAULT NULL COMMENT '0-1个月库龄成本价原值',
  `inv_age_31_to_60_days` decimal(24,6) DEFAULT NULL COMMENT '1-2个月库龄',
  `inv_age_31_to_60_price` varchar(100) DEFAULT NULL COMMENT '1-2个月库龄成本价原值',
  `inv_age_61_to_90_days` decimal(24,6) DEFAULT NULL COMMENT '2-3个月库龄',
  `inv_age_61_to_90_price` varchar(100) DEFAULT NULL COMMENT '2-3个月库龄成本价原值',
  `inv_age_0_to_90_days` decimal(24,6) DEFAULT NULL COMMENT '0-3个月库龄',
  `inv_age_0_to_90_price` varchar(100) DEFAULT NULL COMMENT '0-3个月库龄成本价原值',
  `inv_age_91_to_180_days` decimal(24,6) DEFAULT NULL COMMENT '3-6个月库龄',
  `inv_age_91_to_180_price` varchar(100) DEFAULT NULL COMMENT '3-6个月库龄成本价原值',
  `inv_age_181_to_270_days` decimal(24,6) DEFAULT NULL COMMENT '6-9个月库龄',
  `inv_age_181_to_270_price` varchar(100) DEFAULT NULL COMMENT '6-9个月库龄成本价原值',
  `inv_age_271_to_330_days` decimal(24,6) DEFAULT NULL COMMENT '9-11个月库龄',
  `inv_age_271_to_330_price` varchar(100) DEFAULT NULL COMMENT '9-11个月库龄成本价原值',
  `inv_age_271_to_365_days` decimal(24,6) DEFAULT NULL COMMENT '9-12个月库龄',
  `inv_age_271_to_365_price` varchar(100) DEFAULT NULL COMMENT '9-12个月库龄成本价原值',
  `inv_age_331_to_365_days` decimal(24,6) DEFAULT NULL COMMENT '11-12个月库龄',
  `inv_age_331_to_365_price` varchar(100) DEFAULT NULL COMMENT '11-12个月库龄成本价原值',
  `inv_age_365_plus_days` decimal(24,6) DEFAULT NULL COMMENT '12个月以上库龄',
  `inv_age_365_plus_price` varchar(100) DEFAULT NULL COMMENT '12个月以上库龄成本价原值',
  `recommended_action` varchar(1000) DEFAULT NULL COMMENT '推荐操作',
  `sell_through` decimal(24,6) DEFAULT NULL COMMENT '售出率',
  `estimated_excess_quantity` decimal(24,6) DEFAULT NULL COMMENT '预计冗余数量',
  `estimated_storage_cost_next_month` decimal(24,6) DEFAULT NULL COMMENT '预计30天仓储费用',
  `fba_minimum_inventory_level` decimal(24,6) DEFAULT NULL COMMENT '最低库存水平',
  `fba_inventory_level_health_status` varchar(255) DEFAULT NULL COMMENT '库存水平健康度',
  `historical_days_of_supply` decimal(24,6) DEFAULT NULL COMMENT '历史供货天数',
  `historical_days_of_supply_price` varchar(100) DEFAULT NULL COMMENT '历史供货天数成本价原值',
  `low_inventory_level_fee_applied` varchar(255) DEFAULT NULL COMMENT '低库存水平费收取情况',
  `fulfillment_channel` varchar(255) DEFAULT NULL COMMENT '配送方式',
  `cg_price` varchar(100) DEFAULT NULL COMMENT '单位采购成本原值',
  `cg_transport_costs` varchar(100) DEFAULT NULL COMMENT '单位头程费用原值',
  `warehouse_damaged_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售详情：仓库残损',
  `customer_damaged_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售详情：买家残损',
  `carrier_damaged_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售详情：承运人残损',
  `distributor_damaged_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售详情：分销商残损',
  `defective_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售详情：存在瑕疵',
  `expired_quantity` decimal(24,6) DEFAULT NULL COMMENT '不可售详情：已过期',
  `fba_storage_quantity_list_json` longtext COMMENT '共享仓FBA可售信息列表JSON',
  `raw_json` longtext NOT NULL COMMENT '接口单条完整原始JSON，用于保留未来新增字段',
  `sync_batch_id` varchar(64) NOT NULL COMMENT '同步批次ID',
  `pulled_at` datetime NOT NULL COMMENT '实际拉取时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_amz_fba_snapshot_month` (`pull_month`),
  KEY `idx_amz_fba_snapshot_month_sid` (`pull_month`,`sid`),
  KEY `idx_amz_fba_snapshot_month_sku` (`pull_month`,`sku`),
  KEY `idx_amz_fba_snapshot_month_msku` (`pull_month`,`seller_sku`),
  KEY `idx_amz_fba_snapshot_asin` (`asin`),
  KEY `idx_amz_fba_snapshot_batch` (`sync_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星Amazon FBA库存v2全量月度快照';

-- 统一为标准带括号调用目标，并启用每月1日22:30任务。
UPDATE `sys_job`
SET `job_name` = '领星-Amazon FBA库存月度快照',
    `job_group` = 'OPERATION',
    `invoke_target` = 'operationSyncTask.syncAmzFbaInventorySnapshot()',
    `cron_expression` = '0 30 22 1 * ?',
    `misfire_policy` = '2',
    `concurrent` = '1',
    `status` = '0',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = '每月1日22:30全量拉取当前年月；同年月整月覆盖，不同年月新增保留'
WHERE `invoke_target` IN (
  'operationSyncTask.syncAmzFbaInventorySnapshot',
  'operationSyncTask.syncAmzFbaInventorySnapshot()'
);

INSERT INTO `sys_job` (
  `job_name`, `job_group`, `invoke_target`, `cron_expression`,
  `misfire_policy`, `concurrent`, `status`,
  `create_by`, `create_time`, `remark`
)
SELECT
  '领星-Amazon FBA库存月度快照',
  'OPERATION',
  'operationSyncTask.syncAmzFbaInventorySnapshot()',
  '0 30 22 1 * ?',
  '2',
  '1',
  '0',
  'SYSTEM',
  NOW(),
  '每月1日22:30全量拉取当前年月；同年月整月覆盖，不同年月新增保留'
WHERE NOT EXISTS (
  SELECT 1 FROM `sys_job`
  WHERE `invoke_target` IN (
    'operationSyncTask.syncAmzFbaInventorySnapshot',
    'operationSyncTask.syncAmzFbaInventorySnapshot()'
  )
);

SELECT `job_id`, `job_name`, `invoke_target`, `cron_expression`, `status`
FROM `sys_job`
WHERE `invoke_target` = 'operationSyncTask.syncAmzFbaInventorySnapshot()';
