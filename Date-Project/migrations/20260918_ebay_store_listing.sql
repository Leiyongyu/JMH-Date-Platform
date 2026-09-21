-- 在Python数据库执行；独立新表，不修改任何既有刊登/补货表。
CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_latest (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '原始记录主键',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay身份接口返回的稳定账号ID，覆盖范围及联合唯一键',
 seller_account VARCHAR(128) NOT NULL COMMENT 'eBay卖家账号用户名，用于区分店铺',
 item_id VARCHAR(64) NOT NULL COMMENT 'eBay商品刊登ItemID；同账号内唯一，不按SKU去重',
 sku TEXT NULL COMMENT '刊登SKU原值，缺失为NULL，多变体见完整XML',
 title TEXT NULL COMMENT '刊登商品标题',
 site VARCHAR(16) NULL COMMENT '从商品ViewItemURL域名识别站点，非账号注册站点；无法识别为空',
 current_price VARCHAR(128) NULL COMMENT 'CurrentPrice原始十进制文本，不换汇不丢精度',
 currency VARCHAR(16) NULL COMMENT 'CurrentPrice的currencyID原币种',
 buy_it_now_price VARCHAR(128) NULL COMMENT 'BuyItNowPrice原始十进制文本',
 buy_it_now_currency VARCHAR(16) NULL COMMENT 'BuyItNowPrice原币种',
 quantity BIGINT UNSIGNED NULL COMMENT '接口Quantity原值，非推算库存',
 quantity_available BIGINT UNSIGNED NULL COMMENT '接口QuantityAvailable可用数量',
 quantity_sold BIGINT UNSIGNED NULL COMMENT '接口QuantitySold累计已售数量，缺失不补零',
 watch_count BIGINT UNSIGNED NULL COMMENT '接口WatchCount关注数量',
 listing_type VARCHAR(128) NULL COMMENT '刊登类型，如FixedPriceItem',
 listing_duration VARCHAR(64) NULL COMMENT '刊登时长，如GTC',
 time_left VARCHAR(128) NULL COMMENT '接口TimeLeft原始时长字符串',
 start_time VARCHAR(128) NULL COMMENT 'ListingDetails.StartTime原值，保留UTC标记',
 view_item_url TEXT NULL COMMENT '商品刊登查看链接',
 image_url TEXT NULL COMMENT 'PictureDetails.GalleryURL主图链接',
 source_page INT UNSIGNED NOT NULL COMMENT '本条所在API页码，从1开始，每页100条',
 api_total BIGINT UNSIGNED NOT NULL COMMENT '该账号接口报告的总刊登条数',
 response_meta_json JSON NOT NULL COMMENT '账号身份、分页、Ack、时间及完整响应信封XML等元数据，不含令牌',
 normalized_json JSON NOT NULL COMMENT '标准化商品字段及全部变体数组，数值价格保留十进制文本',
 raw_xml LONGTEXT NOT NULL COMMENT '完整商品Item XML，含所有嵌套字段及未来扩展字段；XML等价重序列化非逐字节原文',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '完整成功发布的同步批次ID',
 pulled_at DATETIME NOT NULL COMMENT '本批拉取开始时间，北京时间',
 PRIMARY KEY(id),
 UNIQUE KEY uk_seller_item(seller_user_id,item_id),
 KEY idx_account_sku(seller_account,sku(128))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='eBay官方Trading在售商品原始数据；按账号保留最新完整批次，不影响其他账号';
CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_state (
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID，账号成功发布状态主键',
 seller_account VARCHAR(128) NOT NULL COMMENT '本次认证成功的卖家用户名',
 row_count BIGINT UNSIGNED NOT NULL COMMENT '该账号成功发布的条数，明确空店为0',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '同步批次ID，与商品原始表同事务提交',
 pulled_at DATETIME NOT NULL COMMENT '拉取开始时间，北京时间',
 published_at DATETIME NOT NULL COMMENT '拉取完成后发布开始时间，北京时间',
 PRIMARY KEY(seller_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='eBay店铺最新成功同步状态，每账号一行，失败不修改';
INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
VALUES('ebay_store_listing_sync','eBay店铺商品信息每月同步','0 0 5 5 * ?',1,
 '每月5日北京时间05:00，Quartz唯一计时；官方GetMyeBaySelling在售列表；配置账号完整拉取校验后事务覆盖，失败保留旧数据。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name),cron_expression=VALUES(cron_expression),description=VALUES(description);
