-- 单独部署仓租概要+明细链：仅建表及注册，不清空数据、不拉接口。
-- 跨两库分段提交；部分失败修复后重跑。需已有date-project.scheduler_task。
SET NAMES utf8mb4;
USE `jmh_data_platform`;
-- 防止已有重复入口或同名不同入口被悄悄再创建；错误时停止，不使用--force。
DROP TEMPORARY TABLE IF EXISTS _gc_rent_weekly_job_guard;
CREATE TEMPORARY TABLE _gc_rent_weekly_job_guard (valid_parent BIGINT NOT NULL);
INSERT INTO _gc_rent_weekly_job_guard
SELECT IF(
 (SELECT COUNT(*) FROM sys_job WHERE TRIM(invoke_target) IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()')) <= 1
 AND NOT EXISTS (SELECT 1 FROM sys_job WHERE job_name='谷仓仓租概要及明细近30天同步'
   AND (invoke_target IS NULL OR TRIM(invoke_target) NOT IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()')))
 AND NOT EXISTS (SELECT 1 FROM sys_job WHERE TRIM(invoke_target) IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()')
   AND LENGTH(invoke_target)<>LENGTH(TRIM(invoke_target))),
 1,NULL);
DROP TEMPORARY TABLE _gc_rent_weekly_job_guard;
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
START TRANSACTION;
INSERT INTO scheduler_task (task_code, task_name, cron_expression, enabled, description)
VALUES ('goodcang_wh_inventory_storage_sync', '谷仓仓租概要及明细近30天同步', '0 0 7 ? * MON', 1,
 '每周一07:00；北京时间包含当天近30天；先拉概要，再按去重单号分页拉明细，全部校验后两表同一事务全量替换。Quartz为唯一计时器。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name), cron_expression=VALUES(cron_expression),
 description=VALUES(description);

COMMIT;
USE `jmh_data_platform`;
START TRANSACTION;
UPDATE sys_job
SET job_name='谷仓仓租概要及明细近30天同步', cron_expression='0 0 7 ? * MON',
    invoke_target='pythonGoodcangStorageTask.runWeekly()',
    misfire_policy='2', concurrent='1',
    update_by='SYSTEM', update_time=NOW(),
    remark='每周一北京时间07:00；包含当天近30天；先拉概要单号再逐单分页拉明细；Python两表同事务全量替换。服务器时区须为Asia/Shanghai。'
WHERE invoke_target IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()');

INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,
 concurrent,status,create_by,create_time,remark)
SELECT '谷仓仓租概要及明细近30天同步','DEFAULT','pythonGoodcangStorageTask.runWeekly()',
 '0 0 7 ? * MON','2','1','0','SYSTEM',NOW(),
 '每周一北京时间07:00；包含当天近30天；先拉概要单号再逐单分页拉明细；Python两表同事务全量替换。服务器时区须为Asia/Shanghai。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job
 WHERE invoke_target IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()'));
COMMIT;
SELECT job_id,job_name,invoke_target,cron_expression,status FROM sys_job WHERE invoke_target IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()');
SELECT task_code,task_name,enabled,cron_expression FROM `date-project`.scheduler_task WHERE task_code='goodcang_wh_inventory_storage_sync';
