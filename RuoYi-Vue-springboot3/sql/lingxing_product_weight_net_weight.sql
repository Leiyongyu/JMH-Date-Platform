-- 领星产品管理：保存产品净重（接口字段 cg_product_net_weight，单位 G）。
-- 可重复执行。

SET @has_col := (
    SELECT COUNT(1)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'lingxing_product_weight'
      AND column_name = 'net_weight'
);

SET @sql := IF(
    @has_col = 0,
    'ALTER TABLE lingxing_product_weight ADD COLUMN net_weight DECIMAL(12,4) NULL COMMENT ''产品净重G'' AFTER gross_weight',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
