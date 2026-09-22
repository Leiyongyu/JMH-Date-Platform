-- 历史最大月销：完整复现页面取值（可直接在 date-project 库执行）
WITH 
        
        inventory_snapshot AS (
            SELECT i.sync_batch_id,i.snapshot_date,MAX(i.pulled_at) inventory_pulled_at
            FROM ods_lingxing_inventory_detail_weekly i
            WHERE EXISTS (
                SELECT 1 FROM ops_weekly_export_file f
                WHERE f.export_code='weekly_inventory_bin'
                  AND f.sync_batch_id=i.sync_batch_id AND f.snapshot_date=i.snapshot_date
                  AND f.status IN ('SUCCESS','DELETE_PENDING','DELETED')
            )
            GROUP BY i.sync_batch_id,i.snapshot_date
            ORDER BY inventory_pulled_at DESC,i.snapshot_date DESC,i.sync_batch_id DESC
            LIMIT 1
        )
    ,
        inventory_ranked AS (
            SELECT i.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY i.wid,i.product_id
                       ORDER BY (i.product_total IS NOT NULL) DESC,i.product_total DESC,
                                i.seller_id DESC,i.id DESC
                   ) inventory_rank
            FROM ods_lingxing_inventory_detail_weekly i
            JOIN inventory_snapshot b
              ON b.sync_batch_id=i.sync_batch_id AND b.snapshot_date=i.snapshot_date
            WHERE i.wid IN (18674,18675,18676,18699,18700,18701,18702)
        ),
        inventory_source AS (
            SELECT CASE WHEN wid IN (18674,18699) THEN '德国'
                        WHEN wid IN (18675,18702) THEN '英国'
                        WHEN wid IN (18676,18700,18701) THEN '美国' END site,
                   TRIM(sku) sku,
                   CASE WHEN wid IN (18674,18675,18676)
                        THEN COALESCE(quantity_receive,0) ELSE 0 END chengdu_in_transit_quantity,
                   CASE WHEN wid IN (18674,18675,18676)
                        THEN COALESCE(product_valid_num,0) ELSE 0 END chengdu_sellable_quantity,
                   CASE WHEN wid IN (18699,18700,18701,18702)
                        THEN COALESCE(product_onway,0) ELSE 0 END overseas_in_transit_quantity,
                   CASE WHEN wid IN (18699,18700,18701,18702)
                        THEN COALESCE(product_valid_num,0) ELSE 0 END overseas_sellable_quantity,
                   COALESCE(product_total,0) pending_outbound_quantity
            FROM inventory_ranked
            WHERE inventory_rank=1 AND sku IS NOT NULL AND TRIM(sku)<>''
        ),
        inventory_summary AS (
            SELECT site,sku,
                   SUM(chengdu_in_transit_quantity) chengdu_in_transit_quantity,
                   SUM(chengdu_sellable_quantity) chengdu_sellable_quantity,
                   SUM(overseas_in_transit_quantity) overseas_in_transit_quantity,
                   SUM(overseas_sellable_quantity) overseas_sellable_quantity,
                   SUM(pending_outbound_quantity) pending_outbound_quantity
            FROM inventory_source GROUP BY site,sku
        )
    ,
monthly AS (
    -- 第1步：只取当前库存里还有的站点+完整SKU，按自然月汇总销量。
    -- 排除发货状态含已作废的订单；payment_time < 当月1号 → 当月未结束不参与。
    SELECT inventory.site, inventory.sku,
           DATE_FORMAT(source.payment_time,'%Y-%m') stat_month,
           SUM(source.purchase_quantity) sales_qty
    FROM inventory_summary inventory
    JOIN dwd_ebay_sku_analysis_order source
      ON CONVERT(source.site_name USING utf8mb4) COLLATE utf8mb4_unicode_ci
       = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
     AND CONVERT(source.inventory_sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
       = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
    WHERE source.payment_time < DATE_FORMAT(CURDATE(),'%Y-%m-01')
      AND COALESCE(source.shipping_status,'') NOT LIKE '%已作废%'
    GROUP BY inventory.site, inventory.sku, DATE_FORMAT(source.payment_time,'%Y-%m')
),
keyed AS (
    -- 第2步：算合并键。SKU第二段是纯数字→按站点+中间码合并，否则退回完整SKU。
    SELECT m.*,
           CASE WHEN LOCATE('-',m.sku)>0
                 AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(m.sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','') REGEXP '^[0-9]+$'
                THEN 'MIDDLE' ELSE 'SKU' END product_key_type,
           CASE WHEN LOCATE('-',m.sku)>0
                 AND REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(m.sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','') REGEXP '^[0-9]+$'
                THEN REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(m.sku,'-',2),'-',-1),
                                    '^[[:space:]]+|[[:space:]]+$','')
                ELSE UPPER(TRIM(m.sku)) END product_key
    FROM monthly m
),
per_month AS (
    -- 第3步：同一中间码下多个SKU，在同一个自然月里先相加。
    SELECT site, product_key_type, product_key, stat_month, SUM(sales_qty) month_qty
    FROM keyed GROUP BY site, product_key_type, product_key, stat_month
),
computed AS (
    -- 第4步：跨月取最大 —— 即这个产品卖得最好的一个月卖了多少。
    SELECT site, product_key_type, product_key,
           MAX(month_qty) orders_max,
           SUBSTRING_INDEX(GROUP_CONCAT(stat_month ORDER BY month_qty DESC, stat_month ASC),',',1) orders_peak_month
    FROM per_month GROUP BY site, product_key_type, product_key
)
-- 第5步：与高水位取大（只升不降）。高水位里有、订单表里没有的也要出现。
SELECT COALESCE(c.site,h.site) 站点,
       COALESCE(c.product_key_type,h.product_key_type) 键类型,
       COALESCE(c.product_key,h.product_key) 中间码或SKU,
       GREATEST(COALESCE(c.orders_max,0), COALESCE(h.max_monthly_sales,0)) 历史最大月销,
       CASE WHEN COALESCE(h.max_monthly_sales,0) > COALESCE(c.orders_max,0)
            THEN 'HISTORY_HIGH_WATER' ELSE 'ORDERS' END 取值来源,
       c.orders_max 订单表算出, c.orders_peak_month 订单表峰值月,
       h.max_monthly_sales 高水位值, h.peak_month 高水位峰值月
FROM computed c
LEFT JOIN dws_ebay_inventory_max_monthly_sales h
  ON h.site=c.site AND h.product_key_type=c.product_key_type AND h.product_key=c.product_key
UNION
SELECT h.site,h.product_key_type,h.product_key,h.max_monthly_sales,'HISTORY_HIGH_WATER',
       NULL,NULL,h.max_monthly_sales,h.peak_month
FROM dws_ebay_inventory_max_monthly_sales h
LEFT JOIN computed c
  ON h.site=c.site AND h.product_key_type=c.product_key_type AND h.product_key=c.product_key
WHERE c.product_key IS NULL
ORDER BY 历史最大月销 DESC
