-- Python业务库 date-project：eBay SKU分析订单接入「平台账号」维度。
--
-- 背景：数字酋长订单模板从 2026-09-24 起在最前面多了一列。在这之前订单表
-- 只有站点、没有店铺，所以产品结构那几张图按店铺筛不了——库里所有 %ebay%
-- 表里带 shop/store/seller 的列全在刊登侧，订单侧一个都没有。
--
--   ods_ebay_sku_analysis_order_raw.source_platform_account   Excel原值，原样留档
--   dwd_ebay_sku_analysis_order.seller_account                清洗后（去首尾空白）
--
-- 这一列的值就是 eBay 卖家账号本身（aplus-shop、oyeah-motor…），与
-- dws_ebay_listing_price_tier.seller_account 完全相等，**不需要另建映射表**：
-- 实测订单文件39个账号，其中37个与在售刊登一字不差地对上，剩下 kelan
-- 是没配 eBay 授权的店，Vco8TviLRZK 共22行、看着像token不像账号。
-- 真正需要推导的只有飞书那一侧（帝蓝泰江-eBay-Oyeah Motor），
-- 那个由读取侧按「只留字母数字、统一小写」的后缀匹配自动算，也不落库。
--
-- 空串的含义是「这批订单是旧模板上传的，源文件里没有这一列」，不是「没有店铺」。
-- 要让历史月份也能按店铺筛，得用新模板把那些月份重传一遍。
--
-- Python 服务启动时 _initialize_tables 会自动补列并改名，这份脚本是给
-- 「想先在库里看一眼、或者不方便重启服务」的场景用的，可重复执行。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ============================================================================
-- 第1步【只读】改之前的底数
-- ============================================================================
SELECT COUNT(*) AS 订单明细行数,
       COUNT(DISTINCT import_batch_id) AS 导入批次数,
       MIN(DATE_FORMAT(payment_time,'%Y-%m')) AS 最早月份,
       MAX(DATE_FORMAT(payment_time,'%Y-%m')) AS 最晚月份
FROM dwd_ebay_sku_analysis_order;


-- ============================================================================
-- 第2步 加列（已有旧列名就改名）
--
-- 2026-09-24 当天先按「店铺名称」接过一版，随后数字酋长把这列定成了
-- 「平台账号」。跑过上一版的机器会有 source_shop_name / shop_name 两个旧列，
-- 这里改名而不是新增——两个列名指的是同一件事，留着旧列只会多一份永远是空的
-- 数据，以后谁都说不清该读哪个。
--
-- 用动态SQL而不是直接写 ALTER：加列和改名是二选一，写死哪一条都会在另一种
-- 情况下报错中断。下面四段都是「存在才执行」，重复跑不会出错。
-- ============================================================================

SET @db = DATABASE();

-- 2.1 ODS：有旧列就改名，没有就加
SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_sku_analysis_order_raw'
                       AND COLUMN_NAME='source_shop_name'),
  'ALTER TABLE ods_ebay_sku_analysis_order_raw RENAME COLUMN source_shop_name TO source_platform_account',
  IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_sku_analysis_order_raw'
              AND COLUMN_NAME='source_platform_account'),
    'DO 0',
    'ALTER TABLE ods_ebay_sku_analysis_order_raw ADD COLUMN source_platform_account VARCHAR(191) DEFAULT NULL COMMENT ''Excel第一列原始平台账号，2026-09-24起模板新增'' AFTER source_row'));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 2.2 DWD：同上
SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                       AND COLUMN_NAME='shop_name'),
  'ALTER TABLE dwd_ebay_sku_analysis_order RENAME COLUMN shop_name TO seller_account',
  IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
              AND COLUMN_NAME='seller_account'),
    'DO 0',
    'ALTER TABLE dwd_ebay_sku_analysis_order ADD COLUMN seller_account VARCHAR(191) NOT NULL DEFAULT '''' COMMENT ''eBay卖家账号，取上传源数据的平台账号；与dws_ebay_listing_price_tier.seller_account同义；空串=该批次源文件没有这一列'' AFTER site_name'));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 2.3 列注释统一刷一遍（改名不会带新注释过来）
ALTER TABLE dwd_ebay_sku_analysis_order
  MODIFY COLUMN seller_account VARCHAR(191) NOT NULL DEFAULT ''
    COMMENT 'eBay卖家账号，取上传源数据的平台账号；与dws_ebay_listing_price_tier.seller_account同义；空串=该批次源文件没有这一列';
ALTER TABLE ods_ebay_sku_analysis_order_raw
  MODIFY COLUMN source_platform_account VARCHAR(191) DEFAULT NULL
    COMMENT 'Excel第一列原始平台账号，2026-09-24起模板新增';

-- 2.4 索引：有旧名就改名，没有就建
SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                       AND INDEX_NAME='idx_esa_dwd_shop_time'),
  'ALTER TABLE dwd_ebay_sku_analysis_order RENAME INDEX idx_esa_dwd_shop_time TO idx_esa_dwd_account_time',
  IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
              AND INDEX_NAME='idx_esa_dwd_account_time'),
    'DO 0',
    'ALTER TABLE dwd_ebay_sku_analysis_order ADD KEY idx_esa_dwd_account_time (seller_account, payment_time)'));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ============================================================================
-- 第3步 已经入过库的批次，若ODS里有账号就回填到DWD
--
-- 只有用新模板传过的批次才填得上；旧批次两边都是空的，回填不动，
-- 必须用新模板重传。
-- ============================================================================
UPDATE dwd_ebay_sku_analysis_order d
INNER JOIN ods_ebay_sku_analysis_order_raw o
        ON o.import_batch_id = d.import_batch_id AND o.source_row = d.source_row
SET d.seller_account = TRIM(o.source_platform_account)
WHERE d.seller_account = ''
  AND o.source_platform_account IS NOT NULL AND TRIM(o.source_platform_account) <> '';


-- ============================================================================
-- 第4步【只读】确认：哪些月份有账号，哪些还得重传
--
-- 有账号的行数=0 的月份，就是还没用新模板传过的月份。
-- ============================================================================
SELECT DATE_FORMAT(payment_time,'%Y-%m') AS 月份,
       COUNT(*) AS 行数,
       SUM(seller_account <> '') AS 有账号的行,
       COUNT(DISTINCT NULLIF(seller_account,'')) AS 账号数,
       ROUND(SUM(seller_account <> '')*100/COUNT(*), 1) AS 覆盖率
FROM dwd_ebay_sku_analysis_order
GROUP BY 1 ORDER BY 1;


-- ============================================================================
-- 第5步【只读】订单账号 vs 在售刊登账号 —— 直接等值join，看能不能全对上
--
-- 预期：绝大多数订单账号在 dws_ebay_listing_price_tier 里找得到。
-- 找不到的要么是没配 eBay 授权凭证的店（该补凭证），要么是脏值。
-- ============================================================================
SELECT o.seller_account AS 订单账号,
       COUNT(*) AS 订单行数,
       SUM(o.purchase_quantity) AS 销量,
       IF(t.seller_account IS NULL, '✗ 在售刊登里没有', '✓ 对上了') AS 对账
FROM dwd_ebay_sku_analysis_order o
LEFT JOIN (SELECT DISTINCT seller_account FROM dws_ebay_listing_price_tier) t
       ON t.seller_account = o.seller_account
WHERE o.seller_account <> ''
GROUP BY o.seller_account, t.seller_account
ORDER BY 对账, 销量 DESC;
