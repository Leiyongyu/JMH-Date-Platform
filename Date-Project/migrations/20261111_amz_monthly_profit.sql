-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk);
-- Chinese values are written as UTF-8 hex literals.
-- AMZ monthly profit statement (finance center): LingXing profit report (settlement basis) pulled monthly in CNY,
-- plus the hand entered supplementary fees. Sub-teams (US3 -> MJ / ZXY) follow the existing department rule in code.
-- Only creates tables and registers the scheduler task; idempotent, changes nothing else.
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ods_lingxing_profit_report_msku_month` (
  `stat_month` CHAR(7) NOT NULL COMMENT 'settlement month YYYY-MM',
  `sid` VARCHAR(32) NOT NULL COMMENT 'LingXing store id',
  `msku` VARCHAR(200) COLLATE utf8mb4_bin NOT NULL COMMENT 'MSKU; store level allocations use -',
  `store_name` VARCHAR(128) NULL COMMENT 'LingXing store name, e.g. EU-xxx-DE',
  `local_sku` VARCHAR(200) NULL,
  `local_name` VARCHAR(500) NULL,
  `currency_code` VARCHAR(8) NOT NULL DEFAULT 'CNY',
  `sales_qty` INT NOT NULL DEFAULT 0 COMMENT 'totalSalesQuantity',
  `refunds_qty` INT NOT NULL DEFAULT 0 COMMENT 'refundsQuantity',
  `returns_qty` INT NOT NULL DEFAULT 0 COMMENT 'fbaReturnsQuantity',
  `sales_amount` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalSalesAmount',
  `shipping_credits` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'shippingCredits',
  `promotional_rebates` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'promotionalRebates',
  `fba_inventory_credit` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'fbaInventoryCredit',
  `cash_on_delivery` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'cashOnDelivery',
  `other_in_amount` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'otherInAmount',
  `sales_refunds` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalSalesRefunds',
  `fee_refunds` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalFeeRefunds',
  `platform_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'platformFee',
  `fba_delivery_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalFbaDeliveryFee',
  `other_transaction_fees` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'otherTransactionFees',
  `ads_cost` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalAdsCost',
  `promotion_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'promotionFee',
  `storage_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalStorageFee',
  `inbound_convenience_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'sharedFbaInboundConvenienceFee',
  `international_inbound_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'sharedFbaIntegerernationalInboundFee',
  `adjustment_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'adjustments',
  `platform_other_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalPlatformOtherFee',
  `custom_order_fee` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'customOrderFee',
  `sales_tax` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'totalSalesTax',
  `sales_tax_refund` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'salesTaxRefund',
  `market_tax` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'salesTaxWithheld',
  `market_tax_refund` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'refundTaxWithheld',
  `purchase_cost` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'cgPriceTotal',
  `first_leg_cost` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'cgTransportCostsTotal',
  `other_cost` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'cgOtherCostsTotal',
  `gross_profit` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'grossProfit',
  `transit_loss` DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'FBA transit loss offset: cost detail codes 226 + 11 of purchase, first leg and other cost',
  `other_fees_json` JSON NULL COMMENT 'otherFeeStr custom fees summed by name',
  `sync_batch_id` VARCHAR(64) NOT NULL,
  `pulled_at` DATETIME NOT NULL,
  PRIMARY KEY (`stat_month`, `sid`, `msku`),
  KEY `idx_profit_report_msku_store` (`stat_month`, `store_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='LingXing profit report MSKU (settlement, monthly summary, CNY); whole month replaced per pull';

CREATE TABLE IF NOT EXISTS `ods_lingxing_profit_report_seller_month` (
  `stat_month` CHAR(7) NOT NULL,
  `sid` VARCHAR(32) NOT NULL,
  `store_name` VARCHAR(128) NULL,
  `country_code` VARCHAR(16) NULL,
  `currency_code` VARCHAR(8) NOT NULL DEFAULT 'CNY',
  `sales_qty` INT NOT NULL DEFAULT 0,
  `sales_amount` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `gross_profit` DECIMAL(18,4) NOT NULL DEFAULT 0,
  `sync_batch_id` VARCHAR(64) NOT NULL,
  `pulled_at` DATETIME NOT NULL,
  PRIMARY KEY (`stat_month`, `sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='LingXing profit report store totals (settlement, monthly, CNY); used to reconcile the MSKU pull';

CREATE TABLE IF NOT EXISTS `fin_amz_monthly_profit_adjustment` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `stat_month` CHAR(7) NOT NULL,
  `row_code` VARCHAR(32) NOT NULL COMMENT 'leaf row: EU / US1 / US2 / MJ / ZXY',
  `fee_item` VARCHAR(32) NOT NULL COMMENT 'which statement column the amount is added to',
  `amount` DECIMAL(18,2) NOT NULL COMMENT 'CNY; costs are negative, income positive',
  `remark` VARCHAR(255) NULL,
  `created_by` VARCHAR(64) NULL,
  `updated_by` VARCHAR(64) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_amz_monthly_profit_adj_month` (`stat_month`, `row_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Hand entered supplementary fees of the AMZ monthly profit statement';

INSERT INTO `scheduler_task` (`task_code`, `task_name`, `cron_expression`, `enabled`, `description`)
VALUES ('amz_monthly_profit_sync', CONVERT(X'414D5AE69C88E5BAA6E588A9E6B6A6E8A1A8E695B0E68DAEE68B89E58F96' USING utf8mb4), '0 0 6 7 * ?', 1,
        CONVERT(X'E6AF8FE69C8837E697A530363A3030E68B89E58F96E4B88AE4B8AAE5AE8CE695B4E887AAE784B6E69C88E9A286E6989FE588A9E6B6A6E68AA5E8A1A8EFBC884D534B55E4B88EE5BA97E993BAEFBC8CE7BB93E7AE97E58FA3E5BE84EFBC8CE4BABAE6B091E5B881EFBC89EFBC8CE695B4E69C88E69BBFE68DA2EFBC9B51756172747AE4B8BAE594AFE4B880E8AEA1E697B6E599A8' USING utf8mb4))
ON DUPLICATE KEY UPDATE `task_name`=VALUES(`task_name`), `cron_expression`=VALUES(`cron_expression`),
  `description`=VALUES(`description`);
