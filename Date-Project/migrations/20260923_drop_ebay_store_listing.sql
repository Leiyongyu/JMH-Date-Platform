-- 下线 eBay 在售刊登拉取：价格结构改以飞书「不良交易刊登」为主表之后，
-- 这条链路已经没有任何读取方。
--
-- 已随代码删除：
--   backend/repositories/ebay_store_listing_repository.py
--   backend/services/ebay_store_listing_sync_service.py
--   listing_price_tier_service.ebay_candidates()
--   RuoYi 的 PythonEbayStoreListingTask.java 与 runEbayStoreListing
--
-- 保留：backend/ebay_api/ 整个包（凭证、账号配置、密钥健康检查仍在用），
--       以及定时任务 ebay_token_health_check。以后想恢复拉取，接回来即可。
--
-- ！！本脚本会删表，不可逆 ！！当前两张表约 18013 行 / 37 个账号。
-- 接口返回的是当前在售状态，重新接回同步就能再拉一份；但**往月的快照拉不回来**。
-- 执行前先确认不再需要这份历史。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- 第1步【只读】删之前看一眼要删掉什么
SELECT 'ods_ebay_store_listing_latest' AS 表, COUNT(*) AS 行数,
       COUNT(DISTINCT stat_month) AS 月份数, COUNT(DISTINCT seller_user_id) AS 账号数
FROM ods_ebay_store_listing_latest
UNION ALL
SELECT 'ods_ebay_store_listing_state', COUNT(*), COUNT(DISTINCT stat_month), COUNT(DISTINCT seller_user_id)
FROM ods_ebay_store_listing_state;


-- 第2步 删表
DROP TABLE IF EXISTS ods_ebay_store_listing_latest;
DROP TABLE IF EXISTS ods_ebay_store_listing_state;


-- 第3步 摘掉 Python 侧的任务登记（密钥健康检查保留，不在此列）
DELETE FROM scheduler_task WHERE task_code = 'ebay_store_listing_sync';


-- 第4步【只读】确认
SELECT COUNT(*) AS 残留表_应为0 FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'date-project'
  AND TABLE_NAME IN ('ods_ebay_store_listing_latest','ods_ebay_store_listing_state');

SELECT task_code AS 剩余的ebay相关任务, task_name, cron_expression, enabled
FROM scheduler_task WHERE task_code LIKE '%ebay%' OR task_code LIKE '%feishu%'
ORDER BY task_code;
