-- 在 Python 数据库执行；独立新表，不改产品档案、不删除业务数据。
-- 重复执行仅检查建表，绝不覆盖已上传价格。不需新增菜单权限。
USE `date-project`;

CREATE TABLE IF NOT EXISTS ebay_inventory_detail_price (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    sku VARCHAR(255) NOT NULL COMMENT '上传的完整SKU，去首尾空格并转大写',
    middle_code VARCHAR(64) NULL COMMENT 'SKU第二段纯数字文本，保留前导零；无法解析时NULL，不参与匹配',
    unit_price DECIMAL(24,6) NOT NULL COMMENT '上传人民币单价；非负，0为有效价',
    source_file VARCHAR(255) NOT NULL DEFAULT '' COMMENT '最近来源文件',
    updated_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近导入人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_inventory_price_sku_price (sku,unit_price),
    KEY idx_inventory_price_middle_price (middle_code,unit_price)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Ebay库存明细上传单价；本次SKU价格集合增量替换，中间码取最低价';

-- 验证
SELECT COUNT(*) AS price_rows, COUNT(DISTINCT sku) AS sku_count,
       COUNT(DISTINCT middle_code) AS middle_code_count
FROM ebay_inventory_detail_price;
