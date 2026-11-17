USE `jmh_data_platform`;

-- 记录每条仓租明细实际采用的领星汇率月份；只加字段，不更新或删除历史数据。
SET @rent_rate_month_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'ebay_replenishment_v2_warehouse_rent_detail'
    AND column_name = 'exchange_rate_month'
);
SET @rent_rate_month_sql = IF(
  @rent_rate_month_exists = 0,
  'ALTER TABLE ebay_replenishment_v2_warehouse_rent_detail ADD COLUMN exchange_rate_month VARCHAR(7) NULL COMMENT ''所用汇率月份，当月缺失时记录回退月份'' AFTER exchange_rate',
  'SELECT 1'
);
PREPARE rent_rate_month_statement FROM @rent_rate_month_sql;
EXECUTE rent_rate_month_statement;
DEALLOCATE PREPARE rent_rate_month_statement;
