-- Python业务库 date-project：eBay店铺刊登数据改为在同一张表里按月累积。
--
-- 背景：ods_ebay_store_listing_latest 每次同步按账号先删后插，只保留最新一份，
-- 历史价格/库存/关注数全部丢失，做不了趋势。同步任务每月5日跑一次
-- （scheduler_task.ebay_store_listing_sync，cron 0 0 5 5 * ?），所以按月累积
-- 正好一个月一份。留档月份取自 pulled_at 的年月，同月补跑按(月份,账号)覆盖。
--
-- 不新建历史表：全项目只有 listing_price_tier_repository 读这张表，
-- 加个月份过滤即可，没必要多一套表。
--
-- ============================================================================
-- 删掉哪些列，为什么
-- ============================================================================
--   raw_xml             商品完整XML，实测 28.9MB，全项目零读取
--   response_meta_json  账号身份/分页/Ack/响应信封，实测 15.6MB，同批次内高度重复
--   normalized_json     实测 12.5MB。抽样3000行核对过：它的键除 variations 外
--                       （sku/site/title/item_id/quantity/image_url/time_left/
--                       start_time/watch_count/listing_type/current_price/
--                       quantity_sold/view_item_url/buy_it_now_price/
--                       listing_duration/quantity_available）全部与扁平列重复
--   source_page         该条所在API页码，只对当次拉取排障有用
--   api_total           接口报告的总条数，用 state 的 row_count 即可
--
-- 接口返回的是当前状态、随时能重拉，所以原始XML留着的边际价值很低；
-- 而按月累积之后它会变成每月 29MB 的净增长。
--
-- 唯一不能删的是变体数组，单拎成 variations_json：
--   报表的 ebay_candidates 在刊登有变体时**按变体的SKU和价格逐个统计、不用父级那行**，
--   而扁平列只有父级的单个 sku/price。实测 43 个刊登带变体、共 141 个变体，
--   删掉会把 141 个SKU塌缩成 43 个，且多规格各变体价格不同，分档会错。
--   变体自己那份 raw_xml 一并剥掉，只留 sku/price/quantity/quantity_sold。
--
-- 容量：改造前 91.1MB/份。裁剪后约 34MB/月，一年约 0.4GB。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ============================================================================
-- 第0步 如果跑过上一版迁移（独立留档表方案），把那两张表删掉
--
-- 它们的内容全部是从 latest 回填出来的，latest 还在，删掉不丢任何东西。
-- 没跑过的话这两行什么也不做。
-- ============================================================================
DROP TABLE IF EXISTS ods_ebay_store_listing_monthly;
DROP TABLE IF EXISTS ods_ebay_store_listing_state_monthly;


-- ============================================================================
-- 第1步【只读】改造前的底数，等会儿拿来比对
--
-- 记下这三个数：行数、带变体的刊登数、变体总数。
-- 本地实测：18076 行 / 43 个带变体 / 141 个变体。
-- ============================================================================
SELECT COUNT(*) AS 行数,
       COUNT(DISTINCT seller_user_id) AS 账号数,
       DATE_FORMAT(MAX(pulled_at),'%Y-%m') AS 拉取月份,
       SUM(JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations'))>0) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')),0)) AS 变体总数,
       MAX(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')),0)) AS 单条最多几个变体
FROM ods_ebay_store_listing_latest;


-- ============================================================================
-- 第2步 加列并填值（此时旧列还在，填不出来可以随时回退）
-- ============================================================================

ALTER TABLE ods_ebay_store_listing_latest
  ADD COLUMN stat_month CHAR(7) NULL
    COMMENT '留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份' AFTER id,
  ADD COLUMN variations_json JSON NULL
    COMMENT '多规格变体数组，每项含sku/price/quantity/quantity_sold，已剥除变体raw_xml；无变体为NULL。统计多规格刊登必须按本列逐变体计，不能用父级sku/current_price'
    AFTER image_url;

UPDATE ods_ebay_store_listing_latest
SET stat_month = DATE_FORMAT(pulled_at,'%Y-%m'),
    -- 只留变体数组，并逐个剥掉变体自己的raw_xml。JSON_REMOVE 会忽略不存在的路径，
    -- 所以给到20个槽位对5个变体也安全；超过20个的行由第1步的"单条最多几个变体"揪出来。
    variations_json = CASE WHEN JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')) > 0
        THEN JSON_REMOVE(JSON_EXTRACT(normalized_json,'$.variations'),
             '$[0].raw_xml','$[1].raw_xml','$[2].raw_xml','$[3].raw_xml','$[4].raw_xml',
             '$[5].raw_xml','$[6].raw_xml','$[7].raw_xml','$[8].raw_xml','$[9].raw_xml',
             '$[10].raw_xml','$[11].raw_xml','$[12].raw_xml','$[13].raw_xml','$[14].raw_xml',
             '$[15].raw_xml','$[16].raw_xml','$[17].raw_xml','$[18].raw_xml','$[19].raw_xml')
        ELSE NULL END;

ALTER TABLE ods_ebay_store_listing_state
  ADD COLUMN stat_month CHAR(7) NULL COMMENT '留档月份YYYY-MM' FIRST;

UPDATE ods_ebay_store_listing_state
SET stat_month = DATE_FORMAT(pulled_at,'%Y-%m');


-- ============================================================================
-- 第3步【只读】删旧列之前先确认变体没丢
--
-- 四个数都必须是 0 才继续往下执行第4步。不为0就**停下**，别删列，
-- 旧的 normalized_json 还在，可以直接 UPDATE 重来。
-- ============================================================================
SELECT SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')),0)
         <> COALESCE(JSON_LENGTH(variations_json),0))              AS 变体数对不上的行_应为0,
       SUM(JSON_SEARCH(variations_json,'one','%',NULL,'$[*].raw_xml') IS NOT NULL)
                                                                    AS 还带rawxml的行_应为0,
       SUM(variations_json IS NOT NULL AND JSON_LENGTH(variations_json)=0)
                                                                    AS 空数组占位的行_应为0,
       SUM(stat_month IS NULL)                                      AS 月份没填上的行_应为0
FROM ods_ebay_store_listing_latest;

SELECT SUM(stat_month IS NULL) AS state月份没填上_应为0 FROM ods_ebay_store_listing_state;


-- ============================================================================
-- 第4步 删旧列、换唯一键
--
-- 唯一键从 (账号,ItemID) 换成 (月份,账号,ItemID)：同一个商品在不同月份各留一行，
-- 同月同账号同商品仍然只能有一行——重复写入会直接报错，不会悄悄多出一份。
-- ============================================================================

ALTER TABLE ods_ebay_store_listing_latest
  MODIFY COLUMN stat_month CHAR(7) NOT NULL
    COMMENT '留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份',
  DROP COLUMN raw_xml,
  DROP COLUMN response_meta_json,
  DROP COLUMN normalized_json,
  DROP COLUMN source_page,
  DROP COLUMN api_total,
  DROP INDEX uk_seller_item,
  ADD UNIQUE KEY uk_month_seller_item(stat_month,seller_user_id,item_id),
  ADD KEY idx_month(stat_month),
  ADD KEY idx_seller_month(seller_user_id,stat_month),
  COMMENT='eBay官方Trading在售商品，按月累积；每账号每月一份，键(月份,账号,ItemID)。不存原始XML与响应元数据，多规格变体见variations_json';

ALTER TABLE ods_ebay_store_listing_state
  MODIFY COLUMN stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM',
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (stat_month,seller_user_id),
  ADD KEY idx_month(stat_month),
  COMMENT='eBay店铺每月同步状态，每账号每月一行；row_count=0代表当月确实空店，缺行代表当月没同步';


-- ============================================================================
-- 第5步【只读】改造后验证
-- ============================================================================

-- 行数、月份、变体都应与第1步记下的底数一致
SELECT COUNT(*) AS 行数, COUNT(DISTINCT stat_month) AS 月份数,
       MIN(stat_month) AS 最早月份, MAX(stat_month) AS 最晚月份,
       SUM(variations_json IS NOT NULL) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(variations_json),0)) AS 变体总数
FROM ods_ebay_store_listing_latest;

-- 每月每账号的条数应与 state 对得上
SELECT s.stat_month AS 月份, COUNT(*) AS 账号数, SUM(s.row_count) AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l WHERE l.stat_month=s.stat_month) AS 明细条数,
       SUM(s.row_count) = (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
                           WHERE l.stat_month=s.stat_month) AS 对得上_应为1
FROM ods_ebay_store_listing_state s GROUP BY s.stat_month ORDER BY s.stat_month;

-- 旧列确实没了（应返回空结果）
SELECT COLUMN_NAME AS 不该存在的列
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_ebay_store_listing_latest'
  AND COLUMN_NAME IN ('raw_xml','response_meta_json','normalized_json','source_page','api_total');

-- 容量：从约91MB降到约34MB
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND(DATA_LENGTH/1024/1024,1) AS 数据MB, ROUND(INDEX_LENGTH/1024/1024,1) AS 索引MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME LIKE 'ods_ebay_store_listing%'
ORDER BY DATA_LENGTH DESC;
