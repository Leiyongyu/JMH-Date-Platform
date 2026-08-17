-- eBay SP 价格查询：SKU-OE 维表、脚本目录、页面及按钮权限。
-- 可重复执行；不会删除已有业务数据。

CREATE TABLE IF NOT EXISTS dim_ebay_sku_oe_mapping (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    sku VARCHAR(128) NOT NULL COMMENT 'SKU；导入文件中出现的SKU按整组覆盖更新',
    oe VARCHAR(128) NOT NULL COMMENT '单个OE号；同一SKU的多个OE分别存为多行',
    oe_index INT NOT NULL DEFAULT 1 COMMENT '同一SKU下OE展示顺序',
    source_file_name VARCHAR(255) NULL COMMENT '最近一次导入来源文件名',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dim_ebay_sku_oe (sku, oe),
    KEY idx_dim_ebay_sku (sku),
    KEY idx_dim_ebay_oe (oe)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DIM-eBay SKU与OE号对照维表';

-- 一级目录：脚本。
SET @scripts_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = 0
    AND menu_type = 'M'
    AND path = 'scripts'
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '脚本', 0, 4, 'scripts', NULL, NULL, 'Scripts',
  1, 0, 'M', '0', '0', NULL, 'code',
  'SYSTEM', NOW(), '业务脚本工具目录'
WHERE @scripts_menu_id IS NULL;

SET @scripts_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = 0
    AND menu_type = 'M'
    AND path = 'scripts'
  ORDER BY menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = '脚本',
    order_num = 4,
    route_name = 'Scripts',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'M',
    visible = '0',
    status = '0',
    icon = 'code',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '业务脚本工具目录'
WHERE menu_id = @scripts_menu_id;

-- 二级菜单：eBay SP价格查询。
SET @ebay_price_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @scripts_menu_id
    AND path = 'ebay-sp-price'
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  'eBay SP价格查询', @scripts_menu_id, 1, 'ebay-sp-price',
  'scripts/ebayPrice/index', NULL, 'EbaySpPrice',
  1, 0, 'C', '0', '0', 'scripts:ebayPrice:list', 'search',
  'SYSTEM', NOW(), '对接eBay官方Buy Browse API查询商品价格和详情'
WHERE @scripts_menu_id IS NOT NULL
  AND @ebay_price_menu_id IS NULL;

SET @ebay_price_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @scripts_menu_id
    AND path = 'ebay-sp-price'
  ORDER BY menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name = 'eBay SP价格查询',
    order_num = 1,
    component = 'scripts/ebayPrice/index',
    route_name = 'EbaySpPrice',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'scripts:ebayPrice:list',
    icon = 'search',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '对接eBay官方Buy Browse API查询商品价格和详情'
WHERE menu_id = @ebay_price_menu_id;

-- 按钮权限。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  'eBay价格查询', @ebay_price_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'scripts:ebayPrice:query', '#',
  'SYSTEM', NOW(), ''
WHERE @ebay_price_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE perms = 'scripts:ebayPrice:query'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '导入SKU-OE', @ebay_price_menu_id, 2, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'scripts:ebayPrice:import', '#',
  'SYSTEM', NOW(), ''
WHERE @ebay_price_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE perms = 'scripts:ebayPrice:import'
  );

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '导出查询结果', @ebay_price_menu_id, 3, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'scripts:ebayPrice:export', '#',
  'SYSTEM', NOW(), ''
WHERE @ebay_price_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE perms = 'scripts:ebayPrice:export'
  );

SET @ebay_query_menu_id := (
  SELECT menu_id FROM sys_menu WHERE perms = 'scripts:ebayPrice:query' ORDER BY menu_id LIMIT 1
);
SET @ebay_import_menu_id := (
  SELECT menu_id FROM sys_menu WHERE perms = 'scripts:ebayPrice:import' ORDER BY menu_id LIMIT 1
);
SET @ebay_export_menu_id := (
  SELECT menu_id FROM sys_menu WHERE perms = 'scripts:ebayPrice:export' ORDER BY menu_id LIMIT 1
);

-- 管理员角色获得页面和全部按钮权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT r.role_id, permission_menu.menu_id
FROM sys_role r
JOIN (
  SELECT @scripts_menu_id AS menu_id
  UNION ALL SELECT @ebay_price_menu_id
  UNION ALL SELECT @ebay_query_menu_id
  UNION ALL SELECT @ebay_import_menu_id
  UNION ALL SELECT @ebay_export_menu_id
) permission_menu ON permission_menu.menu_id IS NOT NULL
WHERE r.role_key = 'admin'
  AND r.status = '0';

-- leiyongyu 当前拥有的全部角色获得页面和全部按钮权限。
INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT ur.role_id, permission_menu.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN (
  SELECT @scripts_menu_id AS menu_id
  UNION ALL SELECT @ebay_price_menu_id
  UNION ALL SELECT @ebay_query_menu_id
  UNION ALL SELECT @ebay_import_menu_id
  UNION ALL SELECT @ebay_export_menu_id
) permission_menu ON permission_menu.menu_id IS NOT NULL
WHERE u.user_name = 'leiyongyu';

-- 部署检查。
SELECT menu_id, parent_id, menu_name, order_num, path, component, menu_type, perms, visible, status
FROM sys_menu
WHERE menu_id IN (
  @scripts_menu_id, @ebay_price_menu_id, @ebay_query_menu_id,
  @ebay_import_menu_id, @ebay_export_menu_id
)
ORDER BY parent_id, order_num, menu_id;

SELECT u.user_name, r.role_name, m.menu_name, m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = r.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND m.menu_id IN (
    @scripts_menu_id, @ebay_price_menu_id, @ebay_query_menu_id,
    @ebay_import_menu_id, @ebay_export_menu_id
  )
ORDER BY m.menu_type, m.order_num;
