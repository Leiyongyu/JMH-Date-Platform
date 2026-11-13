-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk);
-- Chinese values are written as UTF-8 hex literals.
-- Feishu bitable "auto parts purchase orders" (MACH data system V2): only the open orders of the CTU eBay warehouses are
-- pulled (Feishu side filter: warehouse is an eBay option, AMZ ignored; status is not finished / cancelled;
-- orders without a status are kept), one row per Feishu record, replaced
-- as a whole on every sync. eBay replenishment 2.0 reads the orders of the CTU eBay warehouses to show the purchase
-- logistics status per site + SKU (the Chengdu part comes from warehouse_inventory_detail in the ERP database).
-- Only creates the table and registers the scheduler task; idempotent, changes nothing else.
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ods_feishu_auto_parts_order` (
  `record_id` VARCHAR(32) COLLATE utf8mb4_bin NOT NULL COMMENT 'Feishu record_id; case sensitive (recXXab and recXXAB are different records)',
  `po` VARCHAR(64) NULL COMMENT 'purchase order no.',
  `sku` VARCHAR(128) NULL COMMENT 'actual purchase SKU, trimmed, upper case',
  `warehouse` VARCHAR(64) NULL COMMENT 'purchase warehouse as written in Feishu',
  `platform` VARCHAR(8) NULL COMMENT 'EBAY / AMZ, derived from the warehouse',
  `site` VARCHAR(16) NULL COMMENT 'eBay site (DE / UK / US in Chinese), derived from the warehouse; NULL for others',
  `order_status` VARCHAR(32) NULL COMMENT 'order status as written in Feishu',
  `quantity` DECIMAL(18,4) NULL,
  `order_amount` DECIMAL(18,2) NULL,
  `order_date` DATE NULL COMMENT 'order date (Beijing time)',
  `expected_ship_date` DATE NULL COMMENT 'expected ship date (Beijing time)',
  `apply_date` DATE NULL COMMENT 'purchase request date (Beijing time)',
  `purchaser` VARCHAR(64) NULL,
  `product_name` VARCHAR(255) NULL,
  `not_purchased_reason` VARCHAR(255) NULL,
  `feishu_updated_at` DATETIME NULL COMMENT 'Feishu last_modified_time (Beijing time)',
  `sync_batch_id` VARCHAR(36) NOT NULL,
  `synced_at` DATETIME NOT NULL,
  PRIMARY KEY (`record_id`),
  KEY `idx_site_sku` (`site`, `sku`),
  KEY `idx_po` (`po`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Feishu auto parts purchase orders';

INSERT INTO `scheduler_task` (`task_code`, `task_name`, `cron_expression`, `enabled`, `description`)
VALUES ('feishu_auto_parts_order_sync', CONVERT(X'E9A39EE4B9A6E6B1BDE9858DE8AEA2E58D95E5908CE6ADA5' USING utf8mb4), '0 0 8,13,18 * * ?', 1,
        CONVERT(X'E6AF8FE5A4A930383A3030E3808131333A3030E3808131383A3030E5908CE6ADA5E9A39EE4B9A6E3808CE6B1BDE9858DE8AEA2E58D95E3808D43545565626179E4BB93E69CAAE5AE8CE68890E98787E8B4ADE58D95EFBC88E4B88DE590AB414D5AE4BB93E38081E5B7B2E5AE8CE68890E38081E5B7B2E58F96E6B688EFBC9BE78AB6E68081E38081E695B0E9878FE38081E4B88BE58D95E697A5E69C9FE38081E9A284E8AEA1E58F91E8B4A7E697B6E997B4EFBC89EFBC8CE4BE9B65426179E8A1A5E8B4A7322E30E789A9E6B581E78AB6E68081E4BDBFE794A8EFBC9B51756172747AE4B8BAE594AFE4B880E8AEA1E697B6E599A8' USING utf8mb4))
ON DUPLICATE KEY UPDATE `task_name`=VALUES(`task_name`), `cron_expression`=VALUES(`cron_expression`),
  `description`=VALUES(`description`);
