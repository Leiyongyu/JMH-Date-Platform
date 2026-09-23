-- ============================================================================
-- 重拉完成后跑这个，验证「按月留档」是不是由同步流程自己正确写出来的。
-- 全部只读，可以反复执行。每一步下面写了预期值和不符时的判断。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- 【1】留档有没有写进去，月份对不对
--
-- 预期：留档行数 = latest行数；留档月份数 = 1；留档月份 = pulled_at 的年月。
-- 留档行数为0 → 同步跑的是旧代码，确认部署机已 git pull 且重启过 Python。
-- 月份不等于 pulled_at 的年月 → stat_month 取错了（应取拉取时间，不是当前日期）。
SELECT (SELECT COUNT(*) FROM ods_ebay_store_listing_latest)  AS latest行数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly) AS 留档行数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest)
     = (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly) AS 行数相等_应为1,
       (SELECT COUNT(DISTINCT stat_month) FROM ods_ebay_store_listing_monthly) AS 留档月份数_应为1,
       (SELECT MAX(stat_month) FROM ods_ebay_store_listing_monthly)            AS 留档月份,
       (SELECT DATE_FORMAT(MAX(pulled_at),'%Y-%m') FROM ods_ebay_store_listing_latest) AS 拉取月份;


-- 【2】逐行比对：留档与 latest 的共有字段必须逐字相同
--
-- 预期：不一致行数 = 0，且两边互相都没有多出来的 ItemID。
-- 不为0 → 留档不是从同一批记录投影出来的，写入路径有问题。
SELECT COUNT(*) AS 共有ItemID数,
       SUM(l.seller_account <=> m.seller_account
           AND l.sku <=> m.sku AND l.title <=> m.title AND l.site <=> m.site
           AND l.current_price <=> m.current_price AND l.currency <=> m.currency
           AND l.buy_it_now_price <=> m.buy_it_now_price
           AND l.buy_it_now_currency <=> m.buy_it_now_currency
           AND l.quantity <=> m.quantity AND l.quantity_available <=> m.quantity_available
           AND l.quantity_sold <=> m.quantity_sold AND l.watch_count <=> m.watch_count
           AND l.listing_type <=> m.listing_type AND l.listing_duration <=> m.listing_duration
           AND l.time_left <=> m.time_left AND l.start_time <=> m.start_time
           AND l.view_item_url <=> m.view_item_url AND l.image_url <=> m.image_url
           AND l.sync_batch_id <=> m.sync_batch_id AND l.pulled_at <=> m.pulled_at) AS 逐字一致行数,
       SUM(NOT (l.current_price <=> m.current_price))  AS 价格不一致_应为0,
       SUM(NOT (l.sku <=> m.sku))                      AS SKU不一致_应为0
FROM ods_ebay_store_listing_latest l
JOIN ods_ebay_store_listing_monthly m
  ON m.seller_user_id = l.seller_user_id AND m.item_id = l.item_id;

-- 两边不应有对不上的行（都应为0）
SELECT (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
        WHERE NOT EXISTS (SELECT 1 FROM ods_ebay_store_listing_monthly m
                          WHERE m.seller_user_id=l.seller_user_id AND m.item_id=l.item_id)) AS latest有留档没有_应为0,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m
        WHERE NOT EXISTS (SELECT 1 FROM ods_ebay_store_listing_latest l
                          WHERE l.seller_user_id=m.seller_user_id AND l.item_id=m.item_id)) AS 留档有latest没有_应为0;


-- 【3】变体没丢，且变体自己的 raw_xml 已剥掉
--
-- 这是本次改动最容易出错的地方：变体的SKU和价格只在这里，扁平列没有。
-- 预期：两边变体总数相等；带变体的刊登数相等；残留raw_xml = 0。
-- 留档变体总数偏小 → variations_payload 丢了变体，多规格刊登会塌缩成一个SKU。
SELECT (SELECT SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations')),0))
        FROM ods_ebay_store_listing_latest)                            AS latest变体总数,
       (SELECT SUM(COALESCE(JSON_LENGTH(variations_json),0))
        FROM ods_ebay_store_listing_monthly)                           AS 留档变体总数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest
        WHERE JSON_LENGTH(JSON_EXTRACT(normalized_json,'$.variations'))>0) AS latest带变体刊登数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly
        WHERE JSON_LENGTH(variations_json)>0)                          AS 留档带变体刊登数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly
        WHERE JSON_SEARCH(variations_json,'one','%',NULL,'$[*].raw_xml') IS NOT NULL) AS 残留rawxml_应为0,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly
        WHERE variations_json IS NOT NULL AND JSON_LENGTH(variations_json)=0) AS 空数组占位_应为0;

-- 逐个刊登比对变体数量，不一致的列出来（预期无结果）
SELECT l.seller_account AS 店铺, l.item_id AS ItemID, l.sku AS 父级SKU,
       JSON_LENGTH(JSON_EXTRACT(l.normalized_json,'$.variations')) AS latest变体数,
       COALESCE(JSON_LENGTH(m.variations_json),0)                  AS 留档变体数
FROM ods_ebay_store_listing_latest l
JOIN ods_ebay_store_listing_monthly m
  ON m.seller_user_id=l.seller_user_id AND m.item_id=l.item_id
WHERE COALESCE(JSON_LENGTH(JSON_EXTRACT(l.normalized_json,'$.variations')),0)
   <> COALESCE(JSON_LENGTH(m.variations_json),0);

-- 抽一条带变体的看看长什么样：应有 sku/price/quantity/quantity_sold，没有 raw_xml
SELECT seller_account AS 店铺, item_id AS ItemID, sku AS 父级SKU,
       JSON_LENGTH(variations_json) AS 变体数, variations_json AS 变体内容
FROM ods_ebay_store_listing_monthly
WHERE JSON_LENGTH(variations_json) > 0
ORDER BY JSON_LENGTH(variations_json) DESC LIMIT 3;


-- 【4】状态表：每账号每月一行，条数对得上，空店也在
--
-- 预期：账号数与 state 表一致；对得上_应为1；空店行数与 state 表的一致。
-- 空店缺行 → 趋势图分不清「当月空店」和「当月没同步」。
SELECT s.stat_month AS 月份, COUNT(*) AS 留档账号数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_state)  AS state账号数,
       SUM(s.row_count)                                     AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m
        WHERE m.stat_month=s.stat_month)                    AS 明细条数,
       SUM(s.row_count) = (SELECT COUNT(*) FROM ods_ebay_store_listing_monthly m
                           WHERE m.stat_month=s.stat_month) AS 对得上_应为1,
       SUM(s.row_count=0)                                   AS 空店数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_state WHERE row_count=0) AS state里的空店数
FROM ods_ebay_store_listing_state_monthly s
GROUP BY s.stat_month ORDER BY s.stat_month;


-- 【5】容量：留档表应明显小于 latest（去掉了XML与元数据）
--
-- 预期：latest 约 91MB，留档约 34MB。留档接近 latest → 冗余列没砍掉。
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND(DATA_LENGTH/1024/1024,1) AS 数据MB, ROUND(INDEX_LENGTH/1024/1024,1) AS 索引MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME LIKE 'ods_ebay_store_listing%'
ORDER BY DATA_LENGTH DESC;

-- 留档表确实不该再有这些列（应返回空结果）
SELECT COLUMN_NAME AS 不该存在的列
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_ebay_store_listing_monthly'
  AND COLUMN_NAME IN ('raw_xml','response_meta_json','normalized_json','source_page','api_total');


-- ============================================================================
-- 【6】同月重复同步只留一份 —— 想验证覆盖逻辑再跑一次同步，然后执行本段
--
-- 预期：留档月份数仍为1，留档行数仍等于latest行数，没有翻倍；
--       archived_at 变成第二次同步的时间，说明是覆盖不是追加。
-- ============================================================================
SELECT COUNT(*) AS 留档行数,
       COUNT(DISTINCT stat_month)  AS 月份数_应为1,
       COUNT(DISTINCT sync_batch_id) AS 批次数_应为1,
       MIN(archived_at) AS 最早写入, MAX(archived_at) AS 最晚写入
FROM ods_ebay_store_listing_monthly;
