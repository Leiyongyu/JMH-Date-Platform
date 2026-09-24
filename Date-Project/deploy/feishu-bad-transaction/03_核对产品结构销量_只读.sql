-- ============================================================================
-- 核对「产品结构 · 不同价格段销售数量占比」的销量
--
-- 全部只读，可反复执行。每一步下面写了预期值和不符时该查什么。
--
-- 页面上这张图的口径：
--   销量 = dwd_ebay_sku_analysis_order.purchase_quantity，按 payment_time 归月，
--          不分站点、不分店铺，不减退货（与 eBay 补货2.0 一致）
--   档位 = dws_ebay_sku_unit_price 同月该SKU的 SUM(总交易额)/SUM(总交易量) 落档
--   占比的分母只算「两边都有的SKU」，配不上档位的销量不入任何一档
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SET @year = '2026';


-- ============================================================================
-- 【1】各月总销量 —— 这是最外层的数，页面覆盖率的分母
--
-- 用它和 eBay 补货2.0 页面对数：那个页面算 sales_qty_30d 用的是同一张表、
-- 同一个 purchase_quantity，只是窗口不同。
-- ============================================================================
SELECT DATE_FORMAT(payment_time,'%Y-%m')      AS 月份,
       COUNT(*)                               AS 订单行数,
       COUNT(DISTINCT platform_order_no)      AS 去重订单数,
       COUNT(DISTINCT inventory_sku)          AS 去重SKU数,
       SUM(purchase_quantity)                 AS 销量,
       SUM(refund_quantity)                   AS 退货量_未从销量中扣除
FROM dwd_ebay_sku_analysis_order
WHERE payment_time >= CONCAT(@year,'-01-01') AND payment_time < CONCAT(@year+1,'-01-01')
GROUP BY 1 ORDER BY 1;


-- ============================================================================
-- 【2】各月各档位的销量与占比 —— 与页面上的柱子逐格对照
--
-- 这段就是接口里那段SQL的等价写法，只是把分档从Python搬到了CASE里。
-- 档位界限 5/20/50/100/200/500，左闭右开，与页面完全一致。
-- 预期：每个月 占比 一列相加 = 100%
-- ============================================================================
WITH sku_price AS (
    -- 档位先聚到SKU级再join：单价表是按 月×店铺×SKU 存的，
    -- 按店铺行直接join会让订单行按店铺数翻倍。
    SELECT stat_month, sku, SUM(total_amount)/NULLIF(SUM(total_qty),0) AS unit_price
    FROM dws_ebay_sku_unit_price GROUP BY stat_month, sku HAVING SUM(total_qty) > 0
),
sales AS (
    SELECT DATE_FORMAT(payment_time,'%Y-%m') AS m, TRIM(inventory_sku) AS sku,
           SUM(purchase_quantity) AS qty, COUNT(*) AS order_rows
    FROM dwd_ebay_sku_analysis_order
    WHERE payment_time IS NOT NULL AND TRIM(IFNULL(inventory_sku,'')) <> ''
    GROUP BY 1, 2
),
tiered AS (
    SELECT s.m, s.sku, s.qty, s.order_rows,
           CASE WHEN p.unit_price IS NULL      THEN 0
                WHEN p.unit_price <   5        THEN 1
                WHEN p.unit_price <  20        THEN 2
                WHEN p.unit_price <  50        THEN 3
                WHEN p.unit_price < 100        THEN 4
                WHEN p.unit_price < 200        THEN 5
                WHEN p.unit_price < 500        THEN 6
                ELSE 7 END AS tier_no
    FROM sales s LEFT JOIN sku_price p ON p.stat_month = s.m AND p.sku = s.sku
),
-- 分母单独算：窗口函数不能和 GROUP BY 混用（ONLY_FULL_GROUP_BY 会拒绝），
-- 先把每月「有档位的销量合计」算出来再join。
matched AS (
    SELECT m, SUM(qty) AS matched_qty FROM tiered WHERE tier_no > 0 GROUP BY m
)
SELECT t.m AS 月份,
       CASE t.tier_no WHEN 0 THEN '(无档位，不计入占比)' WHEN 1 THEN '0-5' WHEN 2 THEN '5-20'
            WHEN 3 THEN '20-50' WHEN 4 THEN '50-100' WHEN 5 THEN '100-200'
            WHEN 6 THEN '200-500' ELSE '500以上' END AS 价格档,
       SUM(t.qty)        AS 销量,
       SUM(t.order_rows) AS 订单行数,
       COUNT(*)          AS SKU数,
       -- 无档位那行不在分母里，给它算占比会误导，直接留空。
       CASE WHEN t.tier_no > 0
            THEN ROUND(SUM(t.qty) * 100 / NULLIF(mt.matched_qty, 0), 1) END AS 占比
FROM tiered t LEFT JOIN matched mt ON mt.m = t.m
WHERE t.m LIKE CONCAT(@year,'-%')
GROUP BY t.m, t.tier_no, mt.matched_qty ORDER BY t.m, t.tier_no;


-- ============================================================================
-- 【3】覆盖率 —— 页面图下那行注记的来源
--
-- 预期：43%~50%。低于这个区间说明单价表覆盖的SKU变少了，
-- 去查飞书不良交易刊登表当月是不是少同步了批次。
-- ============================================================================
WITH sku_price AS (
    SELECT stat_month, sku FROM dws_ebay_sku_unit_price
    GROUP BY stat_month, sku HAVING SUM(total_qty) > 0
),
sales AS (
    SELECT DATE_FORMAT(payment_time,'%Y-%m') AS m, TRIM(inventory_sku) AS sku,
           SUM(purchase_quantity) AS qty
    FROM dwd_ebay_sku_analysis_order
    WHERE payment_time IS NOT NULL AND TRIM(IFNULL(inventory_sku,'')) <> ''
    GROUP BY 1, 2
)
SELECT s.m AS 月份,
       SUM(s.qty)                                              AS 总销量,
       SUM(CASE WHEN p.sku IS NOT NULL THEN s.qty ELSE 0 END)  AS 有档位销量,
       ROUND(SUM(CASE WHEN p.sku IS NOT NULL THEN s.qty ELSE 0 END) * 100 / SUM(s.qty), 1) AS 覆盖率,
       COUNT(*)                                                AS 订单SKU数,
       SUM(p.sku IS NOT NULL)                                  AS 有档位SKU数
FROM sales s LEFT JOIN sku_price p ON p.stat_month = s.m AND p.sku = s.sku
WHERE s.m LIKE CONCAT(@year,'-%')
GROUP BY s.m ORDER BY s.m;


-- ============================================================================
-- 【4】抽一个SKU从头核到尾 —— 最直接的验证方式
--
-- 换成你想查的SKU和月份。三段输出应当能自洽：
--   订单明细逐行相加 = 汇总销量
--   单价表的 金额/数量 = 单价，落在哪一档
--   该SKU的销量就应当计入【2】里那一档
-- ============================================================================
SET @sku = 'FRD-70361-4-0734';
SET @month = '2026-09';

-- 4.1 订单明细（销量的来源，逐行可数）
SELECT payment_time AS 付款时间, platform_order_no AS 订单号, site_name AS 站点,
       purchase_quantity AS 数量, refund_quantity AS 退货, paid_amount_cny AS 金额人民币
FROM dwd_ebay_sku_analysis_order
WHERE TRIM(inventory_sku) = @sku AND DATE_FORMAT(payment_time,'%Y-%m') = @month
ORDER BY payment_time;

-- 4.2 该SKU当月汇总
SELECT @sku AS SKU, @month AS 月份,
       COUNT(*) AS 订单行数, COUNT(DISTINCT platform_order_no) AS 去重订单数,
       SUM(purchase_quantity) AS 销量
FROM dwd_ebay_sku_analysis_order
WHERE TRIM(inventory_sku) = @sku AND DATE_FORMAT(payment_time,'%Y-%m') = @month;

-- 4.3 该SKU当月的档位（分店铺的原始行 + 聚到SKU级后的单价）
SELECT shop AS 店铺, reg_date AS 来源批次, total_amount AS 总交易额,
       total_qty AS 总交易量, ROUND(unit_price,4) AS 该店铺单价, tier_no AS 该店铺档位
FROM dws_ebay_sku_unit_price WHERE sku = @sku AND stat_month = @month ORDER BY shop;

SELECT @sku AS SKU, @month AS 月份,
       SUM(total_amount) AS 金额合计, SUM(total_qty) AS 数量合计,
       ROUND(SUM(total_amount)/NULLIF(SUM(total_qty),0), 4) AS SKU级单价,
       CASE WHEN SUM(total_amount)/NULLIF(SUM(total_qty),0) <   5 THEN '0-5'
            WHEN SUM(total_amount)/NULLIF(SUM(total_qty),0) <  20 THEN '5-20'
            WHEN SUM(total_amount)/NULLIF(SUM(total_qty),0) <  50 THEN '20-50'
            WHEN SUM(total_amount)/NULLIF(SUM(total_qty),0) < 100 THEN '50-100'
            WHEN SUM(total_amount)/NULLIF(SUM(total_qty),0) < 200 THEN '100-200'
            WHEN SUM(total_amount)/NULLIF(SUM(total_qty),0) < 500 THEN '200-500'
            ELSE '500以上' END AS 落档
FROM dws_ebay_sku_unit_price WHERE sku = @sku AND stat_month = @month;


-- ============================================================================
-- 【5】与 eBay 补货2.0 对数
--
-- 补货2.0 的近30天销量算法：以订单表里最大付款日为锚点，往前30天。
-- 这里按同一算法算一遍总量，页面上把各SKU的「近30天销量」加起来应当对得上。
-- 注意补货2.0 是分站点+SKU展示的，求和时别漏站点。
-- ============================================================================
WITH anchor AS (
    SELECT COALESCE(DATE(MAX(payment_time)), CURDATE()) AS anchor_date
    FROM dwd_ebay_sku_analysis_order
)
SELECT a.anchor_date AS 锚点日期,
       DATE_SUB(a.anchor_date, INTERVAL 29 DAY) AS 窗口起,
       SUM(o.purchase_quantity) AS 近30天销量合计,
       COUNT(DISTINCT o.inventory_sku) AS 涉及SKU数
FROM dwd_ebay_sku_analysis_order o CROSS JOIN anchor a
WHERE o.payment_time >= DATE_SUB(a.anchor_date, INTERVAL 29 DAY)
  AND o.payment_time <  DATE_ADD(a.anchor_date, INTERVAL 1 DAY)
GROUP BY a.anchor_date;


-- ============================================================================
-- 【6】数据完整性自检
--
-- 预期：三个数都是 0。
--   付款时间为空  —— 这些行不会进任何月份，等于白丢
--   SKU为空      —— 同上
--   数量非正      —— 退款/作废单应当体现在 refund_quantity，而不是负的购买数量
-- ============================================================================
SELECT SUM(payment_time IS NULL)                        AS 付款时间为空,
       SUM(TRIM(IFNULL(inventory_sku,'')) = '')         AS SKU为空,
       SUM(purchase_quantity IS NULL OR purchase_quantity <= 0) AS 数量非正
FROM dwd_ebay_sku_analysis_order
WHERE payment_time IS NULL
   OR payment_time >= CONCAT(@year,'-01-01');
