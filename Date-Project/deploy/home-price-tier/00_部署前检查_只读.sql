-- 预期10张表。前4张本轮新建，其余6张是源表依赖；不显示原始JSON或凭证。
SELECT e.table_schema,e.table_name,
 CASE WHEN t.table_name IS NULL THEN '缺表' ELSE '已存在' END table_status
FROM (
 SELECT 'date-project' table_schema,'dws_listing_cny_price_report' table_name
 UNION ALL SELECT 'date-project','dws_listing_cny_price_tier'
 UNION ALL SELECT 'date-project','dws_ebay_usd_price_report'
 UNION ALL SELECT 'date-project','dws_ebay_usd_price_tier'
 UNION ALL SELECT 'date-project','ods_lingxing_amz_listing_latest'
 UNION ALL SELECT 'date-project','ods_lingxing_amz_listing_state'
 UNION ALL SELECT 'date-project','ods_ebay_store_listing_latest'
 UNION ALL SELECT 'date-project','ods_ebay_store_listing_state'
 UNION ALL SELECT 'date-project','dim_lingxing_currency_month'
 UNION ALL SELECT 'jmh_data_platform','shop_list'
) e LEFT JOIN information_schema.tables t
 ON t.table_schema=e.table_schema AND t.table_name=e.table_name;
SELECT table_schema,table_name,column_name,column_type
FROM information_schema.columns
WHERE table_schema='date-project' AND table_name='dim_lingxing_currency_month'
 AND column_name IN ('rate_month','currency_code','my_rate','rate_org');
-- 只确认权限定义，不代表当前用户一定已获授权。
SELECT menu_id,menu_name,perms,status FROM jmh_data_platform.sys_menu
WHERE perms IN ('operations:amzReplenishment:list','operations:ebayReplenishmentV2:list');
