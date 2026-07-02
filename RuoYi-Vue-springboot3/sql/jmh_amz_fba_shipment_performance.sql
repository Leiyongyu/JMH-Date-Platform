-- AMZ FBA货件页面性能优化索引
-- 可重复执行：索引已存在时会跳过。
-- 用途：
-- 1. 降低 FBA货件列表默认按创建时间倒序分页的排序成本。
-- 2. 降低店铺名称关联筛选的 join 成本。
-- 3. 降低已完结标记关联筛选的 join 成本。

SET @schema_name = DATABASE();

SET @sql = IF(
    (SELECT COUNT(1) FROM information_schema.statistics
     WHERE table_schema = @schema_name AND table_name = 'amz_fba_shipment'
       AND index_name = 'idx_amz_fba_shipment_gmt_create') = 0,
    'CREATE INDEX idx_amz_fba_shipment_gmt_create ON amz_fba_shipment (gmt_create, shipment_id, sku)',
    'SELECT ''idx_amz_fba_shipment_gmt_create exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(1) FROM information_schema.statistics
     WHERE table_schema = @schema_name AND table_name = 'shop_list'
       AND index_name = 'idx_shop_list_platform_sid') = 0,
    'CREATE INDEX idx_shop_list_platform_sid ON shop_list (platform_code, sid)',
    'SELECT ''idx_shop_list_platform_sid exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(1) FROM information_schema.statistics
     WHERE table_schema = @schema_name AND table_name = 'amz_fba_shipment_mark'
       AND index_name = 'idx_amz_fba_shipment_mark_msku_shipment') = 0,
    'CREATE INDEX idx_amz_fba_shipment_mark_msku_shipment ON amz_fba_shipment_mark (msku, shipment_id)',
    'SELECT ''idx_amz_fba_shipment_mark_msku_shipment exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
