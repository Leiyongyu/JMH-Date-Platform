-- Python数据库；仅新建独立产品等级表，不删除/覆盖任何已有业务表。
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS ebay_inventory_detail_grade (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    site VARCHAR(100) NOT NULL COMMENT '归一站点：德国、英国、美国、法国',
    sku VARCHAR(255) NOT NULL COMMENT '完整SKU，不去品牌前缀',
    grade VARCHAR(64) NOT NULL COMMENT '上传文件的原始等级文本，不套补货2.0等级规则',
    source_file VARCHAR(255) NOT NULL DEFAULT '' COMMENT '最近一次来源文件',
    updated_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近一次导入人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_inventory_detail_site_sku (site,sku),
    KEY idx_inventory_detail_grade (grade)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Ebay库存明细独立等级配置，文件按站点完整SKU增量更新';
