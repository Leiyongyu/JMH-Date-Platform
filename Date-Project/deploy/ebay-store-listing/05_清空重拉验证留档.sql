-- ============================================================================
-- 清空 eBay 刊登四张表，然后重新拉一次接口，验证「按月留档」整条链路。
--
-- 用途：验证留档是不是由同步流程自己写出来的，而不是靠迁移脚本回填的。
-- 清空后重拉，ods_ebay_store_listing_monthly 里的数据只可能来自 Python
-- 写入路径（replace_snapshots），验证才有意义。
--
-- ！！这是破坏性操作，清掉的是可以重新拉回来的原始数据 ！！
--   latest / state          —— 下次同步会全量重建
--   monthly / state_monthly —— 下次同步会写入当月这一份
-- 真正不可再生的是**往月**的留档。现在只有 2026-09 这一个月，且它本身就是
-- 从 latest 回填出来的，重拉后会以同样的月份重新写入，所以不丢历史。
-- 等以后攒了好几个月的留档，**不要**再执行本脚本。
--
-- 影响面：清空到重拉完成之间，「EBAY · 美元价格结构」点「重新统计」会报
-- 「尚无完整原始刊登数据，请先完成商品同步」。已发布的报表存在
-- dws_ebay_usd_price_* 里，没被碰，页面照常显示上一次的结果。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ============================================================================
-- 第1步 清空前先看一眼现状，留个底数
-- ============================================================================
SELECT 'latest' AS 表, COUNT(*) AS 行数, COUNT(DISTINCT seller_user_id) AS 账号数,
       MIN(pulled_at) AS 最早拉取, MAX(pulled_at) AS 最晚拉取
FROM ods_ebay_store_listing_latest
UNION ALL
SELECT 'monthly', COUNT(*), COUNT(DISTINCT seller_user_id), MIN(pulled_at), MAX(pulled_at)
FROM ods_ebay_store_listing_monthly;


-- ============================================================================
-- 第2步 重建留档表（新结构）并清空 latest / state
--
-- 用 DROP+CREATE 而不是 TRUNCATE：这样不管你之前有没有跑过迁移、跑的是
-- 哪一版结构，执行完都一定是当前这版（含 variations_json，不含 raw_xml 等）。
-- 本脚本不带回填，留档要靠重拉时的同步流程自己写——这正是要验证的东西。
-- ============================================================================

DROP TABLE IF EXISTS ods_ebay_store_listing_monthly;
DROP TABLE IF EXISTS ods_ebay_store_listing_state_monthly;

CREATE TABLE ods_ebay_store_listing_monthly (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '留档记录主键',
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay身份接口返回的稳定账号ID',
 seller_account VARCHAR(128) NOT NULL COMMENT 'eBay卖家账号用户名，用于区分店铺',
 item_id VARCHAR(64) NOT NULL COMMENT 'eBay商品刊登ItemID；同账号同月内唯一',
 sku TEXT NULL COMMENT '父级刊登SKU原值，缺失为NULL；多规格的各变体SKU见variations_json',
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
 variations_json JSON NULL COMMENT '多规格变体数组，每项含sku/price/quantity/quantity_sold，已剥除变体raw_xml；无变体为NULL。统计多规格刊登必须按本列逐变体计，不能用父级sku/current_price',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '完整成功发布的同步批次ID',
 pulled_at DATETIME NOT NULL COMMENT '本批拉取开始时间，北京时间',
 archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入留档表的时间',
 PRIMARY KEY(id),
 UNIQUE KEY uk_month_seller_item(stat_month,seller_user_id,item_id),
 KEY idx_month(stat_month),
 KEY idx_seller_month(seller_user_id,stat_month),
 KEY idx_month_sku(stat_month,sku(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='eBay在售商品按月留档；每账号每月一份，与latest表同事务写入，不存原始XML与元数据';

CREATE TABLE ods_ebay_store_listing_state_monthly (
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID',
 seller_account VARCHAR(128) NOT NULL COMMENT '本次认证成功的卖家用户名',
 row_count BIGINT UNSIGNED NOT NULL COMMENT '该账号当月留档条数；空店为0，用来区分"当月无刊登"和"当月没同步"',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '同步批次ID，与留档明细同事务提交',
 pulled_at DATETIME NOT NULL COMMENT '拉取开始时间，北京时间',
 published_at DATETIME NOT NULL COMMENT '拉取完成后发布开始时间，北京时间',
 archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入留档表的时间',
 PRIMARY KEY(stat_month,seller_user_id),
 KEY idx_month(stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='eBay店铺每月留档状态，每账号每月一行；row_count=0代表当月确实空店，缺行代表当月没同步';

TRUNCATE TABLE ods_ebay_store_listing_latest;
TRUNCATE TABLE ods_ebay_store_listing_state;


-- ============================================================================
-- 第3步 确认四张表都空了（四个数都应为 0），然后去触发同步
--
-- 触发方式：定时任务页面手动执行 `ebay_store_listing_sync`
--           （任务名「eBay店铺商品信息每月同步」）
-- 37个账号全量拉，会跑一会儿；任何一个账号失败都会整批回滚，
-- 表会保持为空，不会留下半份数据。
-- ============================================================================
SELECT (SELECT COUNT(*) FROM ods_ebay_store_listing_latest)             AS latest,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_state)              AS state,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly)            AS monthly,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_state_monthly)      AS state_monthly;
