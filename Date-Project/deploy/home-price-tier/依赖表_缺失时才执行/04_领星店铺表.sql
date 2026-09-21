-- 只建表，不写入源数据、不注册同步任务。
USE `jmh_data_platform`;
CREATE TABLE IF NOT EXISTS `shop_list`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `store_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺ID，eBay店铺唯一标识',
  `sid` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'SID标识，默认为空字符串',
  `store_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺名称',
  `platform_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台代码，10003代表eBay平台',
  `platform_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台名称',
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺使用的货币单位，如HKD港币',
  `is_sync` tinyint NOT NULL DEFAULT 0 COMMENT '是否同步数据，1表示同步，0表示未同步',
  `status` tinyint NOT NULL DEFAULT 1 COMMENT '店铺状态，1表示启用，0表示禁用',
  `country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家/地区代码，如HK香港',
  `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_store_id`(`store_id` ASC) USING BTREE,
  INDEX `idx_platform_code`(`platform_code` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_country_code`(`country_code` ASC) USING BTREE,
  INDEX `idx_shop_list_platform_sid`(`platform_code` ASC, `sid` ASC) USING BTREE
) ENGINE = InnoDB  CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星店铺列表表' ROW_FORMAT = DYNAMIC;
