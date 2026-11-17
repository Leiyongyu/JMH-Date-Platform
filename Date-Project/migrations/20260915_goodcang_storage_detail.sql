-- Python库：仅创建仓租明细源表；部署不删除、不覆盖任何业务数据。
-- 接口 /finance/get_wh_inventory_storage_detail；保留20个源字段及原始JSON。
-- wis_code不设唯一键：同一仓租单可包含同SKU多条收费明细，不在ODS层合并。
SET NAMES utf8mb4;
USE `date-project`;

CREATE TABLE IF NOT EXISTS `ods_goodcang_wh_inventory_storage_detail` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键；不作为业务关联键',
  `wis_code` VARCHAR(64) NULL COMMENT '仓租单号；接口原值',
  `reference_no` VARCHAR(255) NULL COMMENT '参考编号；保留前导零',
  `warehouse_code` VARCHAR(64) NULL COMMENT '仓库代码；接口原值',
  `product_sku` VARCHAR(255) NULL COMMENT '商品编码；接口原值',
  `product_barcode` VARCHAR(255) NULL COMMENT '产品代码；接口原值',
  `product_name` VARCHAR(1000) NULL COMMENT '产品名称；接口原值',
  `quantity` BIGINT NULL COMMENT '数量；接口原值，缺失不补零',
  `length` DECIMAL(30,12) NULL COMMENT '产品长cm；接口原值',
  `width` DECIMAL(30,12) NULL COMMENT '产品宽cm；接口原值',
  `height` DECIMAL(30,12) NULL COMMENT '产品高cm；接口原值',
  `volume` DECIMAL(30,12) NULL COMMENT '体积m3；接口原值',
  `cargo_type` VARCHAR(64) NULL COMMENT '货型；接口原值',
  `day` BIGINT NULL COMMENT '库龄天数；接口原值，缺失不补零',
  `bill_amount` DECIMAL(30,12) NULL COMMENT '总金额不含税；计费币种原币，不换算',
  `settlement_amount` DECIMAL(30,12) NULL COMMENT '结算金额不含税；结算币种原币，不换算',
  `warehouse_rent_amount` DECIMAL(30,12) NULL COMMENT '仓租金额不含税；接口原币金额，不换算',
  `bill_currency_code` VARCHAR(16) NULL COMMENT '计费币种；接口原值',
  `settlement_currency_code` VARCHAR(16) NULL COMMENT '结算币种；接口原值',
  `charge_date` VARCHAR(32) NULL COMMENT '计费时间；接口字符串原值',
  `putaway_date` VARCHAR(32) NULL COMMENT '上架时间；接口字符串原值',
  `request_wis_code` VARCHAR(64) NOT NULL COMMENT '实际请求仓租单号；与响应wis_code分开保留用于追溯',
  `request_date_from` DATETIME NOT NULL COMMENT '概要查询开始时间；北京时间，非明细接口请求参数',
  `request_date_to` DATETIME NOT NULL COMMENT '概要查询截止时间；北京时间，非明细接口请求参数',
  `source_page` INT UNSIGNED NOT NULL COMMENT '当前仓租单的来源页码，从1开始',
  `source_row_no` INT UNSIGNED NOT NULL COMMENT '页内行号，从1开始',
  `api_count` INT UNSIGNED NOT NULL COMMENT '当前仓租单明细接口总数量',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '与概要一致的当前同步标识；不保留历史批次',
  `pulled_at` DATETIME NOT NULL COMMENT '本次链式同步起始时刻，也是概要窗口截止时刻',
  `raw_json` JSON NOT NULL COMMENT '原始明细行全部字段；数值精度不降级float',
  PRIMARY KEY (`id`),
  KEY `idx_gc_storage_detail_wis` (`wis_code`),
  KEY `idx_gc_storage_detail_request` (`request_wis_code`),
  KEY `idx_gc_storage_detail_sku_date` (`warehouse_code`, `product_sku`, `charge_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-谷仓近30天仓租单全部明细；概要及逐单明细完整拉取后同事务全表替换，不保留历史';

-- 同一任务升级为概要及明细链，不创建第二个计时器。
START TRANSACTION;
INSERT INTO scheduler_task (task_code, task_name, cron_expression, enabled, description)
VALUES ('goodcang_wh_inventory_storage_sync', '谷仓仓租概要及明细近30天同步', '0 0 7 ? * MON', 1,
 '每周一07:00；北京时间包含当天近30天；先拉概要，再按去重单号分页拉明细，全部校验后两表同一事务全量替换。Quartz为唯一计时器。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name), cron_expression=VALUES(cron_expression),
 description=VALUES(description);

COMMIT;
