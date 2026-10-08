-- 可选且不可逆：先备份三张表并核对新版补货2.0列表/导出均已读取谷仓仓租。
-- 仅供人工在新版 Java、Python、Vue 全部部署、验证通过后执行；不属于自动升级脚本。
-- 不要删除 date-project.ods_goodcang_wh_inventory_storage_detail、
-- date-project.ods_goodcang_wh_inventory_storage_summary 或 dim_lingxing_currency_month。
-- 旧版 20260831/20260902 部署SQL会重建上传表，之后不要再执行这些旧脚本。
USE `jmh_data_platform`;

SELECT 'ebay_replenishment_v2_warehouse_rent_detail' AS table_name, COUNT(*) AS row_count
FROM ebay_replenishment_v2_warehouse_rent_detail
UNION ALL
SELECT 'ebay_replenishment_v2_warehouse_rent', COUNT(*)
FROM ebay_replenishment_v2_warehouse_rent
UNION ALL
SELECT 'ebay_replenishment_v2_warehouse_rent_import_lock', COUNT(*)
FROM ebay_replenishment_v2_warehouse_rent_import_lock;

-- MySQL DDL会隐式提交；确认备份及上述行数后，单独执行下面三句。
-- DROP TABLE `ebay_replenishment_v2_warehouse_rent_detail`;
-- DROP TABLE `ebay_replenishment_v2_warehouse_rent`;
-- DROP TABLE `ebay_replenishment_v2_warehouse_rent_import_lock`;
