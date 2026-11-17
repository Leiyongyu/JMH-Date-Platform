-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk);
-- Chinese values are written as UTF-8 hex literals.
-- eBay monthly profit statement (finance center):
--   ods_ebay_finance_transaction        eBay Finances transactions per store, split per order line, PT month
--   ods_goodcang_bill_fee               GoodCang bill fee lines (account ACG1064502), month = bill_to month
--   fin_ebay_monthly_profit_rate        Bank of China average conversion rate per month, entered by finance
--   fin_ebay_monthly_profit_adjustment  hand entered supplementary items
-- Registers the two monthly pull tasks (7th 05:00 GoodCang bills, 05:30 eBay transactions; AMZ runs 06:00).
-- Only creates tables and registers tasks; idempotent, changes nothing else.
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ods_ebay_finance_transaction` (
  `stat_month` CHAR(7) NOT NULL COMMENT 'natural month in America/Los_Angeles, same as Seller Hub report',
  `store_name` VARCHAR(128) NOT NULL,
  `transaction_id` VARCHAR(64) NOT NULL,
  `line_no` INT NOT NULL COMMENT 'order line index; 1 for single line transactions',
  `transaction_type` VARCHAR(32) NULL COMMENT 'SALE / REFUND / CREDIT / DISPUTE / NON_SALE_CHARGE / ...',
  `transaction_status` VARCHAR(40) NULL,
  `booking_entry` VARCHAR(16) NULL COMMENT 'CREDIT / DEBIT',
  `category` VARCHAR(24) NOT NULL COMMENT 'ORDER/REFUND/CLAIM/PAYMENT_DISPUTE/HOLD/AD_FEE/LISTING_FEE/SHIPPING_LABEL/ADJUSTMENT/OTHER',
  `transaction_time_utc` DATETIME NULL,
  `transaction_date_pt` DATE NULL,
  `order_id` VARCHAR(64) NULL,
  `payout_id` VARCHAR(64) NULL,
  `fee_type` VARCHAR(64) NULL,
  `memo` VARCHAR(500) NULL,
  `reference_text` VARCHAR(500) NULL COMMENT 'TYPE:ID;TYPE:ID',
  `line_item_id` VARCHAR(64) NULL,
  `item_id` VARCHAR(64) NULL,
  `sku` VARCHAR(200) NULL,
  `title` VARCHAR(500) NULL,
  `quantity` INT NULL,
  `payout_currency` VARCHAR(8) NULL,
  `net_amount` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'signed net in payout currency (USD)',
  `tx_currency` VARCHAR(8) NULL,
  `fx_rate` DECIMAL(18,8) NOT NULL DEFAULT 1 COMMENT 'transaction currency -> payout currency, as applied by eBay',
  `gross_amount` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'signed gross in transaction currency (item subtotal + shipping)',
  `fvf_fixed` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `fvf_variable` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `regulatory_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `international_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `inad_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `below_standard_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `other_line_fee` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `ebay_tax` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `sync_batch_id` VARCHAR(64) NOT NULL,
  `pulled_at` DATETIME NOT NULL,
  PRIMARY KEY (`stat_month`, `store_name`, `transaction_id`, `line_no`),
  KEY `idx_ebay_finance_tx_order` (`stat_month`, `order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='eBay Finances transactions for the eBay monthly profit statement; replaced per store and month';

CREATE TABLE IF NOT EXISTS `ods_goodcang_bill_fee` (
  `stat_month` CHAR(7) NOT NULL COMMENT 'month of bill_to',
  `bill_number` VARCHAR(32) NOT NULL,
  `sheet_name` VARCHAR(32) NOT NULL,
  `row_no` INT NOT NULL,
  `account_code` VARCHAR(20) NULL,
  `bill_from` VARCHAR(20) NULL,
  `bill_to` VARCHAR(20) NULL,
  `fee_type` VARCHAR(32) NULL COMMENT 'inbound / storage / outbound / return / value added / claim',
  `fee_detail` VARCHAR(64) NULL,
  `business_type` VARCHAR(32) NULL,
  `business_no` VARCHAR(128) NULL,
  `related_no` VARCHAR(255) NULL COMMENT 'platform order number for outbound fees; returns may carry long label text',
  `tracking_no` VARCHAR(255) NULL,
  `warehouse_code` VARCHAR(16) NULL,
  `sku` VARCHAR(200) NULL,
  `platform` VARCHAR(32) NULL,
  `currency` VARCHAR(8) NULL,
  `amount` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'subtotal of the period, positive = cost',
  `charge_time` VARCHAR(20) NULL,
  `remark` VARCHAR(500) NULL,
  `sync_batch_id` VARCHAR(64) NOT NULL,
  `pulled_at` DATETIME NOT NULL,
  PRIMARY KEY (`stat_month`, `bill_number`, `sheet_name`, `row_no`),
  KEY `idx_goodcang_bill_fee_related` (`stat_month`, `related_no`(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='GoodCang bill fee lines for the eBay monthly profit statement; replaced per month';

CREATE TABLE IF NOT EXISTS `fin_ebay_monthly_profit_rate` (
  `stat_month` CHAR(7) NOT NULL,
  `currency_code` CHAR(3) NOT NULL,
  `rate` DECIMAL(12,6) NOT NULL COMMENT 'CNY per 1 unit, Bank of China average conversion rate',
  `updated_by` VARCHAR(64) NULL,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`stat_month`, `currency_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Bank of China monthly average rates entered for the eBay monthly profit statement';

CREATE TABLE IF NOT EXISTS `fin_ebay_monthly_profit_adjustment` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `stat_month` CHAR(7) NOT NULL,
  `row_code` VARCHAR(64) NOT NULL COMMENT 'ALL / US / DE / UK / owner name',
  `fee_item` VARCHAR(32) NOT NULL COMMENT 'statement column the amount goes to',
  `amount` DECIMAL(18,2) NOT NULL COMMENT 'CNY; costs negative, income positive',
  `remark` VARCHAR(255) NULL,
  `created_by` VARCHAR(64) NULL,
  `updated_by` VARCHAR(64) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ebay_monthly_profit_adj_month` (`stat_month`, `row_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Hand entered supplementary items of the eBay monthly profit statement';

INSERT INTO `scheduler_task` (`task_code`, `task_name`, `cron_expression`, `enabled`, `description`)
VALUES ('goodcang_bill_monthly_sync',
        CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A82DE8B0B7E4BB93E8B4A6E58D95E68B89E58F96' USING utf8mb4),
        '0 0 5 7 * ?', 1,
        CONVERT(X'E6AF8FE69C8837E697A530353A3030E68B89E58F96E4B88AE4B8AAE69C88E8B0B7E4BB9365426179E8B4A6E688B7284143473130363435303229E79A84E8B4A6E58D95E8B4B9E794A8E6988EE7BB86EFBC88E5B0BEE7A88BE38081E4BB93E582A8E7AD89EFBC89EFBC8CE68C89E69C88E695B4E69C88E69BBFE68DA2' USING utf8mb4)),
       ('ebay_finance_monthly_sync',
        CONVERT(X'65426179E69C88E5BAA6E588A9E6B6A6E8A1A82DE4BAA4E69893E6B581E6B0B4E68B89E58F96' USING utf8mb4),
        '0 30 5 7 * ?', 1,
        CONVERT(X'E6AF8FE69C8837E697A530353A3330E68B89E58F96E4B88AE4B8AAE69C88E585A8E983A865426179E5BA97E993BAE79A8446696E616E636573E4BAA4E69893E6B581E6B0B4EFBC88E5A4AAE5B9B3E6B48BE697B6E997B4E58887E69C88EFBC89EFBC8CE68C89E5BA97E993BAE695B4E69C88E69BBFE68DA2' USING utf8mb4))
ON DUPLICATE KEY UPDATE `task_name`=VALUES(`task_name`), `cron_expression`=VALUES(`cron_expression`),
  `description`=VALUES(`description`);
