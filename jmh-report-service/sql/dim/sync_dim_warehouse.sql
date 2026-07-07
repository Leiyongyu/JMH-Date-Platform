-- sync_dim_warehouse.sql
-- 全量覆盖同步：从 ERP 业务库 warehouse → 报表库 dim_warehouse
-- 将 ERP type/sub_type 编码映射为统一仓库类型

TRUNCATE TABLE jmh_report.dim_warehouse;

INSERT INTO jmh_report.dim_warehouse (
  warehouse_id,
  warehouse_name,
  warehouse_type_code,
  warehouse_type,
  warehouse_type_name,
  warehouse_sub_type_code,
  warehouse_sub_type,
  warehouse_sub_type_name,
  country_code,
  is_delete,
  enabled,
  source_system,
  source_table
)
SELECT
  wid AS warehouse_id,
  name AS warehouse_name,
  type AS warehouse_type_code,
  CASE type
    WHEN 1 THEN 'LOCAL'
    WHEN 3 THEN 'OVERSEAS'
    WHEN 4 THEN 'FBA'
    WHEN 6 THEN 'AWD'
    ELSE 'UNKNOWN'
  END AS warehouse_type,
  CASE type
    WHEN 1 THEN '本地仓'
    WHEN 3 THEN '海外仓'
    WHEN 4 THEN '亚马逊平台仓'
    WHEN 6 THEN 'AWD仓'
    ELSE '未知'
  END AS warehouse_type_name,
  sub_type AS warehouse_sub_type_code,
  CASE
    WHEN type = 3 AND sub_type = 1 THEN 'NO_API_OVERSEAS'
    WHEN type = 3 AND sub_type = 2 THEN 'API_OVERSEAS'
    ELSE NULL
  END AS warehouse_sub_type,
  CASE
    WHEN type = 3 AND sub_type = 1 THEN '无API海外仓'
    WHEN type = 3 AND sub_type = 2 THEN '有API海外仓'
    ELSE NULL
  END AS warehouse_sub_type_name,
  NULLIF(country_code, '') AS country_code,
  is_delete,
  CASE WHEN is_delete = 0 THEN 1 ELSE 0 END AS enabled,
  'erp' AS source_system,
  'warehouse' AS source_table
FROM jmh_data_platform.warehouse
WHERE name IS NOT NULL
  AND TRIM(name) <> '';
