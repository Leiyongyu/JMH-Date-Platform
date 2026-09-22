-- Python数据库；eBay库存明细"历史最大月销"高水位表。
--
-- 为什么要单独存：订单表dwd_ebay_sku_analysis_order是Excel导入累积的，
-- 目前只有2026-05起的数据，早于该月的历史高点无法重算。业务口径是
-- "只有某个自然月的总销量超过当前值时才更新"，即只升不降的高水位，
-- 因此必须落库保存，并支持用业务方既有表格种入初值。
--
-- 键与页面合并口径一致：有合法数字中间码时按"站点+中间码"，否则退回
-- "站点+完整SKU"，与服务层 _product_key 同一套规则。
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS dws_ebay_inventory_max_monthly_sales (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    site VARCHAR(100) NOT NULL COMMENT '归一站点：德国、英国、美国、法国',
    product_key_type VARCHAR(16) NOT NULL COMMENT '键类型：MIDDLE=站点+中间码，SKU=站点+完整SKU（无合法中间码时）',
    product_key VARCHAR(255) NOT NULL COMMENT 'product_key_type为MIDDLE时是数字中间码文本（保留前导零）；为SKU时是大写完整SKU',
    max_monthly_sales DECIMAL(30,6) NOT NULL COMMENT '历史最大自然月销量；只升不降，仅当某月总销量超过此值时更新',
    peak_month CHAR(7) NULL COMMENT '产生当前高点的自然月YYYY-MM；种入的初值可为空',
    value_source VARCHAR(16) NOT NULL DEFAULT 'CALCULATED' COMMENT '当前值来源：CALCULATED=订单表算出，SEEDED=业务表格种入',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_max_monthly_sales_product (site, product_key_type, product_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Ebay库存明细历史最大月销高水位，按站点+中间码保存，只升不降';
