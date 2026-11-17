-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- eBay "Friday data" / order sales statistics: the order export of the ERP (Shuzi Qiuzhang, transaction level) is
-- uploaded by hand on the page; only eBay rows with an inventory SKU are kept, one row per order line. Only the latest
-- upload is kept (each upload replaces the previous one, no history). The pivot (per owner: distinct mid code + site,
-- USD income, quantity) is computed on read with the current owner rules and LingXing monthly USD rate.
-- Only creates the two tables; idempotent, changes nothing else.
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ebay_friday_order_upload` (
  `id` TINYINT NOT NULL DEFAULT 1 COMMENT 'always 1: only the latest upload is kept',
  `file_name` VARCHAR(255) NOT NULL,
  `uploaded_by` VARCHAR(64) NULL,
  `uploaded_at` DATETIME NOT NULL,
  `pay_time_from` DATETIME NULL,
  `pay_time_to` DATETIME NULL,
  `source_rows` INT NOT NULL DEFAULT 0 COMMENT 'data rows in the file',
  `used_rows` INT NOT NULL DEFAULT 0 COMMENT 'eBay rows with an inventory SKU',
  `excluded_json` JSON NULL COMMENT 'reason -> row count',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay Friday order sales: latest upload';

CREATE TABLE IF NOT EXISTS `ebay_friday_order_line` (
  `row_no` INT NOT NULL,
  `order_no` VARCHAR(64) NOT NULL,
  `ship_status` VARCHAR(64) NULL,
  `pay_time` DATETIME NULL,
  `currency` VARCHAR(8) NULL,
  `order_rate` DECIMAL(18,6) NULL COMMENT 'CNY per 1 unit of the order currency, as exported',
  `income` DECIMAL(18,4) NULL COMMENT 'income in the order currency',
  `quantity` INT NOT NULL DEFAULT 0,
  `stock_sku` VARCHAR(255) NOT NULL,
  `brand` VARCHAR(32) NULL,
  `mid_code` VARCHAR(32) NULL,
  `site` CHAR(2) NULL COMMENT 'USD -> US, EUR -> DE, others -> UK',
  PRIMARY KEY (`row_no`),
  KEY `idx_sku` (`stock_sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay Friday order sales: order lines';
