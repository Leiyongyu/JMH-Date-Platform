-- Python库：谷仓区域仓库存 ODS（接口 /inventory/get_product_inventory，V1）。
-- 只建表，幂等；不清空、不改其他表。同步任务 goodcang_product_inventory_sync 在一个事务里整表替换，
-- 读方（价格分析刷表）在一致性读下只会看到旧表或新表，所以不与刷表共锁。
-- 所有区域仓原样落库（含 CZ、IT 等）；站点映射与过滤放在价格分析的 DWS 映射里做。缺值不补零。
SET NAMES utf8mb4;
USE `date-project`;

CREATE TABLE IF NOT EXISTS `ods_goodcang_product_inventory_latest` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键；不作为业务关联键',
  `warehouse_code` VARCHAR(32) NOT NULL COMMENT '区域仓代码，如 DE/UK/USEA/USWE/CZ',
  `warehouse_desc` VARCHAR(255) NULL COMMENT '区域仓描述；接口原值',
  `product_sku` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL COMMENT '谷仓商品SKU，如 JMH-10437-0774；区分大小写',
  `product_title` VARCHAR(1000) NULL COMMENT '商品名称；接口原值',
  `sellable` BIGINT NULL COMMENT '良品可售数量',
  `reserved` BIGINT NULL COMMENT '良品待出库数量（已被出库单预占）',
  `onway` BIGINT NULL COMMENT '海外在途数量',
  `transfer_onway` BIGINT NULL COMMENT '发货在途数量',
  `total_onway` BIGINT NULL COMMENT '总在途 = 发货在途 + 海外在途',
  `pending` BIGINT NULL COMMENT '待上架数量',
  `unsellable` BIGINT NULL COMMENT '不良品可售数量',
  `pi_freeze` BIGINT NULL COMMENT '冻结数量',
  `stocking` BIGINT NULL COMMENT '备货数量',
  `pi_warning_qty` BIGINT NULL COMMENT '预警库存数量(可售)',
  `pi_no_stock` BIGINT NULL COMMENT '缺货数量',
  `product_type` INT NULL COMMENT '0 常规商品 / 1 包材SKU',
  `raw_json` JSON NOT NULL COMMENT '原始数据行全部字段；数值不经float',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次；只留最新一份，不保留历史',
  `pulled_at` DATETIME NOT NULL COMMENT '本次同步开始时刻（北京时间）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gc_inventory_wh_sku` (`warehouse_code`, `product_sku`),
  KEY `idx_gc_inventory_sku` (`product_sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-谷仓区域仓库存最新快照；完整拉取并校验后单事务整表替换，不保留历史';
