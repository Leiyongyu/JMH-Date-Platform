-- 执行顺序：
-- 1. 20260806_structure_required_ods_fields.sql
-- 2. 20260806_remove_performance_clearance_raw_json.sql
-- 3. 本文件
--
-- 作用：保留领星共享仓身份字段，使 sid=0 的库存明细也能显示仓库名称和关联店铺。
-- 本迁移只增加/扩展字段，不删除历史数据；旧月份无法从现有精简字段反推共享仓名称，
-- 可按需重新拉取对应月份。本版本同步会以 pull_month 为单位原子替换当月数据。

ALTER TABLE ods_lingxing_amz_fba_inventory_raw
    ADD COLUMN warehouse_name VARCHAR(255) NULL COMMENT '领星仓库名称' AFTER sku,
    ADD COLUMN seller_group_name VARCHAR(1000) NULL COMMENT '共享仓关联店铺列表' AFTER warehouse_name,
    ADD COLUMN share_type TINYINT NULL COMMENT '共享类型：0非共享、1北美共享、2欧洲共享' AFTER seller_group_name;

ALTER TABLE dwd_amz_fba_inventory_monthly_snapshot
    MODIFY COLUMN seller_group_name VARCHAR(1000) NULL COMMENT '共享仓关联店铺列表';

SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE()
  AND TABLE_NAME='ods_lingxing_amz_fba_inventory_raw'
  AND COLUMN_NAME IN ('warehouse_name','seller_group_name','share_type')
ORDER BY ORDINAL_POSITION;
