-- 目标库：Date-Project（Python 数据库）。不要在 jmh_data_platform 执行。
-- 月度库存采购单本地仓在途源表；每次上传文件时全表替换。

CREATE TABLE IF NOT EXISTS `ods_inventory_report_purchase_order_transit` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '月度库存源数据归属年月，格式YYYY-MM',
    `purchase_order_no` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '采购单号',
    `purchase_warehouse` VARCHAR(255) NOT NULL COMMENT '采购仓库，已向下填充合并单元格',
    `purchase_warehouse_detail` VARCHAR(255) NOT NULL COMMENT '采购仓库明细，优先取Excel采购仓库（明细）列',
    `sku` VARCHAR(255) NOT NULL COMMENT '商品SKU',
    `store_name` VARCHAR(255) NULL COMMENT 'Excel店铺名称',
    `unit_price` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '采购单价',
    `pending_arrival_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '待到货数量',
    `sku_pending_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'SKU待到货总成本，单价乘以待到货数量',
    `product_dimension` VARCHAR(255) NULL COMMENT '产品维度',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `group_code` VARCHAR(32) NOT NULL COMMENT '采购仓库归属组别：EBAY-1、EU、US1、US2或US3',
    `department_code` VARCHAR(32) NOT NULL COMMENT '月度库存汇总部门编码；US3落AMZ-US2-MJ并在页面合并显示',
    `source_file_name` VARCHAR(255) NOT NULL COMMENT '上传的原始文件名',
    `source_sheet` VARCHAR(128) NOT NULL COMMENT 'Excel来源工作表名称',
    `source_row` INT NOT NULL COMMENT 'Excel来源行号',
    `import_batch_id` VARCHAR(64) NOT NULL COMMENT '本次全量替换导入批次ID',
    `imported_by` VARCHAR(64) NULL COMMENT '上传操作人',
    `imported_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导入时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_purchase_order_batch_row` (`import_batch_id`,`source_row`),
    KEY `idx_inventory_purchase_order_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_purchase_order_month_warehouse` (`stat_month`,`purchase_warehouse_detail`),
    KEY `idx_inventory_purchase_order_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-月度库存采购单本地仓在途明细，每次上传全表替换';
