-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- Project profit statement: store the LingXing file's own "platform expense" total per MSKU row. Since the
-- 2026-10 finance sheet the AMZ platform expense is this column (it leaves out the net sales / market tax and the
-- multi-channel FBA fee) instead of the sum of the fee columns.
-- Adds one nullable column to fin_project_profit_amz_msku; NULL on rows uploaded before this migration, which
-- keep using the sum of the fee columns until the month is uploaded again.
-- Idempotent: MySQL ADD COLUMN has no IF NOT EXISTS, so the column is checked in information_schema first.
-- Only adds the column; nothing else is changed.
USE `date-project`;
SET NAMES utf8mb4;

SET @has_platform_expense := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'fin_project_profit_amz_msku'
      AND column_name = 'platform_expense'
);
SET @ddl_platform_expense := IF(
    @has_platform_expense = 0,
    'ALTER TABLE `fin_project_profit_amz_msku` ADD COLUMN `platform_expense` DECIMAL(18,4) NULL COMMENT ''LingXing file column platform expense total; NULL = uploaded before this column existed'' AFTER `transit_loss`',
    'SELECT 1'
);
PREPARE stmt_platform_expense FROM @ddl_platform_expense;
EXECUTE stmt_platform_expense;
DEALLOCATE PREPARE stmt_platform_expense;
