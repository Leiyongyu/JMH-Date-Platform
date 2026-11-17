-- AMZ补货新增产品性质：listing保存商品创建日期，补货快照按最近60天计算新品/老品。可重复执行。
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_product_listing'
     AND COLUMN_NAME = 'listing_create_date') = 0,
  'ALTER TABLE amz_product_listing ADD COLUMN listing_create_date DATE NULL COMMENT ''商品创建日期，来自领星open_date_display前10位'' AFTER price',
  'SELECT ''skip amz_product_listing.listing_create_date'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_replenishment_snapshot'
     AND COLUMN_NAME = 'product_nature') = 0,
  'ALTER TABLE amz_replenishment_snapshot ADD COLUMN product_nature TINYINT NULL DEFAULT 1 COMMENT ''产品性质：1老品，2新品；按listing_create_date距离当前日期60天计算'' AFTER product_category',
  'SELECT ''skip amz_replenishment_snapshot.product_nature'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'amz_replenishment_snapshot'
     AND INDEX_NAME = 'idx_amz_repl_product_nature') = 0,
  'ALTER TABLE amz_replenishment_snapshot ADD INDEX idx_amz_repl_product_nature (product_nature)',
  'SELECT ''skip idx_amz_repl_product_nature'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
