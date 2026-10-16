-- eBay补货2.0：只限制Excel导出字段，不限制页面展示；不新增/修改持久表结构。
-- 执行后：系统管理 -> 角色管理 -> 修改 -> 菜单权限 -> eBay补货2.0，
-- 勾选“导出字段-...”权限。37个主表字段、4个分段明细独有字段，共41项。
-- 同字段在主表和90天分段明细共用权限；多角色取并集，内置全权限账号仍导出全部。
-- 首次创建字段权限时，为已有页面查看权限（旧版也凭此导出）的有效角色保留全部字段。
-- 重复执行只为本次新建的权限补初始授权，不重新勾选管理员已取消的字段。
-- 然后执行 20261016_ebay_replenishment_v2_export_menu.sql，建立“导出”总开关和层级。
-- 注意：另行执行“leiyongyu角色全量授权”脚本仍会补回这些角色取消的字段，这是全量授权本身的含义。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

DROP TEMPORARY TABLE IF EXISTS tmp_ebay_replenishment_export_columns;
CREATE TEMPORARY TABLE tmp_ebay_replenishment_export_columns (
    field_key VARCHAR(64) PRIMARY KEY,
    field_title VARCHAR(40) NOT NULL,
    sort_order INT NOT NULL,
    is_new TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO tmp_ebay_replenishment_export_columns (field_key,field_title,sort_order) VALUES
('site','站点',101),
('sku','SKU',102),
('product_name','产品名称',103),
('sales_qty_7d','近7天销量',104),
('sales_qty_15d','近15天销量',105),
('sales_qty_30d','近30天销量',106),
('sales_qty','销量',107),
('gross_profit_amount','毛利',108),
('profit_rate','利润率',109),
('return_qty','退货量',110),
('return_rate','退货率',111),
('return_amount','退货金额',112),
('warehouse_rent_amount_cny','仓租费用',113),
('forecast_sales_quantity','预估销量',114),
('overseas_inventory_age_days','海外仓库龄',115),
('forecast_sales_quantity_2','预估销量2',116),
('forecast_gross_profit_amount','预估毛利',117),
('forecast_return_quantity','预估退货',118),
('forecast_return_amount','预估退货金额',119),
('sell_through_ratio','动销比',120),
('product_level','产品等级',121),
('product_nature','产品性质',122),
('sales_type','销售类型',123),
('chengdu_in_transit_quantity','成都在途',124),
('chengdu_sellable_quantity','成都可售',125),
('overseas_in_transit_quantity','海外在途',126),
('overseas_sellable_quantity','海外可售',127),
('chengdu_warehouse_to_warehouse_days','成都仓到仓时间',128),
('chengdu_qc_outbound_days','成都质检出仓时间',129),
('overseas_transit_to_listing_days','海外在途到上架时间',130),
('safety_stock_quantity','安全库存',131),
('suggested_replenishment_quantity','建议补货量',132),
('safety_stock_quantity_2','安全库存2',133),
('suggested_replenishment_quantity_2','建议补货量2',134),
('operations_note','运营',135),
('development_note','开发',136),
('operations_confirmed','运营确认',137),
('month','分段明细-日期区间',138),
('quality_return_qty','分段明细-产品质量问题退货量',139),
('quality_return_rate','分段明细-产品质量问题退货率',140),
('unclassified_return_qty','分段明细-未分类退货量',141);

START TRANSACTION;
SET @ebay_export_page_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:list' AND menu_type='C' AND status='0'
    ORDER BY menu_id LIMIT 1
);
-- 已部署导出总开关时，复用其父级，不把字段移回页面下。
SET @ebay_export_field_parent_id := COALESCE((
    SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:export' AND parent_id=@ebay_export_page_id AND menu_type='F'
    ORDER BY menu_id LIMIT 1
), @ebay_export_page_id);

UPDATE tmp_ebay_replenishment_export_columns c
SET is_new = NOT EXISTS (
    SELECT 1 FROM sys_menu m
    WHERE m.perms=CONCAT('operations:ebayReplenishmentV2:exportColumn:',c.field_key) COLLATE utf8mb4_unicode_ci
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark
)
SELECT CONCAT('导出字段-',c.field_title),@ebay_export_field_parent_id,c.sort_order,'',NULL,NULL,'',
       1,0,'F','0','0',CONCAT('operations:ebayReplenishmentV2:exportColumn:',c.field_key),
       '#','SYSTEM',NOW(),'只控制补货2.0 Excel导出列，不控制页面展示；同字段各Sheet共用权限'
FROM tmp_ebay_replenishment_export_columns c
WHERE c.is_new=1 AND @ebay_export_page_id IS NOT NULL;

INSERT INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_role_menu page_grant ON page_grant.role_id=r.role_id AND page_grant.menu_id=@ebay_export_page_id
JOIN tmp_ebay_replenishment_export_columns c ON c.is_new=1
JOIN sys_menu m ON m.parent_id=@ebay_export_field_parent_id AND m.menu_type='F' AND m.status='0'
    AND m.perms=CONCAT('operations:ebayReplenishmentV2:exportColumn:',c.field_key) COLLATE utf8mb4_unicode_ci
WHERE r.status='0' AND r.del_flag='0'
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id
  );
COMMIT;

-- 应返回41；返回0时检查补货2.0主菜单是否已部署，不能跳过此SQL直接部署新Java。
SELECT COUNT(*) AS export_field_permission_count
FROM sys_menu m JOIN tmp_ebay_replenishment_export_columns c
  ON m.perms=CONCAT('operations:ebayReplenishmentV2:exportColumn:',c.field_key) COLLATE utf8mb4_unicode_ci
WHERE m.parent_id=@ebay_export_field_parent_id AND m.status='0' AND m.menu_type='F';

DROP TEMPORARY TABLE tmp_ebay_replenishment_export_columns;
-- 角色配置后，账号退出重新登录以刷新权限；无任何导出字段权限时，导出会提示联系管理员。
