-- eBay绩效利润表补充“售出数”，统一供绩效排名和月度库存使用。
-- 可重复执行；旧文件重传时缺少“售出数”会按0保存，并由月度库存回退旧销量源。

SET @has_ods_ebay_sold_quantity := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'ods_ebay_monthly_profit_raw'
      AND column_name = 'sold_quantity'
);
SET @ddl_ods_ebay_sold_quantity := IF(
    @has_ods_ebay_sold_quantity = 0,
    'ALTER TABLE `ods_ebay_monthly_profit_raw` ADD COLUMN `sold_quantity` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT ''eBay售出数；来源利润表“售出数”列，作月度库存销量'' AFTER `multi_variant`',
    'SELECT 1'
);
PREPARE stmt_ods_ebay_sold_quantity FROM @ddl_ods_ebay_sold_quantity;
EXECUTE stmt_ods_ebay_sold_quantity;
DEALLOCATE PREPARE stmt_ods_ebay_sold_quantity;

SET @has_dwd_ebay_sold_quantity := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dwd_ebay_monthly_profit'
      AND column_name = 'sold_quantity'
);
SET @ddl_dwd_ebay_sold_quantity := IF(
    @has_dwd_ebay_sold_quantity = 0,
    'ALTER TABLE `dwd_ebay_monthly_profit` ADD COLUMN `sold_quantity` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT ''eBay售出数；来源利润表“售出数”列，作月度库存销量'' AFTER `multi_variant`',
    'SELECT 1'
);
PREPARE stmt_dwd_ebay_sold_quantity FROM @ddl_dwd_ebay_sold_quantity;
EXECUTE stmt_dwd_ebay_sold_quantity;
DEALLOCATE PREPARE stmt_dwd_ebay_sold_quantity;

UPDATE scheduler_task
SET description = '每月1日12:00拉取上个完整自然月Amazon订单利润amount和volume，覆盖ODS并重建实际达成及销量DWD；eBay实际达成和销量读取绩效利润表sales_amount及sold_quantity'
WHERE task_code = 'monthly_inventory_report_sales_volume_sync';

SELECT table_name, column_name, column_type, column_default, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN (
      'ods_ebay_monthly_profit_raw',
      'dwd_ebay_monthly_profit'
  )
  AND column_name = 'sold_quantity'
ORDER BY table_name;
