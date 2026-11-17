-- 目标库：jmh_data_platform（Java ERP数据库）。
-- 功能：保存谷仓eBay库存库龄全量月快照，以及领星产品采购价、阶梯价和国家头程成本月快照。

CREATE TABLE IF NOT EXISTS `ods_goodcang_inventory_age_monthly` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '快照归属年月，格式YYYY-MM',
    `warehouse_code` VARCHAR(30) NOT NULL DEFAULT '' COMMENT '谷仓仓库代码',
    `product_sku` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '谷仓商品SKU',
    `iba_quantity` BIGINT NOT NULL DEFAULT 0 COMMENT '在库库存数量',
    `iba_fifo_time` VARCHAR(32) NULL COMMENT '上架时间，保留谷仓原始格式',
    `iba_warning_age` INT NULL COMMENT '预警库龄',
    `product_title` VARCHAR(500) NULL COMMENT '商品中文名称',
    `product_title_en` VARCHAR(500) NULL COMMENT '商品英文名称',
    `warehouse_desc` VARCHAR(255) NULL COMMENT '谷仓仓库名称',
    `warehouse_age` INT NULL COMMENT '谷仓返回的库龄天数',
    `expiration_date` VARCHAR(32) NULL COMMENT '过期日期，保留谷仓原始格式',
    `source_page` INT NOT NULL COMMENT '接口来源页码',
    `source_row_no` INT NOT NULL COMMENT '接口页内行号',
    `api_code` INT NULL COMMENT '谷仓接口业务状态码',
    `api_message` VARCHAR(500) NULL COMMENT '谷仓接口返回消息',
    `api_total` BIGINT NULL COMMENT '谷仓接口返回总记录数',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `raw_json` JSON NOT NULL COMMENT '谷仓库龄明细原始JSON，用于完整保留接口数据',
    `pulled_at` DATETIME NOT NULL COMMENT '接口拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_gc_inventory_age_month_page_row` (`snapshot_month`,`source_page`,`source_row_no`),
    KEY `idx_gc_inventory_age_month_sku` (`snapshot_month`,`product_sku`),
    KEY `idx_gc_inventory_age_month_warehouse` (`snapshot_month`,`warehouse_code`),
    KEY `idx_gc_inventory_age_month_age` (`snapshot_month`,`warehouse_age`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='谷仓eBay库存库龄月度ODS全量快照';

CREATE TABLE IF NOT EXISTS `ods_lingxing_product_procurement_monthly` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '快照归属年月，格式YYYY-MM',
    `sku` VARCHAR(255) NOT NULL COMMENT '领星本地产品SKU',
    `cg_price` DECIMAL(24,6) NULL COMMENT '采购成本，来源data.cg_price',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `pulled_at` DATETIME NOT NULL COMMENT '接口拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_lx_product_procurement_month_sku` (`snapshot_month`,`sku`),
    KEY `idx_lx_product_procurement_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='领星产品管理采购成本月度ODS快照';

CREATE TABLE IF NOT EXISTS `ods_lingxing_product_supplier_step_price_monthly` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '快照归属年月，格式YYYY-MM',
    `sku` VARCHAR(255) NOT NULL COMMENT '领星本地产品SKU',
    `supplier_index` INT NOT NULL COMMENT 'supplier_quote数组顺序下标',
    `quote_index` INT NOT NULL COMMENT 'quotes数组顺序下标',
    `step_price_index` INT NOT NULL COMMENT 'step_prices数组顺序下标',
    `price` DECIMAL(24,6) NOT NULL COMMENT '供应商阶梯不含税单价，来源supplier_quote.quotes.step_prices.price',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `pulled_at` DATETIME NOT NULL COMMENT '接口拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_lx_step_price_month_position` (`snapshot_month`,`sku`,`supplier_index`,`quote_index`,`step_price_index`),
    KEY `idx_lx_step_price_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='领星产品供应商阶梯价月度ODS明细';

CREATE TABLE IF NOT EXISTS `ods_lingxing_product_transport_cost_monthly` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '快照归属年月，格式YYYY-MM',
    `sku` VARCHAR(255) NOT NULL COMMENT '领星本地产品SKU',
    `relation_index` INT NOT NULL COMMENT 'product_logistics_relation数组顺序下标',
    `country_code` CHAR(2) NOT NULL COMMENT '国家简码，由XX_cg_transport_costs字段前缀提取',
    `transport_cost` DECIMAL(24,6) NOT NULL COMMENT '默认头程成本含税，来源product_logistics_relation.XX_cg_transport_costs',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `pulled_at` DATETIME NOT NULL COMMENT '接口拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_lx_transport_cost_month_position` (`snapshot_month`,`sku`,`relation_index`,`country_code`),
    KEY `idx_lx_transport_cost_sku_country` (`sku`,`country_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='领星产品国家默认头程成本月度ODS明细';

UPDATE `sys_job`
SET `job_name`='谷仓-eBay库存库龄月快照',
    `job_group`='DATA_CENTER',
    `invoke_target`='operationSyncTask.syncGoodcangInventoryAge()',
    `cron_expression`='0 0 22 3 * ?',
    `misfire_policy`='2',
    `concurrent`='1',
    `status`='1',
    `update_by`='SYSTEM',
    `update_time`=NOW(),
    `remark`='已并入AMZ FBA与谷仓eBay库存库龄同步任务；本任务仅保留手工排查入口。'
WHERE `invoke_target` IN (
    'operationSyncTask.syncGoodcangInventoryAge',
    'operationSyncTask.syncGoodcangInventoryAge()'
);

UPDATE `sys_job`
SET `job_name`='领星-产品采购与头程成本月快照',
    `job_group`='DATA_CENTER',
    `invoke_target`='operationSyncTask.syncLingxingProductProcurement()',
    `cron_expression`='0 0 23 3 * ?',
    `misfire_policy`='2',
    `concurrent`='1',
    `status`='1',
    `update_by`='SYSTEM',
    `update_time`=NOW(),
    `remark`='已并入AMZ FBA与谷仓eBay库存库龄同步任务；本任务仅保留手工排查入口。'
WHERE `invoke_target` IN (
    'operationSyncTask.syncLingxingProductProcurement',
    'operationSyncTask.syncLingxingProductProcurement()'
);

INSERT INTO `sys_job` (
    `job_name`,`job_group`,`invoke_target`,`cron_expression`,
    `misfire_policy`,`concurrent`,`status`,`create_by`,`create_time`,`remark`
)
SELECT
    '谷仓-eBay库存库龄月快照','DATA_CENTER',
    'operationSyncTask.syncGoodcangInventoryAge()','0 0 22 3 * ?',
    '2','1','1','SYSTEM',NOW(),
    '已并入AMZ FBA与谷仓eBay库存库龄同步任务；本任务仅保留手工排查入口。'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` IN (
        'operationSyncTask.syncGoodcangInventoryAge',
        'operationSyncTask.syncGoodcangInventoryAge()'
    )
);

INSERT INTO `sys_job` (
    `job_name`,`job_group`,`invoke_target`,`cron_expression`,
    `misfire_policy`,`concurrent`,`status`,`create_by`,`create_time`,`remark`
)
SELECT
    '领星-产品采购与头程成本月快照','DATA_CENTER',
    'operationSyncTask.syncLingxingProductProcurement()','0 0 23 3 * ?',
    '2','1','1','SYSTEM',NOW(),
    '已并入AMZ FBA与谷仓eBay库存库龄同步任务；本任务仅保留手工排查入口。'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` IN (
        'operationSyncTask.syncLingxingProductProcurement',
        'operationSyncTask.syncLingxingProductProcurement()'
    )
);

SELECT table_name,table_comment
FROM information_schema.tables
WHERE table_schema=DATABASE()
  AND table_name IN (
      'ods_goodcang_inventory_age_monthly',
      'ods_lingxing_product_procurement_monthly',
      'ods_lingxing_product_supplier_step_price_monthly',
      'ods_lingxing_product_transport_cost_monthly'
  )
ORDER BY table_name;

SELECT job_id,job_name,invoke_target,cron_expression,status,remark
FROM sys_job
WHERE invoke_target IN (
    'operationSyncTask.syncGoodcangInventoryAge()',
    'operationSyncTask.syncLingxingProductProcurement()'
)
ORDER BY job_id;
