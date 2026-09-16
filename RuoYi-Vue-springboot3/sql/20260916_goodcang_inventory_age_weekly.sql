-- 目标库：jmh_data_platform（Java ERP数据库）。
-- 谷仓库龄周刷新：只更新latest单批表；不改原月表、月度任务或月度成本结果。
-- 先执行本SQL，再部署新Java/Python/前端并重启Java。
-- 仅写sys_job不会刷新运行中的Quartz；不要将旧月快照任务248直接改成周任务。
SET NAMES utf8mb4;
USE `jmh_data_platform`;

CREATE TABLE IF NOT EXISTS `ods_goodcang_inventory_age_latest` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '本批拉取归属年月；仅作元数据，不保存月历史',
    `warehouse_code` VARCHAR(30) NOT NULL DEFAULT '' COMMENT '谷仓仓库代码',
    `product_sku` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '谷仓商品编码',
    `iba_quantity` BIGINT NOT NULL DEFAULT 0 COMMENT '在库库存数量',
    `iba_fifo_time` VARCHAR(32) NULL COMMENT '上架时间，保留原始格式',
    `iba_warning_age` INT NULL COMMENT '预警库龄',
    `product_title` VARCHAR(500) NULL COMMENT '商品中文名称',
    `product_title_en` VARCHAR(500) NULL COMMENT '商品英文名称',
    `warehouse_desc` VARCHAR(255) NULL COMMENT '谷仓仓库名称',
    `warehouse_age` INT NULL COMMENT '谷仓返回的库龄天数',
    `expiration_date` VARCHAR(32) NULL COMMENT '过期日期，保留原始格式',
    `source_page` INT NOT NULL COMMENT '来源页码',
    `source_row_no` INT NOT NULL COMMENT '接口页内行号',
    `api_code` INT NULL COMMENT '业务状态码',
    `api_message` VARCHAR(500) NULL COMMENT '返回消息',
    `api_total` BIGINT NULL COMMENT '总记录数',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '最新成功同步批次ID',
    `raw_json` JSON NOT NULL COMMENT '完整谷仓库龄原始JSON',
    `pulled_at` DATETIME NOT NULL COMMENT '真实拉取时间；迁移初始化不改此时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_gc_age_latest_page_row` (`source_page`,`source_row_no`),
    KEY `idx_gc_age_latest_warehouse_sku` (`warehouse_code`,`product_sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='谷仓eBay库存库龄最新单批快照；每周一06:00全量事务覆盖；与月快照隔离';

START TRANSACTION;
-- 首次初始化：只在latest为空且最新月源为单批时复制，不删除或改写月表。
-- 保留原始pulled_at及batch ID，不能把9月1日的数据伪装成今天拉取。
-- 重复执行不会覆盖已周更新的latest数据；无月源/混合批次时不初始化，等首次同步。
INSERT INTO `ods_goodcang_inventory_age_latest` (
    snapshot_month,warehouse_code,product_sku,iba_quantity,iba_fifo_time,
    iba_warning_age,product_title,product_title_en,warehouse_desc,warehouse_age,
    expiration_date,source_page,source_row_no,api_code,api_message,api_total,
    sync_batch_id,raw_json,pulled_at
)
SELECT m.snapshot_month,m.warehouse_code,m.product_sku,m.iba_quantity,m.iba_fifo_time,
       m.iba_warning_age,m.product_title,m.product_title_en,m.warehouse_desc,m.warehouse_age,
       m.expiration_date,m.source_page,m.source_row_no,m.api_code,m.api_message,m.api_total,
       m.sync_batch_id,m.raw_json,m.pulled_at
FROM `ods_goodcang_inventory_age_monthly` m
WHERE m.snapshot_month=(SELECT MAX(snapshot_month) FROM `ods_goodcang_inventory_age_monthly`)
  AND NOT EXISTS (SELECT 1 FROM `ods_goodcang_inventory_age_latest`)
  AND 1=(SELECT COUNT(DISTINCT sync_batch_id) FROM `ods_goodcang_inventory_age_monthly`
         WHERE snapshot_month=(SELECT MAX(snapshot_month) FROM `ods_goodcang_inventory_age_monthly`));

-- 只定位新入口；不修改job_id、已有job_group或人工启停状态。
UPDATE `sys_job`
SET job_name='谷仓-eBay库存库龄每周刷新',
    invoke_target='operationSyncTask.syncGoodcangInventoryAgeLatest()',
    cron_expression='0 0 6 ? * MON',misfire_policy='3',concurrent='1',
    update_by='SYSTEM',update_time=NOW(),
    remark='每周一北京时间06:00；page=1起逐页/page_size=200；只覆盖latest单批库龄表，不触发月度成本链。JVM时区须Asia/Shanghai；错过时间不补跑。'
WHERE invoke_target IN ('operationSyncTask.syncGoodcangInventoryAgeLatest',
                        'operationSyncTask.syncGoodcangInventoryAgeLatest()');

INSERT INTO `sys_job` (job_name,job_group,invoke_target,cron_expression,
    misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '谷仓-eBay库存库龄每周刷新','DATA_CENTER',
       'operationSyncTask.syncGoodcangInventoryAgeLatest()','0 0 6 ? * MON',
       '3','1','0','SYSTEM',NOW(),
       '每周一北京时间06:00；page=1起逐页/page_size=200；只覆盖latest单批库龄表，不触发月度成本链。JVM时区须Asia/Shanghai；错过时间不补跑。'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job`
    WHERE invoke_target IN ('operationSyncTask.syncGoodcangInventoryAgeLatest',
                            'operationSyncTask.syncGoodcangInventoryAgeLatest()'));
COMMIT;

SELECT job_id,job_name,invoke_target,cron_expression,status
FROM `sys_job`
WHERE invoke_target IN ('operationSyncTask.syncGoodcangInventoryAgeLatest()',
    'operationSyncTask.syncGoodcangInventoryAge()',
    'pythonFbaInventoryTask.syncCurrentMonth()') ORDER BY job_id;

SELECT COUNT(*) latest_rows,COUNT(DISTINCT sync_batch_id) batches,
       MIN(pulled_at) earliest_pulled_at,MAX(pulled_at) latest_pulled_at
FROM `ods_goodcang_inventory_age_latest`;
