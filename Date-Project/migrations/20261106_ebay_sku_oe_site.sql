-- eBay 价格查询（SOP）用的「中间码+站点 → OE号」对照表，替代原 backend/ebay_tool/SKU主OE对照表.xlsx。
-- 页面上传同结构的四列 Excel，按 site_key（中间码+站点）增量覆盖：没有的新增、有的覆盖 OE号、文件里没有的保留。
-- 只建表，不写数据；初始数据由页面上传或导入现有 Excel 完成。可重复执行。
CREATE TABLE IF NOT EXISTS dim_ebay_sku_oe_site (
    site_key VARCHAR(40) NOT NULL COMMENT '中间码+站点，如 10144US；Excel A列',
    middle_code VARCHAR(32) NOT NULL COMMENT '中间码，由 site_key 去掉末两位站点得到',
    site VARCHAR(2) NOT NULL COMMENT '站点：DE / UK / US',
    oe_no VARCHAR(255) NOT NULL COMMENT 'OE号；Excel D列',
    create_by VARCHAR(64) NULL COMMENT '首次写入人（ERP用户名，导入脚本为 system）',
    update_by VARCHAR(64) NULL COMMENT '最后修改人',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次写入时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'OE号最后变化时间',
    PRIMARY KEY (site_key),
    KEY idx_middle_code (middle_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DIM-eBay价格查询 中间码+站点 OE对照表';
