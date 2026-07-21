-- eBay 财务数据归 Python 服务管理，仅存放于 export_tax_refund。
USE `export_tax_refund`;

CREATE TABLE IF NOT EXISTS `ebay_finance_import_batch` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `platform` varchar(32) NOT NULL, `site` varchar(64) NOT NULL,
  `period_start` date NOT NULL, `period_end` date NOT NULL,
  `file_name` varchar(255) NOT NULL, `file_hash` char(64) DEFAULT NULL,
  `total_rows` int NOT NULL DEFAULT 0, `inserted_rows` int NOT NULL DEFAULT 0,
  `updated_rows` int NOT NULL DEFAULT 0, `operator` varchar(64) DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'SUCCESS', `error_message` varchar(1000) DEFAULT NULL,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_finance_batch_period` (`platform`,`site`,`period_start`,`period_end`),
  KEY `idx_ebay_finance_batch_end` (`period_end`), KEY `idx_ebay_finance_batch_update` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay财务酷长利润导入批次';

CREATE TABLE IF NOT EXISTS `ebay_finance_profit` (
  `id` bigint NOT NULL AUTO_INCREMENT, `batch_id` bigint NOT NULL,
  `platform` varchar(32) NOT NULL, `site` varchar(64) NOT NULL,
  `period_start` date NOT NULL, `period_end` date NOT NULL, `sku` varchar(160) NOT NULL,
  `image_url` varchar(1000) DEFAULT NULL, `multi_attribute` varchar(20) DEFAULT NULL,
  `order_total` decimal(20,6) DEFAULT NULL, `order_amount` decimal(20,6) DEFAULT NULL,
  `units_sold` int DEFAULT NULL, `order_count` int DEFAULT NULL, `tax_amount` decimal(20,6) DEFAULT NULL,
  `profit` decimal(20,6) DEFAULT NULL, `profit_margin` decimal(20,10) DEFAULT NULL,
  `product_sales_amount` decimal(20,6) DEFAULT NULL, `shipping_revenue` decimal(20,6) DEFAULT NULL,
  `platform_fee` decimal(20,6) DEFAULT NULL, `payment_fee` decimal(20,6) DEFAULT NULL,
  `purchase_cost` decimal(20,6) DEFAULT NULL, `first_leg_freight` decimal(20,6) DEFAULT NULL,
  `tail_freight` decimal(20,6) DEFAULT NULL, `refund_amount` decimal(20,6) DEFAULT NULL,
  `advertising_fee` decimal(20,6) DEFAULT NULL, `platform_other_fee` decimal(20,6) DEFAULT NULL,
  `raw_data_json` json NOT NULL, `source_file_name` varchar(255) NOT NULL,
  `created_by` varchar(64) DEFAULT NULL, `updated_by` varchar(64) DEFAULT NULL,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ebay_finance_period_sku` (`platform`,`site`,`period_start`,`period_end`,`sku`),
  KEY `idx_ebay_finance_batch` (`batch_id`), KEY `idx_ebay_finance_period` (`period_end`,`site`),
  KEY `idx_ebay_finance_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay财务酷长利润明细';
