-- 目标库：Date-Project（Python 数据库）。不要在 jmh_data_platform 执行。
-- 月度库存统计新增Amazon订单利润源数据、清洗明细、实际达成和目标达成率。

CREATE TABLE IF NOT EXISTS `ods_lingxing_inventory_report_amz_order_profit` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `sid` VARCHAR(32) NOT NULL COMMENT '领星Amazon店铺SID',
    `msku` VARCHAR(255) NOT NULL COMMENT 'Amazon卖家SKU（MSKU）',
    `local_sku` VARCHAR(255) NULL COMMENT '本地商品SKU',
    `asin` VARCHAR(64) NULL COMMENT 'Amazon商品标识码（ASIN）',
    `item_name` TEXT NULL COMMENT '商品名称',
    `currency_code` VARCHAR(16) NOT NULL DEFAULT 'CNY' COMMENT '销售额币种，本链路固定请求CNY',
    `amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '上个自然月销售额',
    `volume` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '自然月商品销量',
    `pulled_at` DATETIME NOT NULL COMMENT '数据拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_amz_profit_month_sid_msku` (`stat_month`,`sid`,`msku`),
    KEY `idx_inventory_amz_profit_month_local_sku` (`stat_month`,`local_sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-月度库存统计使用的领星Amazon订单利润最小字段快照';

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

-- 已执行过旧版本脚本的环境，删除不参与业务清洗和汇总的接口技术字段。
SELECT GROUP_CONCAT(
           CONCAT('DROP COLUMN `', column_name, '`')
           ORDER BY ordinal_position SEPARATOR ', '
       )
INTO @ods_unused_columns
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'ods_lingxing_inventory_report_amz_order_profit'
  AND column_name IN (
      'sync_batch_id', 'query_start_date', 'query_end_date',
      'source_page', 'source_offset', 'source_row_no',
      'api_request_id', 'api_response_time', 'api_total'
  );
SET @ddl_drop_ods_unused := IF(
    @ods_unused_columns IS NULL,
    'SELECT 1',
    CONCAT(
        'ALTER TABLE `ods_lingxing_inventory_report_amz_order_profit` ',
        @ods_unused_columns
    )
);
PREPARE stmt_drop_ods_unused FROM @ddl_drop_ods_unused;
EXECUTE stmt_drop_ods_unused;
DEALLOCATE PREPARE stmt_drop_ods_unused;

SET @has_dwd_sync_batch := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dwd_inventory_report_amz_sales_detail'
      AND column_name = 'sync_batch_id'
);
SET @ddl_drop_dwd_sync_batch := IF(
    @has_dwd_sync_batch > 0,
    'ALTER TABLE `dwd_inventory_report_amz_sales_detail` DROP COLUMN `sync_batch_id`',
    'SELECT 1'
);
PREPARE stmt_drop_dwd_sync_batch FROM @ddl_drop_dwd_sync_batch;
EXECUTE stmt_drop_dwd_sync_batch;
DEALLOCATE PREPARE stmt_drop_dwd_sync_batch;

SET @has_actual_achievement := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_inventory_report_department_summary'
      AND column_name = 'actual_achievement_amount'
);
SET @ddl_actual_achievement := IF(
    @has_actual_achievement = 0,
    'ALTER TABLE `dws_inventory_report_department_summary` ADD COLUMN `actual_achievement_amount` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT ''实际达成销售额，Amazon订单利润按部门汇总，币种CNY'' AFTER `fba_end_in_transit_total_cost`',
    'SELECT 1'
);
PREPARE stmt_actual_achievement FROM @ddl_actual_achievement;
EXECUTE stmt_actual_achievement;
DEALLOCATE PREPARE stmt_actual_achievement;

SET @has_target_achievement_rate := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_inventory_report_department_summary'
      AND column_name = 'target_achievement_rate'
);
SET @ddl_target_achievement_rate := IF(
    @has_target_achievement_rate = 0,
    'ALTER TABLE `dws_inventory_report_department_summary` ADD COLUMN `target_achievement_rate` DECIMAL(24,10) NOT NULL DEFAULT 0 COMMENT ''目标达成率，实际达成除以销售冲刺目标'' AFTER `actual_achievement_amount`',
    'SELECT 1'
);
PREPARE stmt_target_achievement_rate FROM @ddl_target_achievement_rate;
EXECUTE stmt_target_achievement_rate;
DEALLOCATE PREPARE stmt_target_achievement_rate;

UPDATE `scheduler_task`
SET `task_name` = '月度库存统计表数据拉取',
    `description` = '每月1日拉取上个完整自然月FBA、海外仓、本地仓三个库存接口并按月份覆盖ODS，作为下一个业务月报表库存基准；Amazon订单利润由每月2日06:00任务拉取上月数据'
WHERE `task_code` = 'monthly_inventory_report_source_sync';

SELECT table_name, table_comment
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'ods_lingxing_inventory_report_amz_order_profit',
      'dwd_inventory_report_amz_sales_detail',
      'dws_inventory_report_department_summary'
  )
ORDER BY table_name;
