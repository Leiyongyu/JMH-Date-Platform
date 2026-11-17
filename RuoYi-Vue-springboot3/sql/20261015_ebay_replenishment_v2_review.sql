-- eBay补货2.0：运营/开发备注，运营确认。仅新增表，不覆盖已有备注。
USE `jmh_data_platform`;
CREATE TABLE IF NOT EXISTS `ebay_replenishment_v2_review` (
  `site` VARCHAR(100) NOT NULL,
  `sku` VARCHAR(255) NOT NULL COMMENT '归并二手后缀后的完整SKU',
  `operations_note` VARCHAR(2000) NOT NULL DEFAULT '',
  `development_note` VARCHAR(2000) NOT NULL DEFAULT '',
  `operations_version` BIGINT NOT NULL DEFAULT 0,
  `development_version` BIGINT NOT NULL DEFAULT 0,
  `operations_confirmed` TINYINT NOT NULL DEFAULT 0,
  `operations_confirmed_by` VARCHAR(64) NULL,
  `operations_confirmed_at` DATETIME NULL,
  `operations_update_by` VARCHAR(64) NULL,
  `operations_update_time` DATETIME NULL,
  `development_update_by` VARCHAR(64) NULL,
  `development_update_time` DATETIME NULL,
  PRIMARY KEY (`site`,`sku`),
  KEY `idx_operations_confirmed` (`operations_confirmed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='补货2.0人工备注和运营确认，刷新销量不覆盖；修改运营备注后重新确认';

-- 采购按钮已改为独立权限，请另外执行20261016_ebay_replenishment_v2_purchase_permission.sql。
-- 本脚本不授予采购中心通用权限；备注和确认接口沿用补货2.0查看权限，操作人取登录会话。
