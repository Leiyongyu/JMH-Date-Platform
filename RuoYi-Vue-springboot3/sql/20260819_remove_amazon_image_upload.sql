-- 下线“亚马逊主图批量上传”功能的数据清理脚本。
-- 本脚本会永久删除该功能的菜单、用户配置、任务和日志数据，请先备份后再执行。
-- 两套数据库严格分开处理：ERP 配置在 jmh_data_platform，Python 任务表在 Date-Project。

SET NAMES utf8mb4;

-- 一、Java ERP 数据库：删除角色菜单关系、功能权限和用户配置表。
USE `jmh_data_platform`;

DELETE role_menu
FROM sys_role_menu role_menu
JOIN sys_menu menu_info ON menu_info.menu_id=role_menu.menu_id
WHERE menu_info.perms='sop:amazonImageUpload:use'
   OR menu_info.path LIKE '%amazon-image-upload%'
   OR menu_info.component LIKE '%amazonImageUpload%';

DELETE FROM sys_menu
WHERE perms='sop:amazonImageUpload:use'
   OR path LIKE '%amazon-image-upload%'
   OR component LIKE '%amazonImageUpload%';

DROP TABLE IF EXISTS `sop_amazon_image_upload_user_config`;

-- 专用角色不再使用；先解除用户关系，再删除角色菜单关系和角色。
SET @amazon_upload_role_id := (
    SELECT role_id FROM sys_role
    WHERE role_key='amazon_image_upload_operator' AND del_flag='0'
    ORDER BY role_id LIMIT 1
);
DELETE FROM sys_user_role WHERE role_id=@amazon_upload_role_id;
DELETE FROM sys_role_menu WHERE role_id=@amazon_upload_role_id;
DELETE FROM sys_role WHERE role_id=@amazon_upload_role_id;

-- 二、Python 数据库：删除主图上传任务、日志、进度、执行器和文件批次表。
USE `Date-Project`;

DROP TABLE IF EXISTS `amazon_image_upload_task_log`;
DROP TABLE IF EXISTS `amazon_image_upload_progress`;
DROP TABLE IF EXISTS `amazon_image_upload_executor`;
DROP TABLE IF EXISTS `amazon_image_upload_file_batch`;
DROP TABLE IF EXISTS `amazon_image_upload_task`;

-- 核验：以下两项都应返回 0。
SELECT COUNT(*) AS erp残留菜单数
FROM `jmh_data_platform`.`sys_menu`
WHERE perms='sop:amazonImageUpload:use'
   OR path LIKE '%amazon-image-upload%'
   OR component LIKE '%amazonImageUpload%';

SELECT COUNT(*) AS python残留表数
FROM information_schema.tables
WHERE table_schema='Date-Project'
  AND table_name LIKE 'amazon_image_upload%';
