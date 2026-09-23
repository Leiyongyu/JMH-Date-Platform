-- Python业务库 date-project：eBay店铺刊登数据按月留档。
--
-- 背景：ods_ebay_store_listing_latest 每次同步按账号先删后插，只保留最新一份，
-- 历史价格/库存/关注数全部丢失，做不了趋势。同步任务每月5日跑一次
-- （scheduler_task.ebay_store_listing_sync，cron 0 0 5 5 * ?），所以按月留档
-- 正好一个月一份。留档月份取自 pulled_at 的年月，同月重复同步按(月份,账号)覆盖。
--
-- 写入时机：与 latest 表在**同一个事务**里写，来源是同一批内存记录，
-- 不存在"latest 成功而历史漏写"的中间态。
--
-- 不动 latest 表和 state 表，报表读的仍是 latest，本次改动不影响现有页面。
--
-- ============================================================================
-- 留档不存哪些列，为什么
-- ============================================================================
-- 已从 latest 的列里去掉（都已解析进扁平列，或只对当次同步排障有意义）：
--   raw_xml             商品完整XML，实测 28.9MB，扁平列已全部解析出来
--   response_meta_json  账号身份/分页/Ack/响应信封，实测 15.6MB，同批次内高度重复
--   normalized_json     实测 12.5MB。抽样3000行核对过：它的键除 variations 外
--                       （sku/site/title/item_id/quantity/image_url/time_left/
--                       start_time/watch_count/listing_type/current_price/
--                       quantity_sold/view_item_url/buy_it_now_price/
--                       listing_duration/quantity_available）全部与扁平列重复
--   source_page         该条所在API页码，只对当次拉取排障有用
--   api_total           接口报告的总条数，留档用 state_monthly.row_count 即可
--
-- 唯一不能删的是变体数组，所以单拎出 variations_json：
--   报表的 ebay_candidates 在刊登有变体时**按变体的SKU和价格逐个统计、不用父级那行**，
--   而扁平列只有父级的单个 sku/price。实测 43 个刊登带变体、共 141 个变体，
--   删掉就会把 141 个SKU塌缩成 43 个，且多规格各变体价格不同，分档会错。
--   变体自己那份 raw_xml 一并剥掉，只留 sku/price/quantity/quantity_sold，
--   剥完整个数组不到 100KB。
--
-- 容量：latest 实测 18076行/37账号，数据91.1MB。按上面裁剪后留档约34MB/月，
-- 一年约 0.4GB（不裁剪是 1.2GB）。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ============================================================================
-- 开发阶段重跑：留档表目前的全部内容都是从 latest 回填出来的，latest 还在，
-- 删掉重建不丢任何东西。若已按旧结构建过表，这两行保证换成新结构。
-- 正式有了多个月的留档之后，**不要**再执行这两行。
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
 -- 同账号同月同商品只留一条；同月补跑走先删后插，天然不会撞键。
 UNIQUE KEY uk_month_seller_item(stat_month,seller_user_id,item_id),
 -- 趋势报表按月扫全量，或按店铺看单店曲线。
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


-- ============================================================================
-- 一次性回填：把 latest 里现有的这一份存进留档。
--
-- 不回填的话，当前这份（本地实测 2026-09-21 拉的 18076 行）会在下个月同步时
-- 被覆盖掉，等于白丢一个月。留档月份取自各行自己的 pulled_at，不是当前日期。
--
-- 可重复执行：先按 (月份, 账号) 删掉再插。正常同步之后不需要再跑本段，
-- 同步已经自己写留档了。
-- ============================================================================

DELETE m FROM ods_ebay_store_listing_monthly m
JOIN (SELECT DISTINCT DATE_FORMAT(pulled_at,'%Y-%m') AS stat_month, seller_user_id
      FROM ods_ebay_store_listing_latest) k
  ON k.stat_month = m.stat_month AND k.seller_user_id = m.seller_user_id;

INSERT INTO ods_ebay_store_listing_monthly
 (stat_month,seller_user_id,seller_account,item_id,sku,title,site,current_price,currency,
  buy_it_now_price,buy_it_now_currency,quantity,quantity_available,quantity_sold,watch_count,
  listing_type,listing_duration,time_left,start_time,view_item_url,image_url,variations_json,
  sync_batch_id,pulled_at)
SELECT DATE_FORMAT(pulled_at,'%Y-%m'),seller_user_id,seller_account,item_id,sku,title,site,
       current_price,currency,buy_it_now_price,buy_it_now_currency,quantity,quantity_available,
       quantity_sold,watch_count,listing_type,listing_duration,time_left,start_time,view_item_url,
       image_url,
       -- 只留变体数组，并逐个剥掉变体自己的raw_xml。JSON_REMOVE 会忽略不存在的路径，
       -- 所以给到20个槽位对5个变体也安全；超过20个的行由下面的验证查询揪出来。
       CASE WHEN JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')) > 0
            THEN JSON_REMOVE(JSON_EXTRACT(normalized_json,'$.variations'),
                 '$[0].raw_xml','$[1].raw_xml','$[2].raw_xml','$[3].raw_xml','$[4].raw_xml',
                 '$[5].raw_xml','$[6].raw_xml','$[7].raw_xml','$[8].raw_xml','$[9].raw_xml',
                 '$[10].raw_xml','$[11].raw_xml','$[12].raw_xml','$[13].raw_xml','$[14].raw_xml',
                 '$[15].raw_xml','$[16].raw_xml','$[17].raw_xml','$[18].raw_xml','$[19].raw_xml')
            ELSE NULL END,
       sync_batch_id,pulled_at
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

-- 行数应与 latest 一致（latest 只有一份，就是刚回填的那个月）
SELECT (SELECT COUNT(*) FROM ods_ebay_store_listing_latest)  AS latest行数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly) AS 留档行数,
       (SELECT COUNT(DISTINCT stat_month) FROM ods_ebay_store_listing_monthly) AS 留档月份数;

-- 变体没丢：两边的变体总数应相等，且留档里不应再有变体raw_xml
SELECT (SELECT SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')),0))
        FROM ods_ebay_store_listing_latest)                                   AS latest变体总数,
       (SELECT SUM(COALESCE(JSON_LENGTH(variations_json),0))
        FROM ods_ebay_store_listing_monthly)                                  AS 留档变体总数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly
        WHERE JSON_SEARCH(variations_json,'one','%raw_xml%','',  '$[*]') IS NOT NULL) AS 残留rawxml_应为0,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest
        WHERE JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')) > 20) AS 变体超20个的行_应为0;

-- 每月每账号一份，明细行数应与状态表的row_count对得上
SELECT s.stat_month AS 月份, COUNT(*) AS 账号数, SUM(s.row_count) AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m WHERE m.stat_month=s.stat_month) AS 明细条数,
       SUM(s.row_count) = (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m
                           WHERE m.stat_month=s.stat_month) AS 对得上_应为1
FROM ods_ebay_store_listing_state_monthly s GROUP BY s.stat_month ORDER BY s.stat_month;

-- 容量对比：留档表应明显小于 latest（去掉了XML与元数据）
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND(DATA_LENGTH/1024/1024,1) AS 数据MB, ROUND(INDEX_LENGTH/1024/1024,1) AS 索引MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME LIKE 'ods_ebay_store_listing%'
ORDER BY DATA_LENGTH DESC;
