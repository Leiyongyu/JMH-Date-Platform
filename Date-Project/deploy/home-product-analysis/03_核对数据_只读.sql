-- ============================================================================
-- 核对「EBAY · 美元价格结构」与「产品结构」两张图
--
-- 全部只读，可反复执行。每一步下面写了预期值和不符时该查什么。
-- 在 Python 业务库 date-project 执行，**在 01 建表并点过一次刷新之后**。
-- 没点过刷新的话 dwd/dws 是空的，【1】会全是0，那不是出错。
--
-- 链路：
--   ods_ebay_store_listing_latest   每月5日拉的在售刊登（原样）
--        │ 拆变体、去空SKU/空站点、价格转数值
--   dwd_ebay_listing_sku            一行=一个可分档的刊登SKU，仍是原币
--        │ × rate_org(原币) ÷ rate_org(USD)，落七档
--   dws_ebay_listing_price_tier     一行=月×店铺×站点×SKU 的美元价与档位
--
-- 档位界限 5/20/50/100/200/500，左闭右开，与页面完全一致。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SET @month = '2026-09';
SET @year  = '2026';


-- ============================================================================
-- 【1】三层行数对照 —— 一眼看出哪一层掉了数
--
-- 预期：
--   ODS   = 该月拉回来的刊登条数，和 state 表的 row_count 合计相等
--   DWD   = ODS - 带变体的父级行 + 变体总数 - 清洗丢弃行
--   DWS   ≤ DWD（同店铺同站点同SKU的多条刊登合并成一行）
-- 本地实测 2026-09：ODS 18013 / 候选 18111 / DWD 18111 / DWS 16989
-- ============================================================================
SELECT 'ODS 在售刊登'      AS 层, COUNT(*) AS 行数,
       COUNT(DISTINCT seller_user_id) AS 账号数,
       SUM(variations_json IS NOT NULL) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(variations_json),0)) AS 变体总数
FROM ods_ebay_store_listing_latest WHERE stat_month=@month
UNION ALL
SELECT 'DWD 刊登SKU明细', COUNT(*), COUNT(DISTINCT seller_user_id),
       SUM(is_variation=1), NULL
FROM dwd_ebay_listing_sku WHERE stat_month=@month
UNION ALL
SELECT 'DWS 美元价与档位', COUNT(*), COUNT(DISTINCT seller_user_id),
       NULL, COUNT(DISTINCT sku)
FROM dws_ebay_listing_price_tier WHERE stat_month=@month;

-- 加工状态：清洗丢了多少行、用的哪个月汇率，都在这一行里
SELECT * FROM dws_ebay_listing_price_state WHERE stat_month=@month;

-- ODS 与同步状态表对得上吗（预期 对得上_应为1）
SELECT s.stat_month AS 月份, COUNT(*) AS 账号数, SUM(s.row_count) AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
        WHERE l.stat_month=s.stat_month) AS 明细条数,
       SUM(s.row_count)=(SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
                         WHERE l.stat_month=s.stat_month) AS 对得上_应为1
FROM ods_ebay_store_listing_state s GROUP BY s.stat_month ORDER BY s.stat_month;


-- ============================================================================
-- 【2】换汇有没有算错 —— 抽查每个币种一条，手算一遍
--
-- 预期：手算美元价 与 price_usd 相差在 0.000001 以内。
-- 差得多就去看 dim_lingxing_currency_month 里该币种那个月的 rate_org
-- 是不是被改过（DWS 存的是当时用的值，汇率表改了这里不会跟着变，
-- 这正是要点刷新重算的原因）。
-- ============================================================================
SELECT currency AS 原币, price_original AS 原币价, rate_org AS 原币汇率,
       rate_month AS 汇率月份, usd_rate_org AS 美元汇率, usd_rate_month AS 美元汇率月份,
       price_usd AS 存的美元价,
       ROUND(price_original*rate_org/usd_rate_org, 8) AS 手算美元价,
       ABS(price_usd - price_original*rate_org/usd_rate_org) < 0.000001 AS 对得上_应为1,
       tier_no AS 档位
FROM (SELECT t.*, ROW_NUMBER() OVER (PARTITION BY currency ORDER BY sku) AS rn
      FROM dws_ebay_listing_price_tier t WHERE stat_month=@month) x
WHERE rn=1 ORDER BY currency;

-- 美元原币必须短路：rate_org 与 usd_rate_org 都记 1，且美元价=原币价
SELECT COUNT(*) AS 美元行数,
       SUM(price_usd <> price_original) AS 美元被换过汇的行_应为0,
       SUM(rate_org <> 1 OR usd_rate_org <> 1) AS 美元记了汇率的行_应为0
FROM dws_ebay_listing_price_tier WHERE stat_month=@month AND currency='USD';


-- ============================================================================
-- 【3】分档界限 —— 落档必须和价格自洽
--
-- 预期：档位对不上的行 = 0。
-- ============================================================================
SELECT tier_no AS 档位,
       CASE tier_no WHEN 1 THEN '0-5' WHEN 2 THEN '5-20' WHEN 3 THEN '20-50'
            WHEN 4 THEN '50-100' WHEN 5 THEN '100-200' WHEN 6 THEN '200-500'
            ELSE '500以上' END AS 价格段,
       COUNT(*) AS 行数, COUNT(DISTINCT sku) AS 去重SKU数,
       MIN(price_usd) AS 最低美元价, MAX(price_usd) AS 最高美元价,
       ROUND(COUNT(*)*100/SUM(COUNT(*)) OVER (), 1) AS 占比
FROM dws_ebay_listing_price_tier WHERE stat_month=@month
GROUP BY tier_no ORDER BY tier_no;

SELECT SUM(tier_no <> CASE WHEN price_usd <   5 THEN 1 WHEN price_usd <  20 THEN 2
                           WHEN price_usd <  50 THEN 3 WHEN price_usd < 100 THEN 4
                           WHEN price_usd < 200 THEN 5 WHEN price_usd < 500 THEN 6
                           ELSE 7 END) AS 档位对不上的行_应为0
FROM dws_ebay_listing_price_tier WHERE stat_month=@month;


-- ============================================================================
-- 【4】页面卡片上的三个数 —— 逐个对
--
-- 店铺行按SKU去重（取该店铺内最低档），站点行各站点分别计，
-- 所以「店铺SKU数」小于等于「站点SKU数合计」，这不是对不上账。
-- ============================================================================
SELECT COUNT(DISTINCT seller_account) AS 店铺数,
       COUNT(DISTINCT seller_account, sku) AS 店铺SKU数_卡片上的total,
       COUNT(DISTINCT sku)               AS 去重SKU数_卡片上的distinct,
       COUNT(*)                          AS 店铺站点SKU行数
FROM dws_ebay_listing_price_tier WHERE stat_month=@month;

-- 某个店铺的逐档明细，和页面上那一行逐格对照
SET @shop = 'moses-motorsports';
SELECT tier_no AS 档位, COUNT(*) AS SKU数,
       ROUND(COUNT(*)*100/SUM(COUNT(*)) OVER (), 2) AS 占比
FROM (SELECT sku, MIN(tier_no) AS tier_no FROM dws_ebay_listing_price_tier
      WHERE stat_month=@month AND seller_account=@shop GROUP BY sku) t
GROUP BY tier_no ORDER BY tier_no;


-- ============================================================================
-- 【5】产品结构 · 不同价格段销售数量占比
--
-- 销量 = dwd_ebay_sku_analysis_order.purchase_quantity，按 payment_time 归月，
--        不分站点、不分店铺，毛销量不扣退货（与 eBay 补货2.0 一致）
-- 档位 = 同月 dws_ebay_listing_price_tier 里该SKU的最低档
-- 占比的分母只算「两边都有的SKU」，配不上档位的销量不入任何一档
--
-- 预期：每个月 占比 一列相加 = 100%；覆盖率应在 90% 以上
-- （在售刊登有2000+个SKU，当月卖过的SKU绝大多数都在里面；
--   若覆盖率骤降，去查当月是不是少同步了账号，看【1】的账号数）
-- ============================================================================
WITH sku_tier AS (
    SELECT stat_month, sku, MIN(tier_no) AS tier_no
    FROM dws_ebay_listing_price_tier GROUP BY stat_month, sku
),
sales AS (
    SELECT DATE_FORMAT(payment_time,'%Y-%m') AS m, TRIM(inventory_sku) AS sku,
           SUM(purchase_quantity) AS qty, SUM(refund_quantity) AS refund_qty,
           COUNT(*) AS order_rows
    FROM dwd_ebay_sku_analysis_order
    WHERE payment_time IS NOT NULL AND TRIM(IFNULL(inventory_sku,'')) <> ''
    GROUP BY 1, 2
),
tiered AS (
    SELECT s.m, s.sku, s.qty, s.refund_qty, s.order_rows,
           COALESCE(p.tier_no, 0) AS tier_no
    FROM sales s LEFT JOIN sku_tier p ON p.stat_month=s.m AND p.sku=s.sku
),
-- 分母单独算：窗口函数不能和 GROUP BY 混用（ONLY_FULL_GROUP_BY 会拒绝）。
matched AS (SELECT m, SUM(qty) AS matched_qty FROM tiered WHERE tier_no>0 GROUP BY m)
SELECT t.m AS 月份,
       CASE t.tier_no WHEN 0 THEN '(无档位，不计入占比)' WHEN 1 THEN '0-5' WHEN 2 THEN '5-20'
            WHEN 3 THEN '20-50' WHEN 4 THEN '50-100' WHEN 5 THEN '100-200'
            WHEN 6 THEN '200-500' ELSE '500以上' END AS 价格档,
       SUM(t.qty) AS 销量, SUM(t.refund_qty) AS 退货量_未扣除,
       SUM(t.order_rows) AS 订单行数, COUNT(*) AS SKU数,
       -- 无档位那行不在分母里，给它算占比会误导，直接留空。
       CASE WHEN t.tier_no>0
            THEN ROUND(SUM(t.qty)*100/NULLIF(mt.matched_qty,0), 1) END AS 占比
FROM tiered t LEFT JOIN matched mt ON mt.m=t.m
WHERE t.m LIKE CONCAT(@year,'-%')
GROUP BY t.m, t.tier_no, mt.matched_qty ORDER BY t.m, t.tier_no;

-- 覆盖率（页面图下那行注记的来源）
WITH sku_tier AS (SELECT stat_month, sku FROM dws_ebay_listing_price_tier
                  GROUP BY stat_month, sku),
sales AS (
    SELECT DATE_FORMAT(payment_time,'%Y-%m') AS m, TRIM(inventory_sku) AS sku,
           SUM(purchase_quantity) AS qty
    FROM dwd_ebay_sku_analysis_order
    WHERE payment_time IS NOT NULL AND TRIM(IFNULL(inventory_sku,'')) <> ''
    GROUP BY 1, 2)
SELECT s.m AS 月份, SUM(s.qty) AS 总销量,
       SUM(IF(p.sku IS NOT NULL, s.qty, 0)) AS 有档位销量,
       ROUND(SUM(IF(p.sku IS NOT NULL, s.qty, 0))*100/SUM(s.qty), 1) AS 覆盖率,
       COUNT(*) AS 订单SKU数, SUM(p.sku IS NOT NULL) AS 有档位SKU数
FROM sales s LEFT JOIN sku_tier p ON p.stat_month=s.m AND p.sku=s.sku
WHERE s.m LIKE CONCAT(@year,'-%')
GROUP BY s.m ORDER BY s.m;

-- 注意：某个月没有当月的刊登快照时，页面会借用不晚于该月的最近一个快照来定档，
-- 上面这两段只按「同月」匹配，所以没有快照的月份覆盖率会是0。
-- 哪些月份有快照：
SELECT DISTINCT stat_month AS 有刊登快照的月份 FROM dws_ebay_listing_price_tier ORDER BY 1;


-- ============================================================================
-- 【5b】店铺筛选能不能用 —— 订单账号与刊登账号的对账
--
-- 页面上「产品结构」的店铺多选，销量那张图靠订单表的 seller_account。
-- 预期：有账号的行占比接近100%；对不上的账号只有少数几个（没配eBay授权的店）。
-- 某个月有账号的行=0，说明那个月还是旧模板传的，要用新模板重传。
-- ============================================================================
SELECT DATE_FORMAT(payment_time,'%Y-%m') AS 月份, COUNT(*) AS 行数,
       SUM(seller_account <> '') AS 有账号的行,
       COUNT(DISTINCT NULLIF(seller_account,'')) AS 账号数,
       ROUND(SUM(seller_account <> '')*100/COUNT(*), 1) AS 覆盖率
FROM dwd_ebay_sku_analysis_order
GROUP BY 1 ORDER BY 1;

SELECT o.seller_account AS 订单账号, COUNT(*) AS 订单行数,
       SUM(o.purchase_quantity) AS 销量,
       IF(t.seller_account IS NULL, '✗ 在售刊登里没有（多半是没配eBay授权凭证）', '✓ 对上了') AS 对账
FROM dwd_ebay_sku_analysis_order o
LEFT JOIN (SELECT DISTINCT seller_account FROM dws_ebay_listing_price_tier) t
       ON t.seller_account = o.seller_account
WHERE o.seller_account <> ''
GROUP BY o.seller_account, t.seller_account
ORDER BY 对账, 销量 DESC;


-- ============================================================================
-- 【6】抽一个SKU从头核到尾 —— 最直接的验证方式
--
-- 换成你想查的SKU。四段输出应当自洽：
--   ODS 那几条刊登的挂牌价 -> DWD 拆完之后每条的原币价
--   -> DWS 取最低价、换汇、落档 -> 页面上该店铺该档位里有它
-- ============================================================================
SET @sku = 'FRD-70361-4-0734';

SELECT seller_account AS 店铺, site AS 站点, item_id AS 物品编号,
       current_price AS 挂牌价, currency AS 币种,
       variations_json IS NOT NULL AS 有变体
FROM ods_ebay_store_listing_latest
WHERE stat_month=@month AND TRIM(sku)=@sku ORDER BY seller_account, site;

SELECT seller_account AS 店铺, site AS 站点, item_id AS 物品编号,
       variation_no AS 变体序号, is_variation AS 来自变体,
       price_original AS 原币价, currency AS 币种
FROM dwd_ebay_listing_sku
WHERE stat_month=@month AND sku=@sku ORDER BY seller_account, site, variation_no;

SELECT seller_account AS 店铺, site AS 站点, currency AS 币种,
       price_original AS 最低原币价, price_usd AS 美元价, tier_no AS 档位,
       listing_count AS 合并了几条刊登, rate_org AS 原币汇率, rate_month AS 汇率月份
FROM dws_ebay_listing_price_tier
WHERE stat_month=@month AND sku=@sku ORDER BY seller_account, site;

-- 该SKU当月的销量（产品结构图里它算进哪一档）
SELECT @sku AS SKU, @month AS 月份,
       COUNT(*) AS 订单行数, COUNT(DISTINCT platform_order_no) AS 去重订单数,
       SUM(purchase_quantity) AS 销量, SUM(refund_quantity) AS 退货量
FROM dwd_ebay_sku_analysis_order
WHERE TRIM(inventory_sku)=@sku AND DATE_FORMAT(payment_time,'%Y-%m')=@month;


-- ============================================================================
-- 【7】数据完整性自检
--
-- 预期：所有「_应为0」的列都是 0。
-- ============================================================================
SELECT SUM(sku IS NULL OR sku='')                     AS DWD缺SKU_应为0,
       SUM(site IS NULL OR site='')                   AS DWD缺站点_应为0,
       SUM(price_original <= 0)                       AS DWD价格非正_应为0
FROM dwd_ebay_listing_sku WHERE stat_month=@month;

-- DWS 的每一行都必须能在 DWD 里找到来源
SELECT COUNT(*) AS DWS里DWD没有的组合_应为0
FROM dws_ebay_listing_price_tier w
LEFT JOIN (SELECT DISTINCT stat_month,seller_user_id,site,sku FROM dwd_ebay_listing_sku) d
  ON d.stat_month=w.stat_month AND d.seller_user_id=w.seller_user_id
 AND d.site=w.site AND d.sku=w.sku
WHERE w.stat_month=@month AND d.sku IS NULL;

-- 合并计数要对得上：listing_count 之和 = DWD 行数（扣掉换不出汇的那些）
SELECT (SELECT SUM(listing_count) FROM dws_ebay_listing_price_tier WHERE stat_month=@month)
       AS 合并计数合计,
       (SELECT COUNT(*) FROM dwd_ebay_listing_sku WHERE stat_month=@month)
       AS DWD行数,
       (SELECT dropped_no_rate FROM dws_ebay_listing_price_state WHERE stat_month=@month)
       AS 换不出汇被丢的行;
