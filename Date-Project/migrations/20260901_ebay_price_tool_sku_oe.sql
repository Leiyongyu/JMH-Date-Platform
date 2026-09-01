-- eBay 价格查询工具 v3：SKU-OE 中间码对照表。
-- 与 Java 侧 dim_ebay_sku_oe_mapping 共存，本表额外支持中间码字段。

CREATE TABLE IF NOT EXISTS ebay_price_sku_oe_mapping (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    sku VARCHAR(128) NOT NULL COMMENT 'SKU 编号',
    oe VARCHAR(128) NOT NULL COMMENT '主 OE 号',
    middle_code VARCHAR(128) NULL COMMENT '中间码；为空时由代码从 SKU 自动提取',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ebay_price_sku_oe (sku, oe),
    KEY idx_ebay_price_sku (sku),
    KEY idx_ebay_price_oe (oe),
    KEY idx_ebay_price_middle_code (middle_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='eBay价格查询工具v3-SKU与OE号对照表（含中间码）';
