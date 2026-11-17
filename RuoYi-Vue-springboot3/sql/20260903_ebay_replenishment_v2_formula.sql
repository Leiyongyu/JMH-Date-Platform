-- 目标库：jmh_data_platform。
-- eBay补货2.0安全库存/建议补货量全局系数，与原始补货公式完全隔离。
USE jmh_data_platform;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_formula (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  product_level VARCHAR(20) NOT NULL COMMENT '产品分级：S、A、B、C',
  safety_coefficient DECIMAL(10,4) NOT NULL COMMENT '安全库存风险系数',
  suggest_coefficient DECIMAL(10,4) NOT NULL COMMENT '建议补货量系数',
  remark VARCHAR(500) NULL COMMENT '备注',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用 0停用',
  update_by VARCHAR(64) NULL COMMENT '更新者',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_product_level (product_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0安全库存与建议补货量系数配置；与原始补货公式表相互独立';

-- 重复部署不覆盖运营人员已经修改过的系数。
INSERT INTO ebay_replenishment_v2_formula
  (product_level,safety_coefficient,suggest_coefficient,remark,status,update_by)
VALUES
  ('S',0.6000,1.6000,'eBay补货2.0默认S级系数',1,'SYSTEM'),
  ('A',0.4000,1.4000,'eBay补货2.0默认A级系数',1,'SYSTEM'),
  ('B',0.2000,1.2000,'eBay补货2.0默认B级系数；长尾产品-B按本级计算',1,'SYSTEM'),
  ('C',0.0000,0.0000,'eBay补货2.0默认C级系数；C级不补货',1,'SYSTEM')
ON DUPLICATE KEY UPDATE product_level=VALUES(product_level);

SET @ebay_replenishment_v2_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE menu_type='C'
    AND perms='operations:ebayReplenishmentV2:list'
  ORDER BY menu_id
  LIMIT 1
);

SET @formula_permission_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE menu_type='F'
    AND perms='operations:ebayReplenishmentV2:formula'
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '维护补货2.0公式',@ebay_replenishment_v2_id,3,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:formula','',
       'SYSTEM',NOW(),'维护eBay补货2.0全局分级安全系数和补货系数'
WHERE @ebay_replenishment_v2_id IS NOT NULL
  AND @formula_permission_id IS NULL;

SET @formula_permission_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE menu_type='F'
    AND perms='operations:ebayReplenishmentV2:formula'
  ORDER BY menu_id
  LIMIT 1
);

UPDATE sys_menu
SET parent_id=@ebay_replenishment_v2_id,
    menu_name='维护补货2.0公式',order_num=3,path='',component=NULL,
    query=NULL,route_name='',is_frame=1,is_cache=0,menu_type='F',
    visible='0',status='0',perms='operations:ebayReplenishmentV2:formula',
    icon='',update_by='SYSTEM',update_time=NOW(),
    remark='维护eBay补货2.0全局分级安全系数和补货系数'
WHERE menu_id=@formula_permission_id
  AND @ebay_replenishment_v2_id IS NOT NULL;

-- 延续现有约定：给 leiyongyu 的全部有效角色补齐该独立按钮权限。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,@formula_permission_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0'
  AND @formula_permission_id IS NOT NULL;

SELECT product_level,safety_coefficient,suggest_coefficient,status,update_by
FROM ebay_replenishment_v2_formula
ORDER BY FIELD(product_level,'S','A','B','C');

SELECT menu_id,parent_id,menu_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@ebay_replenishment_v2_id,@formula_permission_id)
ORDER BY menu_type,menu_id;
