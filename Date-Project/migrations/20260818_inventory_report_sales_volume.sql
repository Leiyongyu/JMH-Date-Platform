-- 目标库：Date-Project（Python 数据库）。不要在 jmh_data_platform 执行。
-- 月度库存实际达成及销量：Amazon订单利润amount、volume落库，并注册每月11日23:00拉取上月数据的填充任务。

SET @has_ods_volume := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'ods_lingxing_inventory_report_amz_order_profit'
      AND column_name = 'volume'
);
SET @ddl_ods_volume := IF(
    @has_ods_volume = 0,
    'ALTER TABLE `ods_lingxing_inventory_report_amz_order_profit` ADD COLUMN `volume` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT ''自然月商品销量'' AFTER `amount`',
    'SELECT 1'
);
PREPARE stmt_ods_volume FROM @ddl_ods_volume;
EXECUTE stmt_ods_volume;
DEALLOCATE PREPARE stmt_ods_volume;

SET @has_dwd_volume := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dwd_inventory_report_amz_sales_detail'
      AND column_name = 'volume'
);
SET @ddl_dwd_volume := IF(
    @has_dwd_volume = 0,
    'ALTER TABLE `dwd_inventory_report_amz_sales_detail` ADD COLUMN `volume` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT ''清洗后自然月商品销量'' AFTER `amount`',
    'SELECT 1'
);
PREPARE stmt_dwd_volume FROM @ddl_dwd_volume;
EXECUTE stmt_dwd_volume;
DEALLOCATE PREPARE stmt_dwd_volume;

INSERT INTO `scheduler_task` (
    task_code, task_name, cron_expression, enabled, description
) VALUES (
    'monthly_inventory_report_sales_volume_sync',
    '月度库存实际达成及销量填充',
    '0 0 23 11 * ?',
    1,
    '每月11日23:00一次拉取上个完整自然月Amazon订单利润amount和volume并覆盖ODS、重建实际达成及销量DWD；eBay销量由jmh_data_platform.ebay_sales按payment_time实时汇总quantity'
)
ON DUPLICATE KEY UPDATE
    task_name = VALUES(task_name),
    cron_expression = VALUES(cron_expression),
    description = VALUES(description);

SELECT table_name,column_name,column_type,column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND (
      (table_name = 'ods_lingxing_inventory_report_amz_order_profit' AND column_name = 'volume')
      OR
      (table_name = 'dwd_inventory_report_amz_sales_detail' AND column_name = 'volume')
  );
