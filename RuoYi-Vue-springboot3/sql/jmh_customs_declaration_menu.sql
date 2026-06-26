-- 报关管理菜单。通过“运营中心”名称定位父菜单，可重复执行。
CREATE TABLE IF NOT EXISTS customs_inventory_list (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    product_code VARCHAR(100) DEFAULT NULL COMMENT '编码',
    product_name VARCHAR(255) DEFAULT NULL COMMENT '产品名称',
    sku VARCHAR(100) DEFAULT NULL COMMENT 'SKU',
    purchase_quantity VARCHAR(255) DEFAULT NULL COMMENT '采购数量',
    unit VARCHAR(50) DEFAULT NULL COMMENT '单位',
    tax_included_price VARCHAR(255) DEFAULT NULL COMMENT '含税单价',
    purchase_date VARCHAR(255) DEFAULT NULL COMMENT '采购日期',
    inbound_date VARCHAR(255) DEFAULT NULL COMMENT '入库日期',
    inbound_quantity DECIMAL(18,4) DEFAULT NULL COMMENT '入库数量',
    inbound_remark VARCHAR(500) DEFAULT NULL COMMENT '入库备注',
    outbound_date TEXT COMMENT '出库日期',
    czech_warehouse_qty DECIMAL(18,4) DEFAULT NULL COMMENT '捷克仓',
    uk_warehouse_qty DECIMAL(18,4) DEFAULT NULL COMMENT '英国仓',
    us_warehouse_qty DECIMAL(18,4) DEFAULT NULL COMMENT '美国谷仓',
    de_warehouse_qty DECIMAL(18,4) DEFAULT NULL COMMENT '德国仓',
    fba_de_qty DECIMAL(18,4) DEFAULT NULL COMMENT 'FBA(DE)',
    fba_uk_qty DECIMAL(18,4) DEFAULT NULL COMMENT 'FBA(UK)',
    fba_us_qty DECIMAL(18,4) DEFAULT NULL COMMENT 'FBA(US)',
    fba_fr_qty DECIMAL(18,4) DEFAULT NULL COMMENT 'FBA(FR)',
    remaining_stock DECIMAL(18,4) DEFAULT NULL COMMENT '剩余库存',
    remark VARCHAR(500) DEFAULT NULL COMMENT '备注',
    customs_unit VARCHAR(50) DEFAULT NULL COMMENT '报关计量单位',
    declaration_elements TEXT COMMENT '申报要素',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_customs_inventory_sku (sku),
    KEY idx_customs_inventory_product_code (product_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报关出入库清单';

SET @has_inventory_source_index := (
    SELECT COUNT(1) FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'customs_inventory_list'
      AND index_name = 'uk_customs_inventory_source_row'
);
SET @sql := IF(@has_inventory_source_index > 0,
    'ALTER TABLE customs_inventory_list DROP INDEX uk_customs_inventory_source_row',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_inventory_source_sheet := (
    SELECT COUNT(1) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'customs_inventory_list'
      AND column_name = 'source_sheet'
);
SET @sql := IF(@has_inventory_source_sheet > 0,
    'ALTER TABLE customs_inventory_list DROP COLUMN source_sheet',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_inventory_source_row := (
    SELECT COUNT(1) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'customs_inventory_list'
      AND column_name = 'source_row_no'
);
SET @sql := IF(@has_inventory_source_row > 0,
    'ALTER TABLE customs_inventory_list DROP COLUMN source_row_no',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @operations_parent_id := (
    SELECT menu_id FROM sys_menu
    WHERE menu_name = '运营中心' AND menu_type = 'M'
    ORDER BY menu_id LIMIT 1
);

SET @customs_parent_id := (
    SELECT menu_id FROM sys_menu
    WHERE menu_name = '报关管理' AND menu_type = 'M'
    ORDER BY menu_id LIMIT 1
);

SET @next_menu_id := (SELECT COALESCE(MAX(menu_id), 0) + 1 FROM sys_menu);

INSERT INTO sys_menu
(menu_id, menu_name, parent_id, order_num, path, component, query, route_name, is_frame, is_cache,
 menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT @next_menu_id, '报关管理', @operations_parent_id, 30, 'customs', NULL, '', 'Customs',
       1, 0, 'M', '0', '0', NULL, 'form', 'admin', NOW(), '', NULL, '报关管理目录'
WHERE @operations_parent_id IS NOT NULL
  AND @customs_parent_id IS NULL;

SET @customs_parent_id := (
    SELECT menu_id FROM sys_menu
    WHERE menu_name = '报关管理' AND menu_type = 'M'
    ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET parent_id = @operations_parent_id,
    path = 'customs',
    route_name = 'Customs',
    icon = 'form',
    visible = '0',
    status = '0'
WHERE menu_id = @customs_parent_id;

SET @customs_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'customs:declaration:list'
    ORDER BY menu_id LIMIT 1
);

SET @next_menu_id := (SELECT COALESCE(MAX(menu_id), 0) + 1 FROM sys_menu);

INSERT INTO sys_menu
(menu_id, menu_name, parent_id, order_num, path, component, query, route_name, is_frame, is_cache,
 menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT @next_menu_id,
       '报关单制作', @customs_parent_id, 1, 'declaration',
       'operations/customs/declaration/index', '', 'CustomsDeclaration', 1, 0,
       'C', '0', '0', 'customs:declaration:list', 'form', 'admin', NOW(), '', NULL, '报关单制作菜单'
WHERE @customs_parent_id IS NOT NULL
  AND @customs_menu_id IS NULL;

SET @customs_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'customs:declaration:list'
    ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET parent_id = @customs_parent_id,
    order_num = 1,
    path = 'declaration',
    component = 'operations/customs/declaration/index',
    route_name = 'CustomsDeclaration',
    visible = '0',
    status = '0'
WHERE menu_id = @customs_menu_id;

SET @inventory_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'customs:inventory:list'
    ORDER BY menu_id LIMIT 1
);

SET @next_menu_id := (SELECT COALESCE(MAX(menu_id), 0) + 1 FROM sys_menu);

INSERT INTO sys_menu
(menu_id, menu_name, parent_id, order_num, path, component, query, route_name, is_frame, is_cache,
 menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT @next_menu_id,
       '出入库清单', @customs_parent_id, 2, 'inventory',
       'operations/customs/inventory/index', '', 'CustomsInventory', 1, 0,
       'C', '0', '0', 'customs:inventory:list', 'list', 'admin', NOW(), '', NULL, '报关出入库清单菜单'
WHERE @customs_parent_id IS NOT NULL
  AND @inventory_menu_id IS NULL;

SET @inventory_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms = 'customs:inventory:list'
    ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET parent_id = @customs_parent_id,
    order_num = 2,
    path = 'inventory',
    component = 'operations/customs/inventory/index',
    route_name = 'CustomsInventory',
    visible = '0',
    status = '0'
WHERE menu_id = @inventory_menu_id;

SET @next_button_id := (SELECT COALESCE(MAX(menu_id), 0) FROM sys_menu);

INSERT INTO sys_menu
(menu_id, menu_name, parent_id, order_num, path, component, query, route_name, is_frame, is_cache,
 menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT (@next_button_id := @next_button_id + 1),
       p.menu_name, @customs_menu_id, p.order_num, '#', '', '', '', 1, 0,
       'F', '0', '0', p.perms, '#', 'admin', NOW(), '', NULL, ''
FROM (
    SELECT '报关查询' menu_name, 1 order_num, 'customs:declaration:query' perms
    UNION ALL SELECT '报关导入', 2, 'customs:declaration:import'
    UNION ALL SELECT '报关导出', 3, 'customs:declaration:export'
    UNION ALL SELECT '商品资料保存', 4, 'customs:product:edit'
) p
WHERE @customs_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu x WHERE x.perms = p.perms);

SET @next_button_id := (SELECT COALESCE(MAX(menu_id), 0) FROM sys_menu);

INSERT INTO sys_menu
(menu_id, menu_name, parent_id, order_num, path, component, query, route_name, is_frame, is_cache,
 menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
SELECT (@next_button_id := @next_button_id + 1),
       p.menu_name, @inventory_menu_id, p.order_num, '#', '', '', '', 1, 0,
       'F', '0', '0', p.perms, '#', 'admin', NOW(), '', NULL, ''
FROM (
    SELECT '出入库清单查询' menu_name, 1 order_num, 'customs:inventory:list' perms
    UNION ALL SELECT '出入库清单导入', 2, 'customs:inventory:import'
    UNION ALL SELECT '出入库清单新增', 3, 'customs:inventory:add'
    UNION ALL SELECT '出入库清单导出', 4, 'customs:inventory:export'
    UNION ALL SELECT '出入库清单编辑', 5, 'customs:inventory:edit'
    UNION ALL SELECT '字段-编码', 101, 'customs:inventory:field:productCode'
    UNION ALL SELECT '字段-产品名称', 102, 'customs:inventory:field:productName'
    UNION ALL SELECT '字段-SKU', 103, 'customs:inventory:field:sku'
    UNION ALL SELECT '字段-采购数量', 104, 'customs:inventory:field:purchaseQuantity'
    UNION ALL SELECT '字段-单位', 105, 'customs:inventory:field:unit'
    UNION ALL SELECT '字段-含税单价', 106, 'customs:inventory:field:taxIncludedPrice'
    UNION ALL SELECT '字段-采购日期', 107, 'customs:inventory:field:purchaseDate'
    UNION ALL SELECT '字段-入库日期', 108, 'customs:inventory:field:inboundDate'
    UNION ALL SELECT '字段-入库数量', 109, 'customs:inventory:field:inboundQuantity'
    UNION ALL SELECT '字段-入库备注', 110, 'customs:inventory:field:inboundRemark'
    UNION ALL SELECT '字段-出库日期', 111, 'customs:inventory:field:outboundDate'
    UNION ALL SELECT '字段-捷克仓', 112, 'customs:inventory:field:czechWarehouseQty'
    UNION ALL SELECT '字段-英国仓', 113, 'customs:inventory:field:ukWarehouseQty'
    UNION ALL SELECT '字段-美国谷仓', 114, 'customs:inventory:field:usWarehouseQty'
    UNION ALL SELECT '字段-德国仓', 115, 'customs:inventory:field:deWarehouseQty'
    UNION ALL SELECT '字段-FBA(DE)', 116, 'customs:inventory:field:fbaDeQty'
    UNION ALL SELECT '字段-FBA(UK)', 117, 'customs:inventory:field:fbaUkQty'
    UNION ALL SELECT '字段-FBA(US)', 118, 'customs:inventory:field:fbaUsQty'
    UNION ALL SELECT '字段-FBA(FR)', 119, 'customs:inventory:field:fbaFrQty'
    UNION ALL SELECT '字段-剩余库存', 120, 'customs:inventory:field:remainingStock'
    UNION ALL SELECT '字段-备注', 121, 'customs:inventory:field:remark'
    UNION ALL SELECT '字段-报关计量单位', 122, 'customs:inventory:field:customsUnit'
    UNION ALL SELECT '字段-申报要素', 123, 'customs:inventory:field:declarationElements'
) p
WHERE @inventory_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu x WHERE x.perms = p.perms AND x.menu_type = 'F');

-- 管理员与系统开发人员默认获得报关目录、页面和按钮权限。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.role_id, m.menu_id
FROM sys_role r
JOIN sys_menu m ON m.menu_id IN (
    @operations_parent_id, @customs_parent_id, @customs_menu_id, @inventory_menu_id,
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:declaration:query' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:declaration:import' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:declaration:export' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:product:edit' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:inventory:list' AND menu_type = 'F' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:inventory:import' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:inventory:add' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:inventory:export' LIMIT 1),
    (SELECT menu_id FROM sys_menu WHERE perms = 'customs:inventory:edit' LIMIT 1)
)
WHERE r.role_key IN ('admin', 'admins')
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu rm
      WHERE rm.role_id = r.role_id AND rm.menu_id = m.menu_id
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.role_id, m.menu_id
FROM sys_role r
JOIN sys_menu m ON m.perms LIKE 'customs:inventory:field:%'
WHERE r.role_key IN ('admin', 'admins')
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu rm
      WHERE rm.role_id = r.role_id AND rm.menu_id = m.menu_id
  );
