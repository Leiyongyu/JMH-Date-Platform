-- ============================================================================
-- 回填「历史最大月销」高水位
--
-- 口径就一句话：
--   历史最大月销 = 各统计日期的「近30天销量」，按 站点+中间码 取最大值。
--
-- 页面每次「重新计算」观测当前这一个窗口并写进高水位；本脚本把之前各统计
-- 日期已经观测到的值一次性补齐。因为拉取是每周一次、每批只观测一次，
-- 这些快照就是全部观测，不需要再从订单表滑动补窗口。
--
-- 可以用眼睛验：在页面上把统计日期从最早翻到今天，记下「近30天销量」的
-- 最大值，应当等于今天这行的「历史最大月销」。
--
--   合并键 = 站点 + 中间码（SKU第二段是纯数字时），否则退回站点 + 完整SKU
--   窗口右端 = 该统计日期（窗口为 [统计日期-30, 统计日期)）
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
WITH observed AS (
    -- 每个统计日期、每个合并键的观测值。
    -- EXCEL_IMPORT 的历史行是逐SKU的，同中间码要先相加；PAGE_REFRESH 的行
    -- 本身已是合并行，一个键只有一行，相加不影响。
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
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d'))
                    AS DECIMAL(30,6))) AS window_qty
    FROM ebay_inventory_detail_history h
    JOIN ebay_inventory_pivot_snapshot s ON s.id = h.snapshot_id
    WHERE JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d') IS NOT NULL
      AND JSON_TYPE(JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d')) <> 'NULL'
      AND s.stat_date <= CURDATE()
      AND h.site IS NOT NULL AND TRIM(h.site) <> ''
      AND h.sku  IS NOT NULL AND TRIM(h.sku)  <> ''
    GROUP BY 1, 2, 3, s.stat_date
),
best AS (
    -- 取最大；并列时取最早的统计日期，保证重复执行结果稳定。
    -- 别名不能叫 peak_window_end：INSERT...SELECT 里会与目标表同名列冲突（1052）。
    SELECT site, product_key_type, product_key,
           window_qty AS max_qty, window_end AS peak_end
    FROM (SELECT o.*, ROW_NUMBER() OVER (
                        PARTITION BY o.site, o.product_key_type, o.product_key
                        ORDER BY o.window_qty DESC, o.window_end ASC) AS rn
          FROM observed o) ranked
    WHERE rn = 1
)
SELECT best.site, best.product_key_type, best.product_key,
       best.max_qty, best.peak_end, 'CALCULATED'
FROM best
WHERE best.max_qty > 0
ON DUPLICATE KEY UPDATE
    -- 用 >= 而不是 >：值相等时也把窗口补上，旧口径留下的行只有数值没有窗口。
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
