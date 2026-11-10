-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- Adds two nullable columns to dws_ebay_price_analysis for the "why not matched" reason:
--   unmatched_reason       reason code, NULL when the listing is matched
--   unmatched_reason_text  page text,   NULL when the listing is matched
-- Idempotent: MySQL ADD COLUMN has no IF NOT EXISTS, so each column is checked in
-- information_schema first. Only adds columns; no existing column is changed or dropped.
-- Values are written by the next ebay_price_analysis_refresh run (whole-table replace).
USE `date-project`;
SET NAMES utf8mb4;

SET @has_unmatched_reason := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_ebay_price_analysis'
      AND column_name = 'unmatched_reason'
);
SET @ddl_unmatched_reason := IF(
    @has_unmatched_reason = 0,
    'ALTER TABLE `dws_ebay_price_analysis` ADD COLUMN `unmatched_reason` VARCHAR(32) NULL COMMENT ''unmatched reason code; NULL when matched'' AFTER `inventory_matched`',
    'SELECT 1'
);
PREPARE stmt_unmatched_reason FROM @ddl_unmatched_reason;
EXECUTE stmt_unmatched_reason;
DEALLOCATE PREPARE stmt_unmatched_reason;

SET @has_unmatched_reason_text := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_ebay_price_analysis'
      AND column_name = 'unmatched_reason_text'
);
SET @ddl_unmatched_reason_text := IF(
    @has_unmatched_reason_text = 0,
    'ALTER TABLE `dws_ebay_price_analysis` ADD COLUMN `unmatched_reason_text` VARCHAR(255) NULL COMMENT ''unmatched reason text for the page; NULL when matched'' AFTER `unmatched_reason`',
    'SELECT 1'
);
PREPARE stmt_unmatched_reason_text FROM @ddl_unmatched_reason_text;
EXECUTE stmt_unmatched_reason_text;
DEALLOCATE PREPARE stmt_unmatched_reason_text;
