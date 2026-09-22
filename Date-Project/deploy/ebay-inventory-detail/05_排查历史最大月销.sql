-- ============================================================================
-- 排查：页面「历史最大月销」等于当天「近30天销量」，说明高水位没被回填补上。
-- 全部只读，可以反复执行。每一步下面写了「预期」和「不符怎么办」。
-- 用 20192 举例，换别的中间码改 @key 即可。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4;
SET @key = '20192';


-- 【1】高水位表里这个中间码现在存的是什么
--
-- 预期：德国 47（峰值窗口右端 2025-12-08）、英国 21（2026-08-17），来源 CALCULATED。
-- 若 peak_window_end 为空、或等于今天 —— 这行是「重新计算」当场新建的，
--   说明回填没跑过、或跑在 DELETE 之前又被删掉了 → 直接重跑 04（幂等）。
SELECT site                                        AS 站点,
       product_key_type                            AS 键类型,
       product_key                                 AS 中间码,
       max_monthly_sales                           AS 历史最大月销,
       peak_window_end                             AS 峰值窗口右端,
       DATE_SUB(peak_window_end, INTERVAL 30 DAY)  AS 峰值窗口左端,
       value_source                                AS 来源,
       updated_at                                  AS 最后更新
FROM dws_ebay_inventory_max_monthly_sales
WHERE product_key = @key
ORDER BY site;


-- 【2】历史快照里这个中间码每个统计日期的近30天销量（回填的唯一数据源）
--
-- 预期：德国最大 47 在 2025-12-08，英国最大 21 在 2026-08-17，
--       且 2026-09-07 这行已不存在（坏批次已删）。
-- 德国根本没有 47 那行 → 部署机历史快照比本地少，问题在数据不在SQL，看第3步。
-- 2026-09-07 还在且德国是 55 → 坏批次没删干净，回填会把 55 又抬回去。
SELECT s.stat_date     AS 统计日期,
       h.site          AS 站点,
       s.trigger_type  AS 触发方式,
       COUNT(*)        AS 合并了几个SKU,
       SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(h.item_json,'$.values.sales_qty_30d'))
                AS DECIMAL(30,6))) AS 近30天销量
FROM ebay_inventory_detail_history h
JOIN ebay_inventory_pivot_snapshot s ON s.id = h.snapshot_id
WHERE LOCATE('-', h.sku) > 0
  AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(h.sku,'-',2),'-',-1),
                     '^[[:space:]]+|[[:space:]]+$','') = @key
GROUP BY s.stat_date, h.site, s.trigger_type
ORDER BY 近30天销量 DESC, s.stat_date;


-- 【3】部署机的历史快照覆盖了哪些统计日期
--
-- 预期：最早 2025-10 前后，十几个统计日期，每个日期只有 1 份快照。
-- 最早只到 2026 年 → 历史快照没导全，回填补不出 2025-12-08 的 47。
-- 同一个 stat_date 出现多份 → 有脏快照，点一次「重新计算」会自动清掉。
SELECT s.stat_date          AS 统计日期,
       COUNT(DISTINCT s.id) AS 快照份数,
       MIN(s.trigger_type)  AS 触发方式,
       SUM(s.item_count)    AS 明细行数,
       MAX(s.generated_at)  AS 生成时间
FROM ebay_inventory_pivot_snapshot s
GROUP BY s.stat_date
ORDER BY s.stat_date;


-- 【4】坏批次 2026-09-07 是否残留
--
-- 预期：三个数都是 0。任何一个不为 0，先把之前那四条 DELETE 补执行完再回填。
SELECT (SELECT COUNT(*) FROM ebay_inventory_pivot_snapshot
         WHERE stat_date = '2026-09-07')                                AS 残留快照,
       (SELECT COUNT(*) FROM dws_ebay_inventory_max_monthly_sales
         WHERE peak_window_end = '2026-09-07')                          AS 被坏批次抬高的高水位,
       (SELECT COUNT(*) FROM dws_ebay_inventory_max_monthly_sales
         WHERE value_source = 'CALCULATED' AND peak_window_end IS NULL)  AS 算出行但无窗口_应为0;


-- 【5】回填「应该」算出什么 —— 不写库，只把结果打出来跟第1步比
--
-- 这就是 04_回填历史最大月销.sql 的 SELECT 部分原样搬过来。
-- 算出 47 而第1步是 41 → 回填没跑，重跑 04 即可（幂等）。
-- 也只算出 41   → 不是回填的问题，是历史快照缺 2025-12-08，看第3步。
WITH observed AS (
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
    SELECT site, product_key_type, product_key,
           window_qty AS max_qty, window_end AS peak_end
    FROM (SELECT o.*, ROW_NUMBER() OVER (
                        PARTITION BY o.site, o.product_key_type, o.product_key
                        ORDER BY o.window_qty DESC, o.window_end ASC) AS rn
          FROM observed o) ranked
    WHERE rn = 1
)
SELECT b.site              AS 站点,
       b.product_key       AS 中间码,
       b.max_qty           AS 回填应算出,
       b.peak_end          AS 峰值窗口右端,
       w.max_monthly_sales AS 库里现在是,
       CASE WHEN w.max_monthly_sales IS NULL     THEN '库里没有这行'
            WHEN b.max_qty > w.max_monthly_sales THEN '★ 回填没跑，重跑04'
            ELSE '一致' END AS 结论
FROM best b
LEFT JOIN dws_ebay_inventory_max_monthly_sales w
       ON w.site = b.site AND w.product_key_type = b.product_key_type
      AND w.product_key = b.product_key
WHERE b.product_key = @key;


-- 【6】全表范围的同一个比对：还有多少行「回填能算出更大值但库里偏小」
--
-- 预期：0 行。大于 0 就是回填没跑或跑漏了，重跑 04 之后这里应归零。
WITH observed AS (
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
    SELECT site, product_key_type, product_key,
           window_qty AS max_qty, window_end AS peak_end
    FROM (SELECT o.*, ROW_NUMBER() OVER (
                        PARTITION BY o.site, o.product_key_type, o.product_key
                        ORDER BY o.window_qty DESC, o.window_end ASC) AS rn
          FROM observed o) ranked
    WHERE rn = 1
)
SELECT COUNT(*)                         AS 偏小的行数_应为0,
       SUM(w.max_monthly_sales IS NULL) AS 其中库里完全没有的
FROM best b
LEFT JOIN dws_ebay_inventory_max_monthly_sales w
       ON w.site = b.site AND w.product_key_type = b.product_key_type
      AND w.product_key = b.product_key
WHERE b.max_qty > 0
  AND (w.max_monthly_sales IS NULL OR b.max_qty > w.max_monthly_sales);
