-- 报关单制作: 新增箱号/箱组标识字段
-- 可重复执行; 仅新增列, 不删除数据

SET @has_customs_box_no := (
    SELECT COUNT(1) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'customs_products_list'
      AND column_name = 'box_no'
);
SET @sql := IF(@has_customs_box_no = 0,
    'ALTER TABLE customs_products_list ADD COLUMN box_no varchar(100) DEFAULT NULL COMMENT ''箱号/箱组标识'' AFTER box_height',
    'SELECT ''customs_products_list.box_no already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_fba_box_no := (
    SELECT COUNT(1) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'amz_fba_shipment_box'
      AND column_name = 'box_no'
);
SET @sql := IF(@has_fba_box_no = 0,
    'ALTER TABLE amz_fba_shipment_box ADD COLUMN box_no varchar(100) DEFAULT NULL COMMENT ''箱号'' AFTER box_num',
    'SELECT ''amz_fba_shipment_box.box_no already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
