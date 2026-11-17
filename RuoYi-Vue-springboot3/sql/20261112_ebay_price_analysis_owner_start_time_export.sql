-- ============================================================
-- 【本脚本含 INSERT，需用户审批后执行】
-- ============================================================
-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：价格分析新增「负责人」「上架时间」两个导出列权限，挂在「导出」按钮下，
--       与已有 19 个导出列权限同一形态（只控制 Excel 导出列，不控制页面展示）。
-- 授权：新建的两个权限授予「当前已有 SKU 导出列权限」的有效角色——
--       与这些角色现在能导出的列保持一致；管理员之后可在角色管理里单独取消。
-- 幂等：按 perms 判重；已存在的权限不重复插入、不重新授权（不会勾回管理员取消的授权）。
-- 依赖：新版 Java（EbayPriceAnalysisController 导出列清单含 owner_name、listing_start_time）。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

SET @export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='operations:ebayPriceAnalysis:export'
  ORDER BY menu_id LIMIT 1
);
SET @sku_column_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='operations:ebayPriceAnalysis:exportColumn:sku'
  ORDER BY menu_id LIMIT 1
);

DROP TEMPORARY TABLE IF EXISTS tmp_price_analysis_new_columns;
CREATE TEMPORARY TABLE tmp_price_analysis_new_columns (
  field_key VARCHAR(64) PRIMARY KEY,
  field_title VARCHAR(64) NOT NULL,
  sort_order INT NOT NULL,
  is_new TINYINT NOT NULL DEFAULT 0
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO tmp_price_analysis_new_columns (field_key,field_title,sort_order) VALUES
('owner_name','负责人',120),
('listing_start_time','上架时间',121);

START TRANSACTION;
UPDATE tmp_price_analysis_new_columns c
SET is_new = NOT EXISTS (
    SELECT 1 FROM sys_menu m
    WHERE m.perms=CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key)
          COLLATE utf8mb4_unicode_ci
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark
)
SELECT CONCAT('导出字段-',c.field_title),@export_id,c.sort_order,'',NULL,NULL,'',
       1,0,'F','0','0',CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key),
       '#','SYSTEM',NOW(),'只控制价格分析Excel导出列，不控制页面展示'
FROM tmp_price_analysis_new_columns c
WHERE c.is_new=1 AND @export_id IS NOT NULL;

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_role_menu sku_grant ON sku_grant.role_id=r.role_id AND sku_grant.menu_id=@sku_column_id
JOIN tmp_price_analysis_new_columns c ON c.is_new=1
JOIN sys_menu m ON m.parent_id=@export_id AND m.menu_type='F' AND m.status='0'
    AND m.perms=CONCAT('operations:ebayPriceAnalysis:exportColumn:',c.field_key)
        COLLATE utf8mb4_unicode_ci
WHERE r.status='0' AND r.del_flag='0' AND @sku_column_id IS NOT NULL;
COMMIT;

-- 校验：应返回 2 行，parent_id 为导出按钮，role_grants 与 SKU 导出列的授权角色数一致。
SELECT m.menu_id,m.parent_id,m.menu_name,m.perms,
       (SELECT COUNT(*) FROM sys_role_menu rm WHERE rm.menu_id=m.menu_id) AS role_grants,
       (SELECT COUNT(*) FROM sys_role_menu rm WHERE rm.menu_id=@sku_column_id) AS sku_column_grants
FROM sys_menu m
WHERE m.perms IN ('operations:ebayPriceAnalysis:exportColumn:owner_name',
                  'operations:ebayPriceAnalysis:exportColumn:listing_start_time');

DROP TEMPORARY TABLE IF EXISTS tmp_price_analysis_new_columns;
-- 执行后：角色权限有变化的账号退出重新登录。
