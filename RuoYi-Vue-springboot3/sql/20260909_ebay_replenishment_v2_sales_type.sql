-- 补货2.0：人工销售类型（与自动新品/老品分开）。
-- 只新增表及权限按钮；不回填/覆盖历史标记，不给角色自动授权。
USE `jmh_data_platform`;

CREATE TABLE IF NOT EXISTS `ebay_replenishment_v2_sales_type` (
  `site` VARCHAR(100) NOT NULL COMMENT '站点，与订单站点精确匹配',
  `sku` VARCHAR(255) NOT NULL COMMENT '完整SKU，不去除任何前后缀',
  `sales_type` ENUM('NORMAL','BRUSH') NOT NULL DEFAULT 'NORMAL' COMMENT 'NORMAL正常，BRUSH刷单',
  `update_by` VARCHAR(64) NULL COMMENT '最后修改账号，由登录会话提供',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`site`,`sku`),
  KEY `idx_sales_type` (`sales_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='eBay补货2.0人工销售类型；订单重传、切月和刷新不覆盖';

START TRANSACTION;
SET @sales_type_parent = (
  SELECT menu_id FROM sys_menu
  WHERE perms='operations:ebayReplenishmentV2:list' AND menu_type='C'
  ORDER BY menu_id LIMIT 1
);
INSERT INTO sys_menu
  (menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,
   menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '修改销售类型',@sales_type_parent,8,'',NULL,NULL,'',1,0,
       'F','0','0','operations:ebayReplenishmentV2:editSalesType','#','SYSTEM',NOW(),
       '按站点和完整SKU保存正常或刷单；不修改自动新品老品或现有公式'
WHERE @sales_type_parent IS NOT NULL
  AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:ebayReplenishmentV2:editSalesType');
COMMIT;

SELECT IF(@sales_type_parent IS NULL,'ERROR: 未找到补货2.0页面菜单，请先部署父菜单后重跑',
          'OK: 父菜单已找到') AS result;
SELECT menu_id,parent_id,menu_name,perms FROM sys_menu
WHERE perms='operations:ebayReplenishmentV2:editSalesType';
SELECT sales_type,COUNT(*) AS saved_skus FROM ebay_replenishment_v2_sales_type GROUP BY sales_type;
-- 授权后退出重新登录。若仍需leiyongyu当前全权限，可按用户授权另执行08脚本。
-- 不存在手工记录的SKU，列表按正常展示；空表不是部署失败。
