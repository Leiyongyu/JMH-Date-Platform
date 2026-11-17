-- 核对「历史最大月销」取值 —— 在 date-project 库执行
--
-- 页面取值 = MAX(本次观测, 高水位)
--   本次观测 = 近30天销量，窗口 [今天-30, 今天)，不含当天，排除已作废；
--              按 站点+中间码 合并（SKU第二段是纯数字时），否则退回完整SKU
--   高水位   = dws_ebay_inventory_max_monthly_sales，只升不降，由
--              04_回填历史最大月销.sql 扫描全部历史滑动窗口写入
--
-- 想查单个商品，把最后的 WHERE 注释放开。

WITH observed AS (
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
           SUM(o.purchase_quantity) AS observed_qty
    FROM dwd_ebay_sku_analysis_order o
    WHERE COALESCE(o.shipping_status,'') NOT LIKE '%已作废%'
      AND o.payment_time >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
      AND o.payment_time <  CURDATE()
    GROUP BY 1, 2, 3
)
SELECT COALESCE(o.site, h.site)                         AS 站点,
       COALESCE(o.product_key, h.product_key)           AS 中间码或SKU,
       GREATEST(COALESCE(o.observed_qty,0),
                COALESCE(h.max_monthly_sales,0))        AS 历史最大月销,
       CASE WHEN COALESCE(h.max_monthly_sales,0) > COALESCE(o.observed_qty,0)
            THEN 'HISTORY_HIGH_WATER' ELSE 'ORDERS' END AS 取值来源,
       o.observed_qty                                   AS 本次观测_近30天,
       h.max_monthly_sales                              AS 高水位值,
       DATE_SUB(h.peak_window_end, INTERVAL 30 DAY)     AS 高水位窗口左端,
       h.peak_window_end                                AS 高水位窗口右端,
       h.value_source                                   AS 高水位来源
FROM observed o
LEFT JOIN dws_ebay_inventory_max_monthly_sales h
  ON h.site = o.site AND h.product_key_type = o.product_key_type
 AND h.product_key = o.product_key
UNION
SELECT h.site, h.product_key,
       h.max_monthly_sales, 'HISTORY_HIGH_WATER',
       NULL, h.max_monthly_sales,
       DATE_SUB(h.peak_window_end, INTERVAL 30 DAY), h.peak_window_end, h.value_source
FROM dws_ebay_inventory_max_monthly_sales h
LEFT JOIN observed o
  ON h.site = o.site AND h.product_key_type = o.product_key_type
 AND h.product_key = o.product_key
WHERE o.product_key IS NULL
-- WHERE COALESCE(o.product_key, h.product_key) = '10756'
ORDER BY 历史最大月销 DESC;
