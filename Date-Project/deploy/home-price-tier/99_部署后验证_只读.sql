-- 先确认00中的10张表均存在，再执行本文件。
USE `date-project`;
SELECT currency_code,my_rate,rate_org FROM dim_lingxing_currency_month
WHERE rate_month=DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','+08:00'),'%Y-%m')
ORDER BY currency_code;
SELECT id,row_count,shop_count,sync_batch_id,pulled_at,published_at FROM ods_lingxing_amz_listing_state;
SELECT sync_batch_id,COUNT(*) actual_rows FROM ods_lingxing_amz_listing_latest GROUP BY sync_batch_id;
SELECT COUNT(*) active_amz_rows FROM ods_lingxing_amz_listing_latest WHERE status=1 AND is_delete=0;
SELECT s.seller_account,s.row_count,COALESCE(r.actual_rows,0) actual_rows,s.pulled_at,
 CASE WHEN s.row_count=COALESCE(r.actual_rows,0) THEN '数量一致' ELSE '数量不一致' END check_result
FROM ods_ebay_store_listing_state s
LEFT JOIN (
 SELECT seller_user_id,sync_batch_id,COUNT(*) actual_rows
 FROM ods_ebay_store_listing_latest GROUP BY seller_user_id,sync_batch_id
) r ON r.seller_user_id=s.seller_user_id AND r.sync_batch_id=s.sync_batch_id;
SELECT platform,report_id,generated_at,
 JSON_UNQUOTE(JSON_EXTRACT(summary_json,'$.target_currency')) target_currency,
 JSON_UNQUOTE(JSON_EXTRACT(summary_json,'$.total_sku_count')) sku_count
FROM dws_listing_cny_price_report WHERE platform='amz'
UNION ALL
SELECT platform,report_id,generated_at,
 JSON_UNQUOTE(JSON_EXTRACT(summary_json,'$.target_currency')),
 JSON_UNQUOTE(JSON_EXTRACT(summary_json,'$.total_sku_count'))
FROM dws_ebay_usd_price_report WHERE platform='ebay';
-- 应有amz/CNY和ebay/USD；没行说明尚未刷新生成。只加总SITE，不能与SHOP混加。
SELECT platform,tier_no,SUM(sku_count) sku_count FROM dws_listing_cny_price_tier
WHERE platform='amz' AND scope='SITE' GROUP BY platform,tier_no
UNION ALL
SELECT platform,tier_no,SUM(sku_count) FROM dws_ebay_usd_price_tier
WHERE platform='ebay' AND scope='SITE' GROUP BY platform,tier_no;
