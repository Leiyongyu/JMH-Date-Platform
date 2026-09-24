-- Python业务库 date-project：eBay SKU分析订单接入「店铺名称」维度。
--
-- 背景：数字酋长订单模板从 2026-09-24 起在最前面多了一列「店铺名称」。
-- 在这之前订单表只有站点、没有店铺，所以产品结构那几张图按店铺筛不了——
-- 库里所有 %ebay% 表里带 shop/store/seller 的列全在刊登侧，订单侧一个都没有。
--
--   ods_ebay_sku_analysis_order_raw.source_shop_name   Excel原值，原样留档
--   dwd_ebay_sku_analysis_order.shop_name              清洗后（去首尾空白）
--
-- 空串的含义是「这批订单是旧模板上传的，源文件里没有店铺列」，不是「没有店铺」。
-- 要让历史月份也能按店铺筛，得用新模板把那些月份重传一遍。
--
-- 店铺名三边写法不一，不在库里归一，读取侧按「只留字母数字、统一小写」的键匹配：
--   订单文件      Oyeah-Motor
--   eBay卖家账号  oyeah-motor
--   飞书不良交易  帝蓝泰江-eBay-Oyeah Motor
-- 归一规则本身在 ebay_sku_unit_price_repository._match_key，只此一处。
--
-- Python 服务启动时 _initialize_tables 会自动补这两列，这份脚本是给
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
-- 第2步 加列
--
-- MySQL 8.0.29+ 的 ADD COLUMN 是 INSTANT 的，不重建表。
-- 已经加过就会报 1060 duplicate column，属于正常，跳过继续即可。
-- ============================================================================
ALTER TABLE ods_ebay_sku_analysis_order_raw
  ADD COLUMN source_shop_name VARCHAR(191) DEFAULT NULL
    COMMENT 'Excel第一列原始店铺名称，2026-09-24起模板新增' AFTER source_row;

ALTER TABLE dwd_ebay_sku_analysis_order
  ADD COLUMN shop_name VARCHAR(191) NOT NULL DEFAULT ''
    COMMENT '店铺名称，取上传源数据；空串=该批次源文件没有店铺列' AFTER site_name,
  ADD KEY idx_esa_dwd_shop_time (shop_name, payment_time);


-- ============================================================================
-- 第3步 已经入过库的批次，若ODS里有店铺名就回填到DWD
--
-- 只有用新模板传过的批次才填得上；旧批次两边都是空的，回填不动，
-- 必须用新模板重传。
-- ============================================================================
UPDATE dwd_ebay_sku_analysis_order d
INNER JOIN ods_ebay_sku_analysis_order_raw o
        ON o.import_batch_id = d.import_batch_id AND o.source_row = d.source_row
SET d.shop_name = TRIM(o.source_shop_name)
WHERE d.shop_name = '' AND o.source_shop_name IS NOT NULL AND TRIM(o.source_shop_name) <> '';


-- ============================================================================
-- 第4步【只读】确认：哪些月份有店铺名，哪些还得重传
--
-- 有店铺名的行数=0 的月份，就是还没用新模板传过的月份。
-- ============================================================================
SELECT DATE_FORMAT(payment_time,'%Y-%m') AS 月份,
       COUNT(*) AS 行数,
       SUM(shop_name <> '') AS 有店铺名的行,
       COUNT(DISTINCT NULLIF(shop_name,'')) AS 店铺数,
       ROUND(SUM(shop_name <> '')*100/COUNT(*), 1) AS 覆盖率
FROM dwd_ebay_sku_analysis_order
GROUP BY 1 ORDER BY 1;

-- 已经落库的店铺名清单，拿它和 dws_ebay_listing_price_tier.seller_account 对照，
-- 对不上的就是没配 eBay 授权凭证的店。
SELECT shop_name AS 店铺, COUNT(*) AS 订单行数,
       COUNT(DISTINCT inventory_sku) AS SKU数,
       SUM(purchase_quantity) AS 销量
FROM dwd_ebay_sku_analysis_order
WHERE shop_name <> ''
GROUP BY shop_name ORDER BY 销量 DESC;
