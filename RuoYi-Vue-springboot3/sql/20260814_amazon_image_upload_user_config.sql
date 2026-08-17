-- 仅在 Java ERP 数据库 jmh_data_platform 中执行。
-- 本表绝不存储紫鸟密码；密码只按 user_id 缓存于 Redis 8 小时。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `sop_amazon_image_upload_user_config` (
  `user_id` bigint NOT NULL COMMENT 'ERP用户ID，与sys_user.user_id一对一',
  `company_name` varchar(128) NOT NULL COMMENT '紫鸟企业/公司名',
  `account_name` varchar(128) NOT NULL COMMENT '紫鸟登录账号',
  `client_path` varchar(500) NOT NULL COMMENT '紫鸟ziniao.exe启动路径',
  `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  CONSTRAINT `fk_sop_amz_image_user_config_user`
    FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='亚马逊主图上传用户级紫鸟非敏感配置';
