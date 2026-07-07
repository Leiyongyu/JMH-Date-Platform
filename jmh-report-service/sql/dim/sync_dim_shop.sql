-- sync_dim_shop.sql
-- 全量覆盖同步：从 ERP 业务库 shop_list → 报表库 dim_shop
-- 来源表字段：store_id, sid, store_name, platform_code, platform_name, currency, is_sync, status, country_code

TRUNCATE TABLE jmh_report.dim_shop;

INSERT INTO jmh_report.dim_shop (
  sid,
  platform,
  shop_name,
  shop_prefix,
  country_code,
  country_name,
  marketplace,
  enabled,
  source_system,
  source_table
)
SELECT
  sid,
  CASE
    WHEN platform_code = '10001' THEN 'AMZ'
    WHEN platform_code = '10002' THEN 'EBAY'
    ELSE platform_name
  END AS platform,
  store_name AS shop_name,
  SUBSTRING_INDEX(store_name, '-', 1) AS shop_prefix,
  country_code,
  CASE
    WHEN country_code = 'US' THEN '美国'
    WHEN country_code = 'GB' THEN '英国'
    WHEN country_code = 'DE' THEN '德国'
    WHEN country_code = 'FR' THEN '法国'
    WHEN country_code = 'ES' THEN '西班牙'
    WHEN country_code = 'IT' THEN '意大利'
    WHEN country_code = 'CA' THEN '加拿大'
    WHEN country_code = 'MX' THEN '墨西哥'
    WHEN country_code = 'PL' THEN '波兰'
    ELSE country_code
  END AS country_name,
  NULL AS marketplace,
  status AS enabled,
  'erp' AS source_system,
  'shop_list' AS source_table
FROM jmh_data_platform.shop_list
WHERE store_name IS NOT NULL
  AND TRIM(store_name) <> '';
