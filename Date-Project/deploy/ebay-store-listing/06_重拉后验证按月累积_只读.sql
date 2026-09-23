-- ============================================================================
-- 重拉完成后跑这个，验证「按月累积」是不是由同步流程自己正确写出来的。
-- 全部只读，可以反复执行。每一步下面写了预期值和不符时的判断。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- 【1】月份写对了没
--
-- 预期：月份数=1；stat_month = pulled_at 的年月；月份没填的行=0。
-- 月份为空 → 跑的是旧代码，确认部署机已 git pull 且重启过 Python。
-- 月份≠拉取月份 → stat_month 取错了（应取 pulled_at，不是当前日期）。
SELECT COUNT(*) AS 行数,
       COUNT(DISTINCT stat_month) AS 月份数_应为1,
       MAX(stat_month) AS 留档月份,
       DATE_FORMAT(MAX(pulled_at),'%Y-%m') AS 拉取月份,
       MAX(stat_month) = DATE_FORMAT(MAX(pulled_at),'%Y-%m') AS 月份一致_应为1,
       SUM(stat_month IS NULL) AS 月份为空的行_应为0,
       COUNT(DISTINCT sync_batch_id) AS 批次数_应为1
FROM ods_ebay_store_listing_latest;


-- 【2】唯一键生效：同月同账号同商品只有一行
--
-- 预期：无结果。有结果说明唯一键没建上，同一个商品在同月重复了。
SELECT stat_month AS 月份, seller_account AS 店铺, item_id AS ItemID, COUNT(*) AS 重复行数
FROM ods_ebay_store_listing_latest
GROUP BY stat_month, seller_user_id, item_id HAVING COUNT(*) > 1 LIMIT 20;


-- 【3】变体写进去了没，变体自己的 raw_xml 剥掉了没
--
-- 这是本次改动最容易出错的地方：变体的SKU和价格只在这一列里，扁平列没有。
-- 清空前本地实测 43 个带变体刊登 / 141 个变体，重拉后应在同一量级
-- （eBay 上架下架会有出入，数量级差太多才是问题）。
-- 残留rawxml 和 空数组占位 必须都是 0。
SELECT SUM(variations_json IS NOT NULL) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(variations_json),0)) AS 变体总数,
       SUM(JSON_SEARCH(variations_json,'one','%',NULL,'$[*].raw_xml') IS NOT NULL) AS 残留rawxml_应为0,
       SUM(variations_json IS NOT NULL AND JSON_LENGTH(variations_json)=0) AS 空数组占位_应为0,
       MAX(JSON_LENGTH(variations_json)) AS 单条最多几个变体
FROM ods_ebay_store_listing_latest;

-- 抽几条带变体的看看：应有 sku/price/quantity/quantity_sold，没有 raw_xml
SELECT seller_account AS 店铺, item_id AS ItemID, sku AS 父级SKU,
       JSON_LENGTH(variations_json) AS 变体数, variations_json AS 变体内容
FROM ods_ebay_store_listing_latest
WHERE JSON_LENGTH(variations_json) > 0
ORDER BY JSON_LENGTH(variations_json) DESC LIMIT 3;


-- 【4】状态表：每账号每月一行，条数对得上，空店也在
--
-- 预期：对得上_应为1。空店（row_count=0）必须有行，
-- 否则趋势图分不清「当月空店」和「当月没同步」。
SELECT s.stat_month AS 月份, COUNT(*) AS 账号数, SUM(s.row_count) AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l WHERE l.stat_month=s.stat_month) AS 明细条数,
       SUM(s.row_count) = (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
                           WHERE l.stat_month=s.stat_month) AS 对得上_应为1,
       SUM(s.row_count=0) AS 空店数
FROM ods_ebay_store_listing_state s GROUP BY s.stat_month ORDER BY s.stat_month;


-- 【5】冗余列确实没了，容量降下来了
--
-- 预期：第一条无结果；明细表约 34MB（改造前 91MB）。
SELECT COLUMN_NAME AS 不该存在的列
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_ebay_store_listing_latest'
  AND COLUMN_NAME IN ('raw_xml','response_meta_json','normalized_json','source_page','api_total');

SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND(DATA_LENGTH/1024/1024,1) AS 数据MB, ROUND(INDEX_LENGTH/1024/1024,1) AS 索引MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME LIKE 'ods_ebay_store_listing%'
ORDER BY DATA_LENGTH DESC;


-- ============================================================================
-- 【6】同月重复同步只覆盖不追加 —— 再跑一次同步，然后执行本段
--
-- 预期：行数不翻倍、月份数仍为1、批次数仍为1；pulled_at 变成第二次的时间。
-- 行数翻倍 → DELETE 的月份范围不对，往月数据也有被污染的风险。
-- ============================================================================
SELECT COUNT(*) AS 行数,
       COUNT(DISTINCT stat_month) AS 月份数_应为1,
       COUNT(DISTINCT sync_batch_id) AS 批次数_应为1,
       MIN(pulled_at) AS 最早拉取, MAX(pulled_at) AS 最晚拉取
FROM ods_ebay_store_listing_latest;


-- ============================================================================
-- 【7】下个月同步之后跑这段：往月的数据必须原样还在
--
-- 预期：两个月份各自有行，行数都不为0。
-- 上个月的行消失 → DELETE 没按月份限定，历史被冲掉了。
-- ============================================================================
SELECT stat_month AS 月份, COUNT(*) AS 行数, COUNT(DISTINCT seller_user_id) AS 账号数,
       MIN(pulled_at) AS 拉取时间, SUM(variations_json IS NOT NULL) AS 带变体刊登数
FROM ods_ebay_store_listing_latest GROUP BY stat_month ORDER BY stat_month;
