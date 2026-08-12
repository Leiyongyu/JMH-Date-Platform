-- 图片 SOP 完整部署脚本
-- 适用：MySQL 8.0+；执行账号需同时拥有 date-project 和 jmh_data_platform 权限。
-- 特性：幂等执行；仅创建缺失表、菜单和权限，不删除或清空任何业务数据。

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. Python 图片 SOP 运行表：date-project
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS `date-project`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `date-project`.`image_sop_draft` (
    `id` CHAR(32) NOT NULL COMMENT 'SOP草稿UUID（无连字符）',
    `sku` VARCHAR(200) NOT NULL COMMENT 'Amazon MSKU或eBay业务SKU',
    `source_mode` VARCHAR(20) NOT NULL DEFAULT 'amazon' COMMENT '数据来源：amazon或ebay',
    `status` VARCHAR(30) NOT NULL DEFAULT 'completed' COMMENT '草稿状态',
    `store_sid` BIGINT NULL COMMENT '领星店铺SID',
    `data_json` JSON NOT NULL COMMENT '完整SOP草稿、图片清单及生成结果',
    `request_id` VARCHAR(128) NULL COMMENT '跨ERP与Python的请求追踪ID',
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    `expires_at` DATETIME(3) NOT NULL COMMENT '草稿过期时间，默认7天',
    PRIMARY KEY (`id`),
    KEY `idx_image_sop_draft_sku` (`sku`),
    KEY `idx_image_sop_draft_expires` (`expires_at`),
    KEY `idx_image_sop_draft_updated` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='图片SOP生成草稿；复杂生成结果使用JSON保存，大文件仅保存路径';

CREATE TABLE IF NOT EXISTS `date-project`.`image_sop_ai_profile_cache` (
    `cache_key` VARCHAR(255) NOT NULL COMMENT 'Amazon为SID+SKU，eBay为商品版本键',
    `listing_version` VARCHAR(255) NOT NULL COMMENT 'Listing更新时间或内容哈希',
    `data_json` JSON NOT NULL COMMENT 'AI产品分析缓存',
    `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    `expires_at` DATETIME(3) NOT NULL COMMENT '缓存过期时间',
    PRIMARY KEY (`cache_key`),
    KEY `idx_image_sop_ai_cache_expires` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='图片SOP的AI产品分析缓存';

-- ---------------------------------------------------------------------------
-- 2. ERP 菜单和权限：jmh_data_platform
-- ---------------------------------------------------------------------------
USE `jmh_data_platform`;

SET @sop_menu_id := (
  SELECT `menu_id`
  FROM `sys_menu`
  WHERE `parent_id` = 0
    AND `menu_type` = 'M'
    AND (`path` = 'sop' OR `menu_name` = 'SOP')
  ORDER BY CASE WHEN `path` = 'sop' THEN 0 ELSE 1 END, `menu_id`
  LIMIT 1
);

INSERT INTO `sys_menu` (
  `menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,
  `is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,
  `create_by`,`create_time`,`remark`
)
SELECT 'SOP',0,5,'sop',NULL,NULL,'Sop',1,0,'M','0','0',NULL,'guide',
       'SYSTEM',NOW(),'标准作业流程与业务数据处理'
WHERE @sop_menu_id IS NULL;

SET @sop_menu_id := (
  SELECT `menu_id`
  FROM `sys_menu`
  WHERE `parent_id` = 0
    AND `menu_type` = 'M'
    AND (`path` = 'sop' OR `menu_name` = 'SOP')
  ORDER BY CASE WHEN `path` = 'sop' THEN 0 ELSE 1 END, `menu_id`
  LIMIT 1
);

SET @image_sop_menu_id := (
  SELECT `menu_id`
  FROM `sys_menu`
  WHERE `parent_id` = @sop_menu_id
    AND (
      `path` = 'image-sop'
      OR `component` = 'sop/imageSop/index'
      OR `perms` = 'sop:imageSop:use'
    )
  ORDER BY `menu_id`
  LIMIT 1
);

INSERT INTO `sys_menu` (
  `menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,
  `is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,
  `create_by`,`create_time`,`remark`
)
SELECT '图片SOP',@sop_menu_id,4,'image-sop','sop/imageSop/index',NULL,'SopImageSop',
       1,0,'C','0','0','sop:imageSop:use','picture',
       'SYSTEM',NOW(),'领星/eBay商品信息、AI图片需求生成与Excel导出'
WHERE @sop_menu_id IS NOT NULL
  AND @image_sop_menu_id IS NULL;

SET @image_sop_menu_id := (
  SELECT `menu_id`
  FROM `sys_menu`
  WHERE `parent_id` = @sop_menu_id
    AND (
      `path` = 'image-sop'
      OR `component` = 'sop/imageSop/index'
      OR `perms` = 'sop:imageSop:use'
    )
  ORDER BY `menu_id`
  LIMIT 1
);

UPDATE `sys_menu`
SET `menu_name` = '图片SOP',
    `parent_id` = @sop_menu_id,
    `order_num` = 4,
    `path` = 'image-sop',
    `component` = 'sop/imageSop/index',
    `route_name` = 'SopImageSop',
    `is_frame` = 1,
    `is_cache` = 0,
    `menu_type` = 'C',
    `visible` = '0',
    `status` = '0',
    `perms` = 'sop:imageSop:use',
    `icon` = 'picture',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = '领星/eBay商品信息、AI图片需求生成与Excel导出'
WHERE `menu_id` = @image_sop_menu_id;

-- 超级管理员角色获得 SOP 目录与图片 SOP 菜单权限。
INSERT IGNORE INTO `sys_role_menu` (`role_id`,`menu_id`)
SELECT `role_id`, @sop_menu_id
FROM `sys_role`
WHERE `role_key` = 'admin'
  AND `status` = '0'
  AND @sop_menu_id IS NOT NULL;

INSERT IGNORE INTO `sys_role_menu` (`role_id`,`menu_id`)
SELECT `role_id`, @image_sop_menu_id
FROM `sys_role`
WHERE `role_key` = 'admin'
  AND `status` = '0'
  AND @image_sop_menu_id IS NOT NULL;

-- leiyongyu 当前关联的全部角色获得 SOP 目录与图片 SOP 菜单权限。
INSERT IGNORE INTO `sys_role_menu` (`role_id`,`menu_id`)
SELECT DISTINCT `ur`.`role_id`, @sop_menu_id
FROM `sys_user` `u`
JOIN `sys_user_role` `ur` ON `ur`.`user_id` = `u`.`user_id`
WHERE `u`.`user_name` = 'leiyongyu'
  AND @sop_menu_id IS NOT NULL;

INSERT IGNORE INTO `sys_role_menu` (`role_id`,`menu_id`)
SELECT DISTINCT `ur`.`role_id`, @image_sop_menu_id
FROM `sys_user` `u`
JOIN `sys_user_role` `ur` ON `ur`.`user_id` = `u`.`user_id`
WHERE `u`.`user_name` = 'leiyongyu'
  AND @image_sop_menu_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. 执行结果验证
-- ---------------------------------------------------------------------------
SELECT 'date-project.image_sop_draft' AS `object_name`, COUNT(*) AS `row_count`
FROM `date-project`.`image_sop_draft`
UNION ALL
SELECT 'date-project.image_sop_ai_profile_cache', COUNT(*)
FROM `date-project`.`image_sop_ai_profile_cache`;

SELECT `menu_id`,`parent_id`,`menu_name`,`order_num`,`path`,`component`,
       `menu_type`,`perms`,`status`
FROM `sys_menu`
WHERE `menu_id` IN (@sop_menu_id, @image_sop_menu_id)
ORDER BY `parent_id`,`order_num`,`menu_id`;

SELECT `u`.`user_name`,`r`.`role_name`,`r`.`role_key`,`m`.`menu_name`,`m`.`perms`
FROM `sys_user` `u`
JOIN `sys_user_role` `ur` ON `ur`.`user_id` = `u`.`user_id`
JOIN `sys_role` `r` ON `r`.`role_id` = `ur`.`role_id`
JOIN `sys_role_menu` `rm` ON `rm`.`role_id` = `r`.`role_id`
JOIN `sys_menu` `m` ON `m`.`menu_id` = `rm`.`menu_id`
WHERE `u`.`user_name` = 'leiyongyu'
  AND `m`.`menu_id` IN (@sop_menu_id, @image_sop_menu_id)
ORDER BY `r`.`role_id`,`m`.`menu_id`;
