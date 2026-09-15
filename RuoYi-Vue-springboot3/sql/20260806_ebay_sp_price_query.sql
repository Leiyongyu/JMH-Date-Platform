-- 已下线的eBay SP价格审核：仅保留历史SKU-OE维表结构，不创建菜单/权限。
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

-- 2026-09-15：旧ERP价格审核页面已下线，不再创建菜单或角色授权。
-- 上方仅保留历史SKU-OE表结构；不会删除已有数据。
-- 已部署环境执行20260915_remove_legacy_ebay_sp_price_menu.sql清理旧入口。
