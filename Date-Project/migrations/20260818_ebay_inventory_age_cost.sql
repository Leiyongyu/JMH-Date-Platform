-- 目标库：Date-Project（Python数据处理库）。
-- 功能：保存谷仓eBay库存库龄与领星采购价、头程费用匹配后的月度明细。

CREATE TABLE IF NOT EXISTS `dwd_ebay_inventory_age_cost_snapshot` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `pull_month` CHAR(7) NOT NULL COMMENT '库存库龄快照年月，格式YYYY-MM',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次Python清洗匹配批次ID',
    `source_inventory_age_id` BIGINT UNSIGNED NOT NULL COMMENT 'Java库谷仓库存库龄ODS明细ID',
    `source_goodcang_batch_id` VARCHAR(64) NOT NULL COMMENT '谷仓库存库龄源同步批次ID',
    `source_product_batch_id` VARCHAR(64) NULL COMMENT '领星产品管理源同步批次ID',
    `source_product_sku` VARCHAR(255) NOT NULL COMMENT '谷仓原始商品SKU，例如JMH-220085-0056',
    `sku_middle` VARCHAR(255) NOT NULL COMMENT '去掉谷仓SKU首段后的中间SKU，例如220085-0056',
    `sku` VARCHAR(255) NULL COMMENT '按中间SKU匹配出的领星完整商品SKU',
    `warehouse_code` VARCHAR(30) NOT NULL COMMENT '谷仓仓库代码',
    `warehouse_name` VARCHAR(255) NULL COMMENT '谷仓仓库名称',
    `transport_country_code` CHAR(2) NULL COMMENT '仓库映射出的领星头程费用国家简码',
    `inventory_quantity` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '谷仓在库库存数量',
    `warehouse_age_days` INT NULL COMMENT '谷仓库存库龄天数',
    `inventory_age_bucket` VARCHAR(20) NOT NULL COMMENT '库龄区间：0_90、91_180、181_PLUS或UNKNOWN',
    `cg_price` DECIMAL(24,6) NULL COMMENT '领星产品管理采购成本data.cg_price',
    `step_price` DECIMAL(24,6) NULL COMMENT '领星供应商阶梯价中的正数价格最大值',
    `purchase_price` DECIMAL(24,6) NULL COMMENT '清洗后单位采购价，优先正数阶梯价，否则取cg_price',
    `first_leg_cost` DECIMAL(24,6) NULL COMMENT '按谷仓仓库国家匹配的领星单位头程费用',
    `unit_landed_cost` DECIMAL(24,6) NULL COMMENT '单位货值，等于采购价加头程费用',
    `inventory_age_cost` DECIMAL(24,6) NULL COMMENT 'SKU库龄成本，等于采购价加头程费用，不乘库存数量',
    `match_status` VARCHAR(40) NOT NULL COMMENT '匹配状态：MATCHED、PRODUCT_NOT_FOUND、PRODUCT_AMBIGUOUS、PURCHASE_PRICE_NOT_FOUND或TRANSPORT_COST_NOT_FOUND',
    `source_pulled_at` DATETIME NOT NULL COMMENT '谷仓库存库龄源数据拉取时间',
    `pulled_at` DATETIME NOT NULL COMMENT '本次Python清洗匹配时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ebay_inventory_age_month_source` (`pull_month`,`source_inventory_age_id`),
    KEY `idx_ebay_inventory_age_month_bucket` (`pull_month`,`inventory_age_bucket`),
    KEY `idx_ebay_inventory_age_month_sku` (`pull_month`,`sku`),
    KEY `idx_ebay_inventory_age_month_status` (`pull_month`,`match_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-eBay海外仓库存库龄采购价与头程费用匹配明细';
