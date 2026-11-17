-- Python数据库：仅新建两张历史透视表，不删除旧表、不改任务或权限、不自动生成历史。
-- CREATE IF NOT EXISTS可重跑；已存在但结构不一致时请先核查，勿删除历史表重建。
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ebay_inventory_pivot_snapshot` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '历史透视快照主键',
  `stat_date` DATE NOT NULL COMMENT '统计日期；生成时的中国时区实际日期，同日覆盖、跨日保留',
  `stat_month` CHAR(7) NOT NULL COMMENT '统计年月YYYY-MM；由stat_date生成，不代替周变化日期',
  `generated_at` DATETIME(6) NOT NULL COMMENT '实际生成完成时间；中国时区',
  `inventory_batch_id` VARCHAR(64) NOT NULL COMMENT '生成时采用的成功周报库存批次ID',
  `inventory_snapshot_date` DATE NULL COMMENT '源库存快照日期；不冒充统计日期',
  `inventory_pulled_at` DATETIME NULL COMMENT '源库存实际拉取时间',
  `trigger_type` VARCHAR(32) NOT NULL COMMENT '触发来源；JOB、manual或BOOTSTRAP等',
  `item_count` INT NOT NULL COMMENT '本次冻结的站点加完整SKU明细总数',
  `group_count` INT NOT NULL COMMENT '本次负责人加站点汇总行数',
  `metadata_json` JSON NOT NULL COMMENT '冻结来源批次、销量锚点、汇率月、负责人规则月及缺失提示等追溯信息',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首建时间',
  `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近一次同日覆盖时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_inventory_pivot_date` (`stat_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Ebay库存负责人历史透视快照；同日事务覆盖、其他日期永久保存，不随周报ODS清理';

CREATE TABLE IF NOT EXISTS `ebay_inventory_pivot_owner` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '负责人站点汇总主键',
  `snapshot_id` BIGINT UNSIGNED NOT NULL COMMENT '所属历史快照ID',
  `owner` VARCHAR(128) NOT NULL COMMENT '冻结的负责人；未匹配保留未分配',
  `site` VARCHAR(32) NOT NULL COMMENT '归一站点；不跨站合并库存或销量',
  `sku_count` INT NOT NULL COMMENT '同负责人同站点的完整SKU去重数量',
  `overseas_sellable_quantity` DECIMAL(30,6) NOT NULL COMMENT '海外可售数量合计',
  `overseas_total_quantity` DECIMAL(30,6) NOT NULL COMMENT '海外总库存合计',
  `sales_qty_30d` DECIMAL(30,6) NOT NULL COMMENT '冻结的近30天销量合计；沿用源数据最新付款日锚点',
  `in_stock_sales_ratio` DECIMAL(30,6) NOT NULL COMMENT '可售合计除销量合计；零分母为0，保存比值不乘100',
  `total_stock_sales_ratio` DECIMAL(30,6) NOT NULL COMMENT '总库存合计除销量合计；零分母为0，保存比值不乘100',
  `overseas_sellable_value` DECIMAL(30,2) NULL COMMENT '人民币海外可售货值；仅汇总有值SKU，全部缺失为NULL',
  `overseas_total_value` DECIMAL(30,2) NULL COMMENT '人民币海外总货值；仅汇总有值SKU，全部缺失为NULL',
  `warehouse_rent_30d_cny` DECIMAL(30,2) NULL COMMENT '人民币30天谷仓仓租；排除缺失或冲突，仅汇总有值SKU，全部缺失为NULL',
  `missing_price_count` INT NOT NULL COMMENT '缺失或异常单价的SKU数；有效0单价不计缺失',
  `missing_rent_count` INT NOT NULL COMMENT '缺失、异常或冲突仓租的SKU数；有效0仓租不计缺失',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_inventory_pivot_owner_site` (`snapshot_id`,`owner`,`site`),
  KEY `idx_ebay_inventory_pivot_owner_site` (`owner`,`site`),
  CONSTRAINT `fk_ebay_inventory_pivot_snapshot` FOREIGN KEY (`snapshot_id`)
    REFERENCES `ebay_inventory_pivot_snapshot` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Ebay库存历史负责人站点汇总；值生成后冻结，查询不回算当前来源';
