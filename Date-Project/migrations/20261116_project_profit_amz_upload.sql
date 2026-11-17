-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- Finance center "project profit statement": the AMZ columns now come from the LingXing "profit report - MSKU"
-- file that finance exports by hand (settlement, monthly, currency CNY) and uploads on the page, instead of the
-- API pull. The API export loses part of the cost detail (removal / transit loss ...), the hand export does not.
-- Only this statement reads these tables; the AMZ monthly profit statement keeps reading the API pulled
-- ods_lingxing_profit_report_msku_month, which is not touched.
--   fin_project_profit_amz_msku    one row per month / store / MSKU, the same columns the statement used before
--                                  (sums of the file columns, see project_profit_service.AMZ_FILE_COLUMNS).
--   fin_project_profit_amz_upload  the last file uploaded for each month (file name, who, check figures).
-- Only creates the two tables; idempotent, changes nothing else.
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fin_project_profit_amz_msku` (
  `stat_month` CHAR(7) NOT NULL COMMENT 'settlement month YYYY-MM',
  `store_name` VARCHAR(128) NOT NULL COMMENT 'LingXing store name, e.g. EU-xxx-DE',
  `msku` VARCHAR(200) COLLATE utf8mb4_bin NOT NULL COMMENT 'MSKU; store level allocations use -',
  `local_sku` VARCHAR(200) NULL,
  `local_name` VARCHAR(500) NULL,
  `currency_code` VARCHAR(8) NOT NULL DEFAULT 'CNY',
  `sales_qty` INT NOT NULL DEFAULT 0,
  `refunds_qty` INT NOT NULL DEFAULT 0,
  `returns_qty` INT NOT NULL DEFAULT 0,
  `sales_amount` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `shipping_credits` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `promotional_rebates` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `fba_inventory_credit` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `cash_on_delivery` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `other_in_amount` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `sales_refunds` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `fee_refunds` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `platform_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `fba_delivery_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `other_transaction_fees` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `ads_cost` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `promotion_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `storage_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `inbound_convenience_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `international_inbound_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `adjustment_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `platform_other_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `custom_order_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `sales_tax` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `sales_tax_refund` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `market_tax` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `market_tax_refund` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `purchase_cost` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `first_leg_cost` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `other_cost` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `gross_profit` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `removal_cost` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'FBA removal purchase + logistics + other cost',
  `transit_loss` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'FBA transit loss back + shipment transit loss, purchase + logistics + other cost',
  `other_fees_json` JSON NULL COMMENT 'custom fee columns by name (except off-site promotion = custom_order_fee)',
  `uploaded_at` DATETIME NOT NULL,
  PRIMARY KEY (`stat_month`, `store_name`, `msku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Project profit statement: uploaded LingXing profit report MSKU (CNY); whole month replaced per upload';

CREATE TABLE IF NOT EXISTS `fin_project_profit_amz_upload` (
  `stat_month` CHAR(7) NOT NULL,
  `file_name` VARCHAR(255) NOT NULL,
  `uploaded_by` VARCHAR(64) NULL,
  `uploaded_at` DATETIME NOT NULL,
  `check_json` JSON NULL COMMENT 'row count and totals read from the file',
  PRIMARY KEY (`stat_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Project profit statement: last LingXing profit report MSKU file uploaded per month';
