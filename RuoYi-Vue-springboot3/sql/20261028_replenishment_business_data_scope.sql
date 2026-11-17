-- Java ERP database only. Adds permission nodes and an administrator-managed owner binding table.
-- First installation preserves existing page roles' full visibility. Configure
-- narrower roles afterwards. Rerunning does NOT restore revoked full permissions.
USE jmh_data_platform;
SET NAMES utf8mb4;
CREATE TEMPORARY TABLE _replenishment_scope_modules (
  module VARCHAR(100) PRIMARY KEY, parent_id BIGINT NOT NULL, first_install TINYINT NOT NULL
);
INSERT INTO _replenishment_scope_modules
SELECT 'operations:ebayReplenishmentV2',
  IF(COUNT(*)=1,MIN(menu_id),NULL),
  NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:ebayReplenishmentV2:data')
FROM sys_menu WHERE perms='operations:ebayReplenishmentV2:list' AND menu_type='C';
INSERT INTO _replenishment_scope_modules
SELECT 'operations:amzReplenishment',
  IF(COUNT(*)=1,MIN(menu_id),NULL),
  NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:amzReplenishment:data')
FROM sys_menu WHERE perms='operations:amzReplenishment:list'
  AND component='operations/amz/replenishment/index' AND menu_type='C';

CREATE TABLE IF NOT EXISTS sys_business_owner_binding (
  owner_name VARCHAR(100) COLLATE utf8mb4_0900_bin NOT NULL,
  user_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(owner_name), KEY idx_business_owner_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='管理员维护的账号与业务负责人精确绑定';

START TRANSACTION;
-- Seed only once; ambiguous or empty names require manual administrator binding.
INSERT IGNORE INTO sys_business_owner_binding(owner_name,user_id)
SELECT TRIM(u.nick_name),u.user_id FROM sys_user u
WHERE u.del_flag='0' AND u.status='0' AND TRIM(COALESCE(u.nick_name,'')) NOT IN ('','未分配','--')
  AND (SELECT COUNT(*) FROM sys_user x WHERE x.del_flag='0' AND BINARY TRIM(x.nick_name)=BINARY TRIM(u.nick_name))=1
  AND EXISTS(SELECT 1 FROM _replenishment_scope_modules WHERE first_install=1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '业务数据范围',s.parent_id,95,'#',1,0,'F','0','0',CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data'),'#','SYSTEM',NOW(),
  '仅用于该补货模块。多个角色取并集：全部优先，其次本部门，最后仅本人。'
FROM _replenishment_scope_modules s
WHERE NOT EXISTS(SELECT 1 FROM sys_menu m WHERE m.perms=CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data'));

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT options.label,parent.menu_id,options.sort,'#',1,0,'F','0','0',CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data:',options.scope),'#','SYSTEM',NOW(),
  '列表、筛选、导出及行操作共享范围；没有范围权限则不返回数据'
FROM _replenishment_scope_modules s
JOIN sys_menu parent ON parent.perms=CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data')
CROSS JOIN (SELECT 'self' scope,'仅本人数据' label,1 sort
            UNION ALL SELECT 'dept','本部门数据',2
            UNION ALL SELECT 'all','全部数据',3) options
WHERE NOT EXISTS(SELECT 1 FROM sys_menu m WHERE m.perms=CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data:',options.scope));

INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT existing.role_id,permission.menu_id
FROM _replenishment_scope_modules s
JOIN sys_role_menu existing ON existing.menu_id=s.parent_id
JOIN sys_role r ON r.role_id=existing.role_id AND r.del_flag='0'
JOIN sys_menu permission ON permission.perms IN (CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data'),CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data:all'))
WHERE s.first_install=1;
COMMIT;
SELECT m.menu_id,m.parent_id,m.menu_name,m.perms FROM sys_menu m
JOIN _replenishment_scope_modules s ON m.perms LIKE CONCAT(s.module COLLATE utf8mb4_unicode_ci,':data%')
ORDER BY m.parent_id,m.order_num;
DROP TEMPORARY TABLE _replenishment_scope_modules;
