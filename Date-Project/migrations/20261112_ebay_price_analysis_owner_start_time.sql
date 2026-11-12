-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- Adds two nullable columns to dws_ebay_price_analysis:
--   owner_name          eBay owner of the SKU (same brand rules as performance / monthly inventory);
--                       NULL when the listing has no SKU or no eBay owner rule exists yet
--   listing_start_time  listing start time (ListingDetails/StartTime) converted to Beijing time;
--                       the eBay selling API does not return a price-revision time
-- Idempotent: MySQL ADD COLUMN has no IF NOT EXISTS, so each column is checked in
-- information_schema first. Only adds columns; no existing column is changed or dropped.
-- Values are written by the next ebay_price_analysis_refresh run (whole-table replace).
USE `date-project`;
SET NAMES utf8mb4;

SET @has_owner_name := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_ebay_price_analysis'
      AND column_name = 'owner_name'
);
SET @ddl_owner_name := IF(
    @has_owner_name = 0,
    'ALTER TABLE `dws_ebay_price_analysis` ADD COLUMN `owner_name` VARCHAR(64) NULL COMMENT ''eBay owner by SKU brand rule; NULL when no SKU or no rule'' AFTER `status`',
    'SELECT 1'
);
PREPARE stmt_owner_name FROM @ddl_owner_name;
EXECUTE stmt_owner_name;
DEALLOCATE PREPARE stmt_owner_name;

SET @has_listing_start_time := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'dws_ebay_price_analysis'
      AND column_name = 'listing_start_time'
);
SET @ddl_listing_start_time := IF(
    @has_listing_start_time = 0,
    'ALTER TABLE `dws_ebay_price_analysis` ADD COLUMN `listing_start_time` DATETIME NULL COMMENT ''listing start time, Beijing time; NULL when the API value is missing'' AFTER `owner_name`',
    'SELECT 1'
);
PREPARE stmt_listing_start_time FROM @ddl_listing_start_time;
EXECUTE stmt_listing_start_time;
DEALLOCATE PREPARE stmt_listing_start_time;
