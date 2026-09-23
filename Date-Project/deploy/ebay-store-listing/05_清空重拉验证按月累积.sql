-- ============================================================================
-- 清空 eBay 刊登两张表，然后重新拉一次接口，验证「按月累积」整条链路。
--
-- 用途：清空后重拉，表里的 stat_month / variations_json 只可能来自 Python
-- 写入路径（replace_snapshots），验证才有意义。
--
-- 前置：先执行 migrations/20260923_ebay_store_listing_monthly.sql
--       （加 stat_month / variations_json，删5个冗余列，换唯一键）。
--
-- ！！破坏性 ！！清掉的是可以重新拉回来的当前状态。
-- 现在表里只有 2026-09 这一个月，重拉会以同样的月份重新写入，不丢历史。
-- 等以后攒了好几个月，**不要**再执行本脚本——往月的数据是拉不回来的。
--
-- 影响面：清空到重拉完成之间，「EBAY · 美元价格结构」点「重新统计」会报
-- 「尚无完整原始刊登数据，请先完成商品同步」。已发布的报表存在
-- dws_ebay_usd_price_* 里，没被碰，页面照常显示上一次的结果。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- 【1】清空前留个底数
SELECT COUNT(*) AS 行数, COUNT(DISTINCT stat_month) AS 月份数,
       GROUP_CONCAT(DISTINCT stat_month ORDER BY stat_month) AS 有哪些月份,
       COUNT(DISTINCT seller_user_id) AS 账号数,
       SUM(variations_json IS NOT NULL) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(variations_json),0)) AS 变体总数
FROM ods_ebay_store_listing_latest;


-- 【2】清空
TRUNCATE TABLE ods_ebay_store_listing_latest;
TRUNCATE TABLE ods_ebay_store_listing_state;


-- 【3】确认都空了（两个数都应为0），然后去触发同步
--
-- 触发方式：定时任务页面手动执行 `ebay_store_listing_sync`
--           （任务名「eBay店铺商品信息每月同步」）
-- 全部账号完整拉取，会跑一会儿；任何一个账号失败都会整批回滚，
-- 表保持为空，不会留下半份数据。
--
-- 拉完执行 06_重拉后验证按月累积_只读.sql
SELECT (SELECT COUNT(*) FROM ods_ebay_store_listing_latest) AS 明细表,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_state)  AS 状态表;
