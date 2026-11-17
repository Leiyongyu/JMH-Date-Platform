-- 外部接口同步表统一同步时间字段
-- 作用：记录本系统最近一次通过接口新增/覆盖该行的时间，不覆盖源系统业务时间。
-- 可重复执行：表存在且字段不存在时才新增。

DROP PROCEDURE IF EXISTS add_column_if_not_exists;
DELIMITER $$
CREATE PROCEDURE add_column_if_not_exists(
    IN p_table_name VARCHAR(128),
    IN p_column_name VARCHAR(128),
    IN p_column_def TEXT
)
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = p_table_name
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = p_table_name
          AND column_name = p_column_name
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', p_table_name, '` ADD COLUMN `', p_column_name, '` ', p_column_def);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL add_column_if_not_exists('shop_list', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('warehouse', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('ebay_product_listing', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('warehouse_inventory_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('warehouse_statement', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('purchase_order', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('purchase_plan', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_product_listing', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_order_profit', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_restock_summary', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_product_performance_inventory', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_warehouse_inventory_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_fba_shipment', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('amz_fba_shipment_box', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_warehouse', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_product_info', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_grn_list', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('goodcang_grn_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('lingxing_product_weight', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('overseas_stock_order', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');
CALL add_column_if_not_exists('overseas_stock_order_detail', 'sync_time', 'datetime NULL DEFAULT NULL COMMENT ''本地最近同步时间''');

DROP PROCEDURE IF EXISTS add_column_if_not_exists;
