-- SOP / 选竞品商品库、站点公式配置、菜单及权限。
-- 在 jmh_data_platform 库执行；可重复执行，不删除已有业务数据。
USE jmh_data_platform;

CREATE TABLE IF NOT EXISTS ebay_competitor_formula_config (
  site_code                 VARCHAR(8)     NOT NULL COMMENT '站点代码：UK/DE/US',
  site_name                 VARCHAR(32)    NOT NULL COMMENT '站点名称',
  currency                  VARCHAR(8)     NOT NULL COMMENT '站点币种',
  platform_net_rate         DECIMAL(12,6)  NOT NULL COMMENT '扣除平台费用后的净收入比例',
  volumetric_divisor        DECIMAL(12,4)  NOT NULL DEFAULT 6000 COMMENT '体积重除数',
  fixed_fee                 DECIMAL(12,4)  DEFAULT NULL COMMENT 'UK/DE固定费用（当地币）',
  weight_handling_rate      DECIMAL(12,4)  DEFAULT NULL COMMENT 'UK/DE重量处理费率（当地币/kg）',
  sea_first_leg_rate        DECIMAL(12,4)  NOT NULL COMMENT '海运底价公式头程费率（人民币/kg）',
  profit_first_leg_rate     DECIMAL(12,4)  DEFAULT NULL COMMENT '海运利润率公式头程费率（人民币/kg）',
  target_cost_first_leg_rate DECIMAL(12,4) DEFAULT NULL COMMENT '目标产品成本公式头程费率（人民币/kg）',
  rail_first_leg_rate       DECIMAL(12,4)  DEFAULT NULL COMMENT '铁路头程费率（人民币/kg）',
  small_weight_threshold    DECIMAL(12,4)  DEFAULT NULL COMMENT 'US小件计费阈值（kg）',
  small_fixed_fee           DECIMAL(12,4)  DEFAULT NULL COMMENT 'US小件固定费用（美元）',
  large_fixed_fee           DECIMAL(12,4)  DEFAULT NULL COMMENT 'US大件固定费用（美元）',
  small_delivery_rate       DECIMAL(12,4)  DEFAULT NULL COMMENT 'US小件尾程费率（美元/kg）',
  large_delivery_rate       DECIMAL(12,4)  DEFAULT NULL COMMENT 'US大件尾程费率（美元/kg）',
  chargeable_volume_factor  DECIMAL(12,6)  NOT NULL DEFAULT 1 COMMENT '计费体积重系数',
  formula_version           VARCHAR(32)    NOT NULL COMMENT '公式版本',
  status                    CHAR(1)        NOT NULL DEFAULT '0' COMMENT '状态：0正常，1停用',
  update_by                 VARCHAR(64)    DEFAULT NULL COMMENT '更新人',
  update_time               DATETIME       DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (site_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay选竞品站点公式配置';

-- 兼容旧环境：US测试表的底价、利润率、目标成本分别使用3个不同的头程费率。
SET @add_profit_rate_sql := IF(
  EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='ebay_competitor_formula_config'
      AND column_name='profit_first_leg_rate'
  ),
  'SELECT 1',
  'ALTER TABLE ebay_competitor_formula_config ADD COLUMN profit_first_leg_rate DECIMAL(12,4) DEFAULT NULL COMMENT ''海运利润率公式头程费率（人民币/kg）'' AFTER sea_first_leg_rate'
);
PREPARE add_profit_rate_stmt FROM @add_profit_rate_sql;
EXECUTE add_profit_rate_stmt;
DEALLOCATE PREPARE add_profit_rate_stmt;

SET @add_target_rate_sql := IF(
  EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='ebay_competitor_formula_config'
      AND column_name='target_cost_first_leg_rate'
  ),
  'SELECT 1',
  'ALTER TABLE ebay_competitor_formula_config ADD COLUMN target_cost_first_leg_rate DECIMAL(12,4) DEFAULT NULL COMMENT ''目标产品成本公式头程费率（人民币/kg）'' AFTER profit_first_leg_rate'
);
PREPARE add_target_rate_stmt FROM @add_target_rate_sql;
EXECUTE add_target_rate_stmt;
DEALLOCATE PREPARE add_target_rate_stmt;

INSERT IGNORE INTO ebay_competitor_formula_config (
  site_code,site_name,currency,platform_net_rate,volumetric_divisor,
  fixed_fee,weight_handling_rate,sea_first_leg_rate,profit_first_leg_rate,
  target_cost_first_leg_rate,rail_first_leg_rate,
  small_weight_threshold,small_fixed_fee,large_fixed_fee,
  small_delivery_rate,large_delivery_rate,chargeable_volume_factor,
  formula_version,status,update_by,update_time
) VALUES
  ('UK','英国站','GBP',0.705000,6000,2.0000,0.3000,9.2000,9.2000,9.2000,12.8000,
   NULL,NULL,NULL,NULL,NULL,1.000000,'2026-08-v1','0','SYSTEM',NOW()),
  ('DE','德国站','EUR',0.678000,6000,3.5000,0.3000,8.4200,8.4200,8.4200,15.0000,
   NULL,NULL,NULL,NULL,NULL,1.000000,'2026-08-v1','0','SYSTEM',NOW()),
  ('US','美国站','USD',0.857500,6000,NULL,NULL,8.0000,21.0000,6.0000,NULL,
   0.5000,4.0000,8.0000,8.0000,1.7000,0.800000,'2026-08-us-excel-v2','0','SYSTEM',NOW());

UPDATE ebay_competitor_formula_config
SET profit_first_leg_rate=COALESCE(profit_first_leg_rate,sea_first_leg_rate),
    target_cost_first_leg_rate=COALESCE(target_cost_first_leg_rate,sea_first_leg_rate)
WHERE site_code IN ('UK','DE');

UPDATE ebay_competitor_formula_config
SET profit_first_leg_rate=21.0000,
    target_cost_first_leg_rate=6.0000,
    formula_version='2026-08-us-excel-v2',
    update_by='SYSTEM',update_time=NOW()
WHERE site_code='US';

CREATE TABLE IF NOT EXISTS ebay_competitor_product (
  id                          BIGINT         NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  site_code                   VARCHAR(8)     NOT NULL COMMENT '站点代码：UK/DE/US',
  marketplace_id              VARCHAR(32)    NOT NULL COMMENT 'eBay Marketplace ID',
  currency                    VARCHAR(8)     NOT NULL COMMENT '售价币种',
  ebay_item_id                VARCHAR(32)    NOT NULL COMMENT 'eBay商品ID',
  oe                          VARCHAR(500)   DEFAULT NULL COMMENT 'OE号',
  sku                         VARCHAR(255)   DEFAULT NULL COMMENT 'SKU',
  reference_url               VARCHAR(1000)  NOT NULL COMMENT '商品参考链接',
  remark                      VARCHAR(1000)  DEFAULT NULL COMMENT '备注',
  sale_price                  DECIMAL(18,2)  NOT NULL COMMENT '实际卖价（站点币种），四舍五入保留2位',
  product_cost_cny            DECIMAL(18,2)  NOT NULL COMMENT '产品成本（人民币），四舍五入保留2位',
  length_cm                   DECIMAL(18,2)  NOT NULL COMMENT '长（cm），四舍五入保留2位',
  width_cm                    DECIMAL(18,2)  NOT NULL COMMENT '宽（cm），四舍五入保留2位',
  height_cm                   DECIMAL(18,2)  NOT NULL COMMENT '高（cm），四舍五入保留2位',
  volumetric_weight_kg        DECIMAL(18,2)  NOT NULL COMMENT '体积重（kg），四舍五入保留2位',
  actual_weight_kg            DECIMAL(18,2)  NOT NULL COMMENT '实重（kg），四舍五入保留2位',
  exchange_rate               DECIMAL(18,2)  NOT NULL COMMENT '实时汇率（人民币/站点币种），四舍五入保留2位',
  sea_floor_price             DECIMAL(18,2)  NOT NULL COMMENT '海运底价反推结果，四舍五入保留2位',
  rail_floor_price            DECIMAL(18,2)  DEFAULT NULL COMMENT '铁路底价反推结果，四舍五入保留2位',
  sea_profit_rate             DECIMAL(18,6)  NOT NULL COMMENT '海运利润率',
  rail_profit_rate            DECIMAL(18,6)  DEFAULT NULL COMMENT '铁路利润率',
  target_profit_rate          DECIMAL(18,6)  NOT NULL COMMENT '目标/固定利润率',
  target_product_cost_sea     DECIMAL(18,2)  NOT NULL COMMENT '目标产品成本（海运），四舍五入保留2位',
  target_product_cost_rail    DECIMAL(18,2)  DEFAULT NULL COMMENT '目标产品成本（铁路），四舍五入保留2位',
  local_image_url             VARCHAR(500)   NOT NULL COMMENT '本地商品图片访问地址',
  formula_version             VARCHAR(32)    NOT NULL COMMENT '保存时使用的公式版本',
  create_by                   VARCHAR(64)    DEFAULT NULL COMMENT '创建人',
  create_time                 DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_by                   VARCHAR(64)    DEFAULT NULL COMMENT '更新人',
  update_time                 DATETIME       DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_competitor_site_item (site_code,ebay_item_id),
  KEY idx_ebay_competitor_oe (oe(191)),
  KEY idx_ebay_competitor_sku (sku(191)),
  KEY idx_ebay_competitor_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay选竞品已保存商品库';

-- 兼容已执行过旧版脚本的环境：商品ID就是编号，SKU No.就是SKU，删除两个重复字段。
SET @drop_duplicate_columns := (
  SELECT GROUP_CONCAT(CONCAT('DROP COLUMN `',column_name,'`') SEPARATOR ', ')
  FROM information_schema.columns
  WHERE table_schema=DATABASE() AND table_name='ebay_competitor_product'
    AND column_name IN ('sequence_no','sku_no')
);
SET @drop_duplicate_sql := IF(
  @drop_duplicate_columns IS NULL,
  'SELECT 1',
  CONCAT('ALTER TABLE ebay_competitor_product ',@drop_duplicate_columns)
);
PREPARE drop_duplicate_stmt FROM @drop_duplicate_sql;
EXECUTE drop_duplicate_stmt;
DEALLOCATE PREPARE drop_duplicate_stmt;

-- 兼容已执行过旧版脚本的环境：金额、尺寸、重量、汇率和计算金额统一为2位小数。
ALTER TABLE ebay_competitor_product
  MODIFY COLUMN sale_price DECIMAL(18,2) NOT NULL COMMENT '实际卖价（站点币种），四舍五入保留2位',
  MODIFY COLUMN product_cost_cny DECIMAL(18,2) NOT NULL COMMENT '产品成本（人民币），四舍五入保留2位',
  MODIFY COLUMN length_cm DECIMAL(18,2) NOT NULL COMMENT '长（cm），四舍五入保留2位',
  MODIFY COLUMN width_cm DECIMAL(18,2) NOT NULL COMMENT '宽（cm），四舍五入保留2位',
  MODIFY COLUMN height_cm DECIMAL(18,2) NOT NULL COMMENT '高（cm），四舍五入保留2位',
  MODIFY COLUMN volumetric_weight_kg DECIMAL(18,2) NOT NULL COMMENT '体积重（kg），四舍五入保留2位',
  MODIFY COLUMN actual_weight_kg DECIMAL(18,2) NOT NULL COMMENT '实重（kg），四舍五入保留2位',
  MODIFY COLUMN exchange_rate DECIMAL(18,2) NOT NULL COMMENT '实时汇率（人民币/站点币种），四舍五入保留2位',
  MODIFY COLUMN sea_floor_price DECIMAL(18,2) NOT NULL COMMENT '海运底价反推结果，四舍五入保留2位',
  MODIFY COLUMN rail_floor_price DECIMAL(18,2) DEFAULT NULL COMMENT '铁路底价反推结果，四舍五入保留2位',
  MODIFY COLUMN target_product_cost_sea DECIMAL(18,2) NOT NULL COMMENT '目标产品成本（海运），四舍五入保留2位',
  MODIFY COLUMN target_product_cost_rail DECIMAL(18,2) DEFAULT NULL COMMENT '目标产品成本（铁路），四舍五入保留2位';

-- 使用用户提供的Excel公式回填已有US商品；原始体积重由尺寸/6000计算，展示和存库仍为2位。
UPDATE ebay_competitor_product p
JOIN ebay_competitor_formula_config c ON c.site_code=p.site_code AND c.site_code='US'
SET p.volumetric_weight_kg=ROUND(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,2),
    p.sea_profit_rate=ROUND((
      p.sale_price*c.platform_net_rate
      -(p.product_cost_cny+c.profit_first_leg_rate*(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor))/p.exchange_rate
      -IF(GREATEST(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,p.actual_weight_kg)<c.small_weight_threshold,c.small_fixed_fee,c.large_fixed_fee)
      -IF(GREATEST(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,p.actual_weight_kg)<c.small_weight_threshold,c.small_delivery_rate,c.large_delivery_rate)
       *GREATEST(c.chargeable_volume_factor*(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor),p.actual_weight_kg)
    )/p.sale_price,6),
    p.sea_floor_price=ROUND((
      (p.product_cost_cny+c.sea_first_leg_rate*(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor))/p.exchange_rate
      +IF(GREATEST(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,p.actual_weight_kg)<c.small_weight_threshold,c.small_fixed_fee,c.large_fixed_fee)
      +IF(GREATEST(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,p.actual_weight_kg)<c.small_weight_threshold,c.small_delivery_rate,c.large_delivery_rate)
       *GREATEST(c.chargeable_volume_factor*(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor),p.actual_weight_kg)
    )/(c.platform_net_rate-p.target_profit_rate),2),
    p.target_product_cost_sea=ROUND(
      p.exchange_rate*(
        p.sale_price*c.platform_net_rate
        -IF(GREATEST(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,p.actual_weight_kg)<c.small_weight_threshold,c.small_fixed_fee,c.large_fixed_fee)
        -IF(GREATEST(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor,p.actual_weight_kg)<c.small_weight_threshold,c.small_delivery_rate,c.large_delivery_rate)
         *GREATEST(c.chargeable_volume_factor*(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor),p.actual_weight_kg)
        -p.target_profit_rate*p.sale_price
      )-c.target_cost_first_leg_rate*(p.length_cm*p.width_cm*p.height_cm/c.volumetric_divisor),2),
    p.formula_version=c.formula_version,
    p.update_by='SYSTEM',p.update_time=NOW();

CREATE TABLE IF NOT EXISTS ebay_competitor_product_image (
  id               BIGINT        NOT NULL AUTO_INCREMENT COMMENT '图片主键ID',
  product_id       BIGINT        NOT NULL COMMENT '竞品商品ID',
  sort_no          INT           NOT NULL COMMENT '图片顺序，从1开始',
  local_image_url  VARCHAR(500)  NOT NULL COMMENT '本地图片访问地址',
  create_time      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_competitor_product_image_sort (product_id,sort_no),
  KEY idx_ebay_competitor_product_image_product (product_id),
  CONSTRAINT fk_ebay_competitor_product_image_product
    FOREIGN KEY (product_id) REFERENCES ebay_competitor_product(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='eBay选竞品商品本地图片明细';

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND (path='sop' OR menu_name='SOP')
  ORDER BY CASE WHEN path='sop' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'SOP',0,5,'sop',NULL,NULL,'Sop',1,0,'M','0','0',NULL,'guide',
       'SYSTEM',NOW(),'标准作业流程与业务数据处理'
WHERE @sop_menu_id IS NULL;

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M' AND (path='sop' OR menu_name='SOP')
  ORDER BY CASE WHEN path='sop' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @competitor_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id AND
    (path='competitor-lookup' OR component='sop/competitorLookup/index' OR perms='sop:competitor:list')
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '选竞品',@sop_menu_id,3,'competitor-lookup','sop/competitorLookup/index',NULL,'SopCompetitorLookup',
       1,0,'C','0','0','sop:competitor:list','search',
       'SYSTEM',NOW(),'eBay竞品商品库与利润测算'
WHERE @sop_menu_id IS NOT NULL AND @competitor_menu_id IS NULL;

SET @competitor_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id AND
    (path='competitor-lookup' OR component='sop/competitorLookup/index' OR perms='sop:competitor:list')
  ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name='选竞品',parent_id=@sop_menu_id,order_num=3,
    path='competitor-lookup',component='sop/competitorLookup/index',
    route_name='SopCompetitorLookup',is_frame=1,is_cache=0,
    menu_type='C',visible='0',status='0',perms='sop:competitor:list',icon='search',
    update_by='SYSTEM',update_time=NOW(),remark='eBay竞品商品库与利润测算'
WHERE menu_id=@competitor_menu_id;

-- 页面按钮权限：查询/批量导入eBay、保存、编辑、删除和导出商品。
INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '查询eBay竞品',@competitor_menu_id,1,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:query','#','SYSTEM',NOW(),'查询单个eBay商品链接'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:query');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '保存竞品',@competitor_menu_id,2,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:save','#','SYSTEM',NOW(),'保存利润测算合格的竞品'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:save');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '编辑竞品',@competitor_menu_id,3,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:edit','#','SYSTEM',NOW(),'编辑已保存竞品并重新计算利润'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:edit');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '删除竞品',@competitor_menu_id,4,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:remove','#','SYSTEM',NOW(),'删除已保存竞品及本地图片'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:remove');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '批量导入竞品链接',@competitor_menu_id,5,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:import','#','SYSTEM',NOW(),'解析Excel链接并逐条抓取eBay竞品'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:import');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导出竞品商品库',@competitor_menu_id,6,'',NULL,NULL,'',1,0,'F','0','0',
       'sop:competitor:export','#','SYSTEM',NOW(),'导出选中或全部已保存竞品商品'
WHERE @competitor_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:competitor:export');

SET @competitor_query_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:query'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);
SET @competitor_save_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:save'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);
SET @competitor_edit_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:edit'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);
SET @competitor_remove_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:remove'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);
SET @competitor_import_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:import'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);
SET @competitor_export_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:competitor:export'
  ORDER BY CASE WHEN parent_id=@competitor_menu_id THEN 0 ELSE 1 END,menu_id LIMIT 1
);

UPDATE sys_menu SET menu_name='查询eBay竞品',parent_id=@competitor_menu_id,order_num=1,
  menu_type='F',visible='0',status='0',perms='sop:competitor:query',
  update_by='SYSTEM',update_time=NOW(),remark='查询单个eBay商品链接'
WHERE menu_id=@competitor_query_id;

UPDATE sys_menu SET menu_name='保存竞品',parent_id=@competitor_menu_id,order_num=2,
  menu_type='F',visible='0',status='0',perms='sop:competitor:save',
  update_by='SYSTEM',update_time=NOW(),remark='保存利润测算合格的竞品'
WHERE menu_id=@competitor_save_id;

UPDATE sys_menu SET menu_name='编辑竞品',parent_id=@competitor_menu_id,order_num=3,
  menu_type='F',visible='0',status='0',perms='sop:competitor:edit',
  update_by='SYSTEM',update_time=NOW(),remark='编辑已保存竞品并重新计算利润'
WHERE menu_id=@competitor_edit_id;

UPDATE sys_menu SET menu_name='删除竞品',parent_id=@competitor_menu_id,order_num=4,
  menu_type='F',visible='0',status='0',perms='sop:competitor:remove',
  update_by='SYSTEM',update_time=NOW(),remark='删除已保存竞品及本地图片'
WHERE menu_id=@competitor_remove_id;

UPDATE sys_menu SET menu_name='批量导入竞品链接',parent_id=@competitor_menu_id,order_num=5,
  menu_type='F',visible='0',status='0',perms='sop:competitor:import',
  update_by='SYSTEM',update_time=NOW(),remark='解析Excel链接并逐条抓取eBay竞品'
WHERE menu_id=@competitor_import_id;

UPDATE sys_menu SET menu_name='导出竞品商品库',parent_id=@competitor_menu_id,order_num=6,
  menu_type='F',visible='0',status='0',perms='sop:competitor:export',
  update_by='SYSTEM',update_time=NOW(),remark='导出选中或全部已保存竞品商品'
WHERE menu_id=@competitor_export_id;

-- 给管理员角色和 leiyongyu 账户关联的全部角色授予完整权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN (
  SELECT @sop_menu_id AS menu_id
  UNION ALL SELECT @competitor_menu_id
  UNION ALL SELECT @competitor_query_id
  UNION ALL SELECT @competitor_save_id
  UNION ALL SELECT @competitor_edit_id
  UNION ALL SELECT @competitor_remove_id
  UNION ALL SELECT @competitor_import_id
  UNION ALL SELECT @competitor_export_id
) m ON m.menu_id IS NOT NULL
WHERE r.role_key='admin' AND r.status='0';

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN (
  SELECT @sop_menu_id AS menu_id
  UNION ALL SELECT @competitor_menu_id
  UNION ALL SELECT @competitor_query_id
  UNION ALL SELECT @competitor_save_id
  UNION ALL SELECT @competitor_edit_id
  UNION ALL SELECT @competitor_remove_id
  UNION ALL SELECT @competitor_import_id
  UNION ALL SELECT @competitor_export_id
) m ON m.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu';

SELECT menu_id,parent_id,menu_name,order_num,path,component,menu_type,perms,status
FROM sys_menu
WHERE menu_id IN (@sop_menu_id,@competitor_menu_id,@competitor_query_id,@competitor_save_id,
                  @competitor_edit_id,@competitor_remove_id,@competitor_import_id,@competitor_export_id)
ORDER BY parent_id,order_num,menu_id;
