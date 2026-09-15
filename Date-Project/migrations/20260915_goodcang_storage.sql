-- Python库：仅新建源表、登记任务；不会在部署时清空数据。
-- 依赖现有 scheduler_task / scheduler_task_run（本项目已部署调度基础表）。
SET NAMES utf8mb4;
USE `date-project`;

CREATE TABLE IF NOT EXISTS `ods_goodcang_wh_inventory_storage` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键；不作为业务关联键',
  `currency_code` VARCHAR(16) NULL COMMENT '计费货币；接口原值',
  `isdb_volume` DECIMAL(30,12) NULL COMMENT '体积m3；不换算',
  `is_amount` DECIMAL(30,12) NULL COMMENT '计费总金额含税；计费货币原币',
  `is_date` VARCHAR(32) NULL COMMENT '发生时间；接口字符串原值',
  `is_settlement_amount` DECIMAL(30,12) NULL COMMENT '结算总金额含税；结算货币原币',
  `note` TEXT NULL COMMENT '备注；接口原值',
  `settlement_currency_code` VARCHAR(16) NULL COMMENT '结算货币；接口原值',
  `warehouse_code` VARCHAR(64) NULL COMMENT '仓库代码；关联字段',
  `wis_code` VARCHAR(64) NULL COMMENT '仓租单号；用于后续关联仓租明细',
  `wp_settlement_cycle` VARCHAR(64) NULL COMMENT '结算周期；接口原值',
  `request_date_from` DATETIME NOT NULL COMMENT '本次查询开始时间；北京时间',
  `request_date_to` DATETIME NOT NULL COMMENT '本次查询截止时间；北京时间',
  `source_page` INT UNSIGNED NOT NULL COMMENT '来源页码，从1开始',
  `source_row_no` INT UNSIGNED NOT NULL COMMENT '页内行号，从1开始',
  `api_count` INT UNSIGNED NOT NULL COMMENT '接口总数量',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '当前同步请求标识，仅留最新数据，不保留历史批次',
  `pulled_at` DATETIME NOT NULL COMMENT '本次同步起始时刻，也是窗口截止时刻',
  `raw_json` JSON NOT NULL COMMENT '原始数据行全部字段；数值精度不降级float',
  PRIMARY KEY (`id`),
  KEY `idx_gc_storage_wis` (`wis_code`),
  KEY `idx_gc_storage_warehouse_date` (`warehouse_code`, `is_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-谷仓仓租概要近30天；完整拉取成功后全表事务替换，不保留历史';

START TRANSACTION;
INSERT INTO scheduler_task (task_code, task_name, cron_expression, enabled, description)
VALUES ('goodcang_wh_inventory_storage_sync', '谷仓仓租概要近30天同步', '0 0 7 ? * MON', 1,
 '每周一07:00；北京时间包含当天近30天，page从1开始，pageSize=200；完整校验后全表事务替换，不保留历史数据。Quartz为唯一计时器。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name), cron_expression=VALUES(cron_expression),
 description=VALUES(description);

COMMIT;

