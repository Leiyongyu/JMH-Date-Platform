-- eBay补货2.0查询优化：为“站点+MSKU最早刊登时间”增加覆盖索引。
-- 幂等执行，不删除、不覆盖任何业务数据。
SET NAMES utf8mb4;
USE `jmh_data_platform`;

SET @index_exists = (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = 'jmh_data_platform'
    AND TABLE_NAME = 'ebay_product_listing'
    AND INDEX_NAME = 'idx_site_msku_start'
);
SET @index_sql = IF(
  @index_exists = 0,
  'ALTER TABLE `jmh_data_platform`.`ebay_product_listing` ADD INDEX `idx_site_msku_start` (`site_name`,`msku`,`listing_start_time`)',
  'SELECT ''idx_site_msku_start already exists'''
);
PREPARE index_stmt FROM @index_sql;
EXECUTE index_stmt;
DEALLOCATE PREPARE index_stmt;
