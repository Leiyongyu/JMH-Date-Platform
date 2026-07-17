USE jmh_data_platform;

-- 将当前实际使用的管理员类角色提升为超级管理员角色。
-- 规则：
-- 1. 优先选择非 role_id=1 的「管理员 / 系统管理员 / 系统开发人员」角色。
-- 2. 旧 role_id=1 的若依默认超级管理员改为历史停用角色，让出 role_key='admin'。
-- 3. 新超级管理员仍然最多只允许 3 个用户绑定。

SET @new_admin_role_id := (
    SELECT role_id
    FROM sys_role
    WHERE del_flag = '0'
      AND role_id <> 1
      AND role_name IN ('管理员', '系统管理员', '系统开发人员')
    ORDER BY FIELD(role_name, '管理员', '系统管理员', '系统开发人员'), role_id
    LIMIT 1
);

-- 如果部署库角色名不同，但固定使用了 101 作为当前管理员角色，则兜底选择 101。
SET @new_admin_role_id := COALESCE(
    @new_admin_role_id,
    (SELECT role_id FROM sys_role WHERE role_id = 101 AND del_flag = '0' LIMIT 1)
);

-- 旧版 role_id=1 让出 admin 权限字符。
UPDATE sys_role
SET role_name = '旧超级管理员',
    role_key = CONCAT('legacy_admin_', role_id),
    status = '1',
    remark = CONCAT(IFNULL(remark, ''), '；20260717 已停用，超级管理员权限迁移到当前管理员角色'),
    update_time = NOW()
WHERE role_id = 1
  AND @new_admin_role_id IS NOT NULL
  AND role_key = 'admin';

-- 当前管理员类角色升级为超级管理员。
UPDATE sys_role
SET role_name = '超级管理员',
    role_key = 'admin',
    status = '0',
    update_time = NOW()
WHERE role_id = @new_admin_role_id
  AND @new_admin_role_id IS NOT NULL;

-- 旧超级管理员用户迁移到新超级管理员角色，最多迁移到 3 人。
INSERT IGNORE INTO sys_user_role(user_id, role_id)
SELECT old_admin.user_id, @new_admin_role_id
FROM (
    SELECT user_id,
           ROW_NUMBER() OVER (ORDER BY user_id) AS rn
    FROM sys_user_role
    WHERE role_id = 1
) old_admin
WHERE @new_admin_role_id IS NOT NULL
  AND old_admin.rn <= 3;

-- 新超级管理员角色最多保留 3 个用户。
DELETE ur
FROM sys_user_role ur
JOIN (
    SELECT user_id
    FROM (
        SELECT user_id,
               ROW_NUMBER() OVER (ORDER BY user_id) AS rn
        FROM sys_user_role
        WHERE role_id = @new_admin_role_id
    ) ranked
    WHERE ranked.rn > 3
) extra ON extra.user_id = ur.user_id
WHERE ur.role_id = @new_admin_role_id;

-- 旧超级管理员角色停用后不再保留用户绑定。
DELETE FROM sys_user_role
WHERE role_id = 1
  AND @new_admin_role_id IS NOT NULL
  AND @new_admin_role_id <> 1;

-- 验证结果。
SELECT 'new_admin_role' AS check_item, role_id, role_name, role_key, status, del_flag
FROM sys_role
WHERE role_key = 'admin';

SELECT 'new_admin_user_count' AS check_item, COUNT(*) AS value
FROM sys_user_role
WHERE role_id = @new_admin_role_id;

SELECT 'legacy_role' AS check_item, role_id, role_name, role_key, status, del_flag
FROM sys_role
WHERE role_id = 1;
