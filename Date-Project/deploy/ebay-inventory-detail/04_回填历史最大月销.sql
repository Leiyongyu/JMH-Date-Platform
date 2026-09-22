-- ============================================================================
-- 回填「历史最大月销」高水位 —— 取历史上所有30天观测里的最大值
--
-- 为什么需要：页面每次「重新计算」只观测当前这一个窗口 [统计日-30, 统计日)。
-- 之前的窗口不会被看到，本脚本把它们一次性补齐。
--
-- 有两个数据源，缺一不可，取两者最大：
--
--   源A｜历史快照 ebay_inventory_detail_history 里每个统计日期记下的
--        sales_qty_30d。覆盖 2025-10 起的每周观测。EXCEL_IMPORT 那批来自
--        业务方自己的周报表格，是订单表算不出来的独立来源
--        （实测中间码20192德国：快照2026-09-07记55，订单表同窗口只有31）。
--        观测值对应的窗口右端就是该统计日期。
--
--   源B｜订单表 dwd_ebay_sku_analysis_order 的滑动30天窗口。只覆盖
--        2026-05 起，但粒度到天，能补上两次周快照之间的峰值。
--
-- 只用源B会漏掉2025-10~2026-04整整7个月；只用源A会漏掉周与周之间的窗口。
--
-- 口径：窗口 = [右端-30, 右端)，不含右端当天；右端不晚于今天；
--       排除发货状态含「已作废」的订单；
--       合并键 = 站点 + 中间码（SKU第二段是纯数字时），否则退回站点 + 完整SKU。
--
-- 只升不降：GREATEST 保证低于已存值的不覆盖。**可重复执行**。
--
-- 执行前请先执行 migrations/20260922_max_monthly_sales_rolling_window.sql
-- （新增 peak_window_end 列）。该迁移只加列不删列。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4;

INSERT INTO dws_ebay_inventory_max_monthly_sales
    (site, product_key_type, product_key, max_monthly_sales, peak_window_end, value_source)
WITH src AS (
    -- 源B：每笔订单归到合并键与自然日；已作废不计入。
    SELECT o.site_name AS site,
           CASE WHEN LOCATE('-', o.inventory_sku) > 0
                 AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(o.inventory_sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','') REGEXP '^[0-9]+$'
                THEN 'MIDDLE' ELSE 'SKU' END AS product_key_type,
           CASE WHEN LOCATE('-', o.inventory_sku) > 0
                 AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(o.inventory_sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','') REGEXP '^[0-9]+$'
                THEN REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(o.inventory_sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','')
                ELSE UPPER(TRIM(o.inventory_sku)) END AS product_key,
           DATE(o.payment_time) AS sold_on,
           o.purchase_quantity  AS qty
    FROM dwd_ebay_sku_analysis_order o
    WHERE COALESCE(o.shipping_status,'') NOT LIKE '%已作废%'
      AND o.inventory_sku IS NOT NULL AND TRIM(o.inventory_sku) <> ''
      AND o.site_name IS NOT NULL AND TRIM(o.site_name) <> ''
),
daily AS (
    -- 先压到"键 + 自然日"一行，把窗口函数的输入量降下来。
    SELECT site, product_key_type, product_key, sold_on, SUM(qty) AS day_qty
    FROM src
    GROUP BY site, product_key_type, product_key, sold_on
),
rolling AS (
    -- RANGE 帧按日期取前29天到当天，即窗口 [sold_on+1-30, sold_on+1)。
    -- 用窗口函数而不是自连接：MySQL的CTE无索引，自连接是嵌套循环，会慢三个数量级。
    SELECT site, product_key_type, product_key,
           sold_on + INTERVAL 1 DAY AS window_end,
           SUM(day_qty) OVER (
               PARTITION BY site, product_key_type, product_key
               ORDER BY sold_on
               RANGE BETWEEN INTERVAL 29 DAY PRECEDING AND CURRENT ROW
           ) AS window_qty
    FROM daily
),
snapshot_observed AS (
    -- 源A：历史快照里每个统计日期已经记下的近30天销量。
    -- 快照行本身就是合并后的产品行，sales_qty_30d 已是合并口径，直接取用。
    -- 同一统计日可能有多条留底行（历史导入允许重复），用 MAX 去重。
    SELECT h.site AS site,
           CASE WHEN LOCATE('-', h.sku) > 0
                 AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(h.sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','') REGEXP '^[0-9]+$'
                THEN 'MIDDLE' ELSE 'SKU' END AS product_key_type,
           CASE WHEN LOCATE('-', h.sku) > 0
                 AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(h.sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','') REGEXP '^[0-9]+$'
                THEN REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(h.sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','')
                ELSE UPPER(TRIM(h.sku)) END AS product_key,
           s.stat_date AS window_end,
           MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d'))
                    AS DECIMAL(30,6))) AS window_qty
    FROM ebay_inventory_detail_history h
    JOIN ebay_inventory_pivot_snapshot s ON s.id = h.snapshot_id
    WHERE JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d') IS NOT NULL
      AND JSON_TYPE(JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d')) <> 'NULL'
      AND h.site IS NOT NULL AND TRIM(h.site) <> ''
      AND h.sku  IS NOT NULL AND TRIM(h.sku)  <> ''
    GROUP BY 1, 2, 3, s.stat_date
),
combined AS (
    SELECT site, product_key_type, product_key, window_end, window_qty FROM rolling
    UNION ALL
    SELECT site, product_key_type, product_key, window_end, window_qty FROM snapshot_observed
),
best AS (
    -- 两源合起来选胜出行：销量最高，并列时取最早的窗口，保证重复执行结果稳定。
    -- 不用 MIN(CASE WHEN ... THEN window_end END)：MySQL 会把 NULL 分支推导成
    -- 零日期，严格模式下报 1292。
    -- 别名不能叫 peak_window_end：INSERT...SELECT 里会与目标表同名列冲突（1052）。
    SELECT site, product_key_type, product_key,
           window_qty AS max_qty, window_end AS peak_end
    FROM (SELECT c.*, ROW_NUMBER() OVER (
                        PARTITION BY c.site, c.product_key_type, c.product_key
                        ORDER BY c.window_qty DESC, c.window_end ASC) AS rn
          FROM combined c
          WHERE c.window_end <= CURDATE()) ranked
    WHERE rn = 1
)
SELECT best.site, best.product_key_type, best.product_key,
       best.max_qty, best.peak_end, 'CALCULATED'
FROM best
WHERE best.max_qty > 0
ON DUPLICATE KEY UPDATE
    -- 用 >= 而不是 >：值相等时也把窗口补上。旧口径（自然月）留下的行只有数值、
    -- 没有窗口，相等时若不写就会一直空着。计算结果确定，重复执行仍然幂等。
    peak_window_end = IF(VALUES(max_monthly_sales) >= max_monthly_sales,
                         VALUES(peak_window_end), peak_window_end),
    value_source    = IF(VALUES(max_monthly_sales) >= max_monthly_sales,
                         'CALCULATED', value_source),
    max_monthly_sales = GREATEST(max_monthly_sales, VALUES(max_monthly_sales));


-- ============================================================================
-- 执行后的只读验证
-- ============================================================================

-- 总量与来源分布
SELECT COUNT(*) AS 高水位行数,
       SUM(value_source = 'CALCULATED') AS 算出的,
       SUM(value_source = 'SEEDED')     AS 种入的,
       SUM(peak_window_end IS NULL)     AS 无峰值窗口,
       MAX(max_monthly_sales)           AS 最大值
FROM dws_ebay_inventory_max_monthly_sales;

-- 峰值窗口右端不应晚于今天
SELECT MIN(peak_window_end) AS 最早峰值窗口右端,
       MAX(peak_window_end) AS 最晚峰值窗口右端,
       SUM(peak_window_end > CURDATE()) AS 超出今天的行数_应为0
FROM dws_ebay_inventory_max_monthly_sales;

-- 抽查前10名
SELECT site AS 站点, product_key AS 中间码或SKU, max_monthly_sales AS 历史最大月销,
       peak_window_end AS 峰值窗口右端,
       DATE_SUB(peak_window_end, INTERVAL 30 DAY) AS 峰值窗口左端, value_source AS 来源
FROM dws_ebay_inventory_max_monthly_sales
ORDER BY max_monthly_sales DESC LIMIT 10;
