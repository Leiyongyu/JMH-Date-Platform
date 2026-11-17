USE `jmh_data_platform`;

-- 覆盖键调整为“仓库+商品编码+账单日”。只新增查询索引，不删除或改写现有数据。
SET @rent_cover_index_exists = (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'ebay_replenishment_v2_warehouse_rent_detail'
    AND index_name = 'idx_ebay_replenishment_v2_rent_detail_warehouse_product_billing'
);
SET @rent_cover_index_sql = IF(
  @rent_cover_index_exists = 0,
  'ALTER TABLE ebay_replenishment_v2_warehouse_rent_detail ADD INDEX idx_ebay_replenishment_v2_rent_detail_warehouse_product_billing (warehouse_code, product_code, billing_time_text)',
  'SELECT 1'
);
PREPARE rent_cover_index_statement FROM @rent_cover_index_sql;
EXECUTE rent_cover_index_statement;
DEALLOCATE PREPARE rent_cover_index_statement;

ALTER TABLE ebay_replenishment_v2_warehouse_rent_detail
  MODIFY COLUMN order_no VARCHAR(128) NULL COMMENT '仓租单号，仅用于来源追溯，不参与覆盖键',
  COMMENT = 'eBay补货2.0仓租明细Sheet结构化源数据，按仓库、商品编码和账单日增量覆盖';
