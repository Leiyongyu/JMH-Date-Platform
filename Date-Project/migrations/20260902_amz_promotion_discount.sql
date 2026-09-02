-- AMZ绩效利润补充领星OrderProfit促销折扣原值。
-- 可重复执行；历史值保持0，需由后续指定月份接口同步覆盖。

SET @has_ods_amz_promotion_discount := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'ods_lingxing_amz_order_profit_raw'
      AND column_name = 'promotion_discount'
);
SET @ddl_ods_amz_promotion_discount := IF(
    @has_ods_amz_promotion_discount = 0,
    'ALTER TABLE `ods_lingxing_amz_order_profit_raw` ADD COLUMN `promotion_discount` DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''促销折扣；领星OrderProfit接口promotion_discount原值，通常为负数'' AFTER `refund_amount`',
    'SELECT 1'
);
PREPARE stmt_ods_amz_promotion_discount FROM @ddl_ods_amz_promotion_discount;
EXECUTE stmt_ods_amz_promotion_discount;
DEALLOCATE PREPARE stmt_ods_amz_promotion_discount;

SET @has_dwd_amz_promotion_discount := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dwd_amz_monthly_order_profit'
      AND column_name = 'promotion_discount'
);
SET @ddl_dwd_amz_promotion_discount := IF(
    @has_dwd_amz_promotion_discount = 0,
    'ALTER TABLE `dwd_amz_monthly_order_profit` ADD COLUMN `promotion_discount` DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''促销折扣；领星原值，通常为负数'' AFTER `refund_amount`',
    'SELECT 1'
);
PREPARE stmt_dwd_amz_promotion_discount FROM @ddl_dwd_amz_promotion_discount;
EXECUTE stmt_dwd_amz_promotion_discount;
DEALLOCATE PREPARE stmt_dwd_amz_promotion_discount;

SET @has_dws_amz_promotion_discount := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_amz_performance_ranking'
      AND column_name = 'promotion_discount'
);
SET @ddl_dws_amz_promotion_discount := IF(
    @has_dws_amz_promotion_discount = 0,
    'ALTER TABLE `dws_amz_performance_ranking` ADD COLUMN `promotion_discount` DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT ''促销折扣合计；用于核对净销售额'' AFTER `refund_amount`',
    'SELECT 1'
);
PREPARE stmt_dws_amz_promotion_discount FROM @ddl_dws_amz_promotion_discount;
EXECUTE stmt_dws_amz_promotion_discount;
DEALLOCATE PREPARE stmt_dws_amz_promotion_discount;

SELECT table_name, column_name, column_type, column_default, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN (
      'ods_lingxing_amz_order_profit_raw',
      'dwd_amz_monthly_order_profit',
      'dws_amz_performance_ranking'
  )
  AND column_name = 'promotion_discount'
ORDER BY table_name;
