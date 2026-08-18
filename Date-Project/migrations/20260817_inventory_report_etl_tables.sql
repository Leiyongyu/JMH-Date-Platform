-- 目标库：Date-Project（Python 数据库）。不要在 jmh_data_platform 执行。
-- 月度库存报表清洗明细、分维度汇总和部门主表；所有表及字段均使用中文注释。

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_fba_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT 'FBA库存ODS源表主键',
    `source_child_index` INT NOT NULL DEFAULT 0 COMMENT 'ODS子明细序号，非嵌套明细为0',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '源数据同步批次ID',
    `sid` VARCHAR(32) NULL COMMENT '领星店铺SID',
    `store_name` VARCHAR(255) NULL COMMENT 'ERP店铺名称',
    `group_code` VARCHAR(32) NULL COMMENT '库存归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `ware_house_name` VARCHAR(255) NULL COMMENT '领星仓库名称',
    `msku` VARCHAR(255) NULL COMMENT '亚马逊卖家SKU（MSKU）',
    `asin` VARCHAR(64) NULL COMMENT '亚马逊商品标识码（ASIN）',
    `fnsku` VARCHAR(255) NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `local_sku` VARCHAR(255) NULL COMMENT '本地商品SKU',
    `local_name` VARCHAR(1000) NULL COMMENT '本地商品名称',
    `country_code` VARCHAR(32) NULL COMMENT '国家或站点编码',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存含移仓数量',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存含移仓总成本',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_fba_month_source` (`stat_month`,`source_id`,`source_child_index`),
    KEY `idx_inventory_fba_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_fba_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_fba_month_sid` (`stat_month`,`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-领星FBA月度库存报表清洗明细';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_overseas_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT '海外仓库存ODS源表主键',
    `source_child_index` INT NOT NULL DEFAULT 0 COMMENT 'ODS子明细序号，非嵌套明细为0',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '源数据同步批次ID',
    `sys_wid` VARCHAR(32) NULL COMMENT '领星系统仓库ID',
    `ware_house_name` VARCHAR(255) NULL COMMENT '领星仓库名称',
    `seller_name` VARCHAR(255) NULL COMMENT '店铺或卖家名称',
    `product_name` VARCHAR(1000) NULL COMMENT '商品名称',
    `sku` VARCHAR(255) NULL COMMENT '商品SKU',
    `fnsku` VARCHAR(255) NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `spu` VARCHAR(255) NULL COMMENT '标准产品单元（SPU）',
    `api_sku` VARCHAR(255) NULL COMMENT '第三方库存SKU',
    `brand` VARCHAR(255) NULL COMMENT '商品品牌',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `group_code` VARCHAR(32) NULL COMMENT '库存归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存数量',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_overseas_month_source` (`stat_month`,`source_id`,`source_child_index`),
    KEY `idx_inventory_overseas_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_overseas_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_overseas_month_wid` (`stat_month`,`sys_wid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-领星海外仓月度库存报表清洗明细';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_local_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT '本地仓库存ODS源表主键',
    `source_child_index` INT NOT NULL DEFAULT 0 COMMENT 'ODS子明细序号，非嵌套明细为0',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '源数据同步批次ID',
    `sys_wid` VARCHAR(32) NULL COMMENT '领星系统仓库ID',
    `ware_house_name` VARCHAR(255) NULL COMMENT '领星仓库名称',
    `seller_name` VARCHAR(255) NULL COMMENT '店铺或卖家名称',
    `product_name` VARCHAR(1000) NULL COMMENT '商品名称',
    `sku` VARCHAR(255) NULL COMMENT '商品SKU',
    `fnsku` VARCHAR(255) NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `spu` VARCHAR(255) NULL COMMENT '标准产品单元（SPU）',
    `brand` VARCHAR(255) NULL COMMENT '商品品牌',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `group_code` VARCHAR(32) NULL COMMENT '库存归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存数量',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_local_month_source` (`stat_month`,`source_id`,`source_child_index`),
    KEY `idx_inventory_local_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_local_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_local_month_wid` (`stat_month`,`sys_wid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-领星本地仓月度库存报表清洗明细';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_amz_sales_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT 'Amazon订单利润ODS源表主键',
    `sid` VARCHAR(32) NOT NULL COMMENT '领星Amazon店铺SID',
    `store_name` VARCHAR(255) NULL COMMENT 'ERP店铺名称',
    `group_code` VARCHAR(32) NULL COMMENT '销售归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `msku` VARCHAR(255) NOT NULL COMMENT 'Amazon卖家SKU（MSKU）',
    `local_sku` VARCHAR(255) NULL COMMENT '本地商品SKU',
    `asin` VARCHAR(64) NULL COMMENT 'Amazon商品标识码（ASIN）',
    `item_name` TEXT NULL COMMENT '商品名称',
    `currency_code` VARCHAR(16) NOT NULL DEFAULT 'CNY' COMMENT '销售额币种，本链路固定为CNY',
    `amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '用于实际达成计算的销售额',
    `volume` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '清洗后自然月商品销量',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_amz_sales_month_source` (`stat_month`,`source_id`),
    KEY `idx_inventory_amz_sales_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_amz_sales_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_amz_sales_month_sid_msku` (`stat_month`,`sid`,`msku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-月度库存统计Amazon销售额清洗明细';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_ebay_sales_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT 'eBay销售额ODS源表主键',
    `sku` VARCHAR(255) NOT NULL COMMENT 'eBay商品SKU',
    `brand_code` VARCHAR(32) NOT NULL COMMENT '从SKU解析出的品牌编码',
    `image_url` TEXT NULL COMMENT '商品图片链接',
    `multi_variant` VARCHAR(16) NULL COMMENT '是否多属性',
    `department_code` VARCHAR(32) NOT NULL DEFAULT 'EBAY-1' COMMENT '汇总部门编码，固定EBAY-1',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '按eBay品牌规则匹配的负责人',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `product_sales_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '商品销售额',
    `receivable_shipping_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '应收运费',
    `amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'eBay实际达成金额，商品销售额加应收运费',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_ebay_sales_month_source` (`stat_month`,`source_id`),
    KEY `idx_inventory_ebay_sales_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_ebay_sales_month_brand` (`stat_month`,`brand_code`),
    KEY `idx_inventory_ebay_sales_month_sku` (`stat_month`,`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-月度库存统计eBay实际达成负责人清洗明细';

CREATE TABLE IF NOT EXISTS `dws_inventory_report_dimension_summary` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_type` VARCHAR(16) NOT NULL COMMENT '来源类型：FBA、OVERSEAS或LOCAL',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `dimension_type` VARCHAR(16) NOT NULL COMMENT '汇总维度：GROUP、OWNER或WAREHOUSE',
    `dimension_value` VARCHAR(255) NOT NULL COMMENT '组别、负责人或仓库名称',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `source_rows` INT NOT NULL DEFAULT 0 COMMENT '参与汇总的明细行数',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量汇总',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本汇总',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存数量汇总',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存总成本汇总',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_dimension` (`stat_month`,`source_type`,`platform_code`,`dimension_type`,`dimension_value`,`department_code`),
    KEY `idx_inventory_dimension_month_department` (`stat_month`,`department_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWS-月度库存报表来源维度汇总';

CREATE TABLE IF NOT EXISTS `dws_inventory_report_department_summary` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `department_code` VARCHAR(32) NOT NULL COMMENT '部门编码',
    `department_name` VARCHAR(64) NOT NULL COMMENT '部门显示名称',
    `display_order` INT NOT NULL COMMENT '页面显示顺序',
    `is_total` TINYINT NOT NULL DEFAULT 0 COMMENT '是否汽配小计行：0否，1是',
    `local_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末在途数量',
    `local_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末在途总成本',
    `local_end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末库存数量',
    `local_end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末库存总成本',
    `overseas_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末在途数量',
    `overseas_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末在途总成本',
    `overseas_end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末库存数量',
    `overseas_end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末库存总成本',
    `fba_end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末库存含移仓数量',
    `fba_end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末库存含移仓总成本',
    `fba_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末在途数量',
    `fba_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末在途总成本',
    `next_month_opening_inventory_qty` DECIMAL(24,6) NULL DEFAULT NULL COMMENT '次月月初库存数量，取本月海外仓与FBA仓期末库存数量之和',
    `actual_achievement_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '实际达成销售额，Amazon订单利润按部门汇总，币种CNY',
    `target_achievement_rate` DECIMAL(24,10) NOT NULL DEFAULT 0 COMMENT '目标达成率，实际达成除以销售冲刺目标',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_department_month` (`stat_month`,`department_code`),
    KEY `idx_inventory_department_month_order` (`stat_month`,`display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWS-月度库存报表部门主表';

CREATE TABLE IF NOT EXISTS `monthly_inventory_report_manual_input` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `department_code` VARCHAR(32) NOT NULL COMMENT '部门编码',
    `local_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '人工填写的本地仓期末在途数量',
    `local_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '人工填写的本地仓期末在途总成本',
    `updated_by` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最后修改人',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后修改时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_manual_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_manual_month` (`stat_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='月度库存报表本地仓期末在途人工录入表；按月份与部门唯一';
