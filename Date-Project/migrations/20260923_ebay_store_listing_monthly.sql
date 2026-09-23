-- Python业务库 date-project：eBay店铺刊登原始数据按月留档。
--
-- 背景：ods_ebay_store_listing_latest 每次同步按账号先删后插，只保留最新一份，
-- 历史价格/库存/关注数全部丢失，做不了趋势。同步任务是每月5日跑一次
-- （scheduler_task.ebay_store_listing_sync，cron 0 0 5 5 * ?），所以按月留档
-- 正好一个月一份，不会重复膨胀。
--
-- 写入时机：与 latest 表在**同一个事务**里写，来源是同一批内存记录，
-- 不存在"latest 成功而历史漏写"的中间态。同月重复同步（手工补跑）时按
-- (账号, 月份) 先删后插，仍然只留一份，可重复执行。
--
-- 不动 latest 表和 state 表，报表读的仍是 latest，本次改动不影响现有页面。
--
-- 容量：实测 18076 行 / 37 个账号约 100MB（数据91MB + 索引8.5MB），
-- 每月一份，一年约 1.2GB。其中 raw_xml 平均1678字节、response_meta_json
-- 平均903字节。若日后嫌大，可只清理历史表的这两列（UPDATE ... SET raw_xml=''），
-- 结构化字段仍可做趋势；本脚本默认全字段留档，保真优先。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_monthly (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '留档记录主键',
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay身份接口返回的稳定账号ID',
 seller_account VARCHAR(128) NOT NULL COMMENT 'eBay卖家账号用户名，用于区分店铺',
 item_id VARCHAR(64) NOT NULL COMMENT 'eBay商品刊登ItemID；同账号同月内唯一',
 sku TEXT NULL COMMENT '刊登SKU原值，缺失为NULL，多变体见normalized_json',
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
 raw_xml LONGTEXT NOT NULL COMMENT '完整商品Item XML，含所有嵌套字段；XML等价重序列化非逐字节原文',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '完整成功发布的同步批次ID',
 pulled_at DATETIME NOT NULL COMMENT '本批拉取开始时间，北京时间',
 archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入历史表的时间',
 PRIMARY KEY(id),
 -- 同账号同月同商品只留一条；同月补跑走先删后插，天然不会撞键。
 UNIQUE KEY uk_month_seller_item(stat_month,seller_user_id,item_id),
 -- 趋势报表按月扫全量，或按店铺看单店曲线。
 KEY idx_month(stat_month),
 KEY idx_seller_month(seller_user_id,stat_month),
 KEY idx_month_sku(stat_month,sku(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='eBay在售商品原始数据按月留档；每账号每月一份，与latest表同事务写入';

CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_state_monthly (
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID',
 seller_account VARCHAR(128) NOT NULL COMMENT '本次认证成功的卖家用户名',
 row_count BIGINT UNSIGNED NOT NULL COMMENT '该账号当月留档条数；空店为0，用来区分"当月无刊登"和"当月没同步"',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '同步批次ID，与留档明细同事务提交',
 pulled_at DATETIME NOT NULL COMMENT '拉取开始时间，北京时间',
 published_at DATETIME NOT NULL COMMENT '拉取完成后发布开始时间，北京时间',
 archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入历史表的时间',
 PRIMARY KEY(stat_month,seller_user_id),
 KEY idx_month(stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='eBay店铺每月留档状态，每账号每月一行；row_count=0代表当月确实空店，缺行代表当月没同步';


-- ============================================================================
-- 一次性回填：把 latest 表里现有的这一份存进历史。
--
-- 不回填的话，当前这份（本地实测 2026-09-21 拉的 18076 行）会在下个月同步时
-- 被覆盖掉，等于白丢一个月。留档月份取自各行自己的 pulled_at，不是当前日期。
--
-- 可重复执行：先按 (月份, 账号) 删掉再插，重复跑结果一致。
-- 正常同步之后不需要再跑本段，同步已经自己写历史了。
-- ============================================================================

DELETE m FROM ods_ebay_store_listing_monthly m
JOIN (SELECT DISTINCT DATE_FORMAT(pulled_at,'%Y-%m') AS stat_month, seller_user_id
      FROM ods_ebay_store_listing_latest) k
  ON k.stat_month = m.stat_month AND k.seller_user_id = m.seller_user_id;

INSERT INTO ods_ebay_store_listing_monthly
 (stat_month,seller_user_id,seller_account,item_id,sku,title,site,current_price,currency,
  buy_it_now_price,buy_it_now_currency,quantity,quantity_available,quantity_sold,watch_count,
  listing_type,listing_duration,time_left,start_time,view_item_url,image_url,source_page,
  api_total,response_meta_json,normalized_json,raw_xml,sync_batch_id,pulled_at)
SELECT DATE_FORMAT(pulled_at,'%Y-%m'),seller_user_id,seller_account,item_id,sku,title,site,
       current_price,currency,buy_it_now_price,buy_it_now_currency,quantity,quantity_available,
       quantity_sold,watch_count,listing_type,listing_duration,time_left,start_time,view_item_url,
       image_url,source_page,api_total,response_meta_json,normalized_json,raw_xml,sync_batch_id,pulled_at
FROM ods_ebay_store_listing_latest;

-- 状态表同样回填，空店（row_count=0）也要有行，否则趋势图分不清"空店"和"没同步"。
REPLACE INTO ods_ebay_store_listing_state_monthly
 (stat_month,seller_user_id,seller_account,row_count,sync_batch_id,pulled_at,published_at)
SELECT DATE_FORMAT(pulled_at,'%Y-%m'),seller_user_id,seller_account,row_count,
       sync_batch_id,pulled_at,published_at
FROM ods_ebay_store_listing_state;


-- ============================================================================
-- 只读验证
-- ============================================================================

-- 历史表与latest表行数应一致（latest只有一份，且就是刚回填的那个月）
SELECT (SELECT COUNT(*) FROM ods_ebay_store_listing_latest)  AS latest行数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly) AS 历史行数,
       (SELECT COUNT(DISTINCT stat_month) FROM ods_ebay_store_listing_monthly) AS 留档月份数;

-- 每月每账号一份，明细行数应与状态表的row_count对得上
SELECT s.stat_month AS 月份, COUNT(*) AS 账号数, SUM(s.row_count) AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m WHERE m.stat_month=s.stat_month) AS 明细条数,
       SUM(s.row_count) = (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m
                           WHERE m.stat_month=s.stat_month) AS 对得上_应为1
FROM ods_ebay_store_listing_state_monthly s GROUP BY s.stat_month ORDER BY s.stat_month;

-- 容量增长，用来估算以后每月涨多少
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND(DATA_LENGTH/1024/1024,1) AS 数据MB, ROUND(INDEX_LENGTH/1024/1024,1) AS 索引MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME LIKE 'ods_ebay_store_listing%'
ORDER BY DATA_LENGTH DESC;
