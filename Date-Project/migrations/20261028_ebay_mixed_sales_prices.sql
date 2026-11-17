-- Python数据库：混销独立月度在售商品快照。SHOP行登记成功空店，ITEM行保存刊登。
CREATE TABLE IF NOT EXISTS ods_ebay_mixed_sales_listing_monthly (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
 stat_month CHAR(7) NOT NULL,
 seller_user_id VARCHAR(128) NOT NULL,
 seller_account VARCHAR(128) NOT NULL,
 shop_name VARCHAR(200) NOT NULL,
 record_type VARCHAR(8) NOT NULL COMMENT 'SHOP=店铺成功快照标记，ITEM=在售刊登',
 item_id VARCHAR(64) NOT NULL DEFAULT '',
 sku VARCHAR(255) NULL,
 normalized_sku VARCHAR(255) NULL COMMENT '与补货2.0相同，仅归并YXR/RXY后缀',
 title TEXT NULL,
 site VARCHAR(16) NULL,
 current_price VARCHAR(128) NULL COMMENT 'CurrentPrice原始十进制文本，不换汇',
 currency VARCHAR(16) NULL,
 buy_it_now_price VARCHAR(128) NULL,
 buy_it_now_currency VARCHAR(16) NULL,
 listing_type VARCHAR(128) NULL,
 quantity BIGINT UNSIGNED NULL,
 quantity_available BIGINT UNSIGNED NULL,
 quantity_sold BIGINT UNSIGNED NULL,
 view_item_url TEXT NULL,
 image_url TEXT NULL,
 variations_json JSON NULL,
 raw_json JSON NULL COMMENT '商品信息原值，去掉重复XML，不含授权凭证',
 source_listing_count BIGINT UNSIGNED NULL COMMENT 'SHOP行登记接口确认的完整刊登数，允许0',
 sync_batch_id VARCHAR(64) NOT NULL,
 pulled_at DATETIME NOT NULL,
 published_at DATETIME NOT NULL,
 PRIMARY KEY(id),
 UNIQUE KEY uk_mixed_month_seller_item(stat_month,seller_user_id,item_id),
 KEY idx_mixed_month_sku(stat_month,normalized_sku),
 KEY idx_mixed_shop_month(seller_user_id,stat_month),
 KEY idx_mixed_month_type(stat_month,record_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='混销-eBay每月每店铺完整在售商品及原币售价；同店同月覆盖';

INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
SELECT 'ebay_mixed_sales_price_sync','混销-eBay在售售价月度同步','0 0 7 3 * ?',0,
 'Java Quartz每月3日北京时间07:00调度；Python登记禁用，避免双调度；当月店铺完整覆盖，保留其他月份'
WHERE NOT EXISTS(SELECT 1 FROM scheduler_task WHERE task_code='ebay_mixed_sales_price_sync');
