-- 目标库：jmh_data_platform（Java ERP 数据库）。
-- 新增“运营中心 / eBay / 店铺分析 / eBay补货2.0”菜单。
-- 创建人工时效表、按“站点+完整SKU”汇总的仓租表，并给 leiyongyu 的有效角色补齐完整祖先链和功能权限。
USE jmh_data_platform;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_lead_time (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '人工时效配置主键',
  site VARCHAR(100) NOT NULL COMMENT '站点',
  sku VARCHAR(255) NOT NULL COMMENT '完整库存SKU',
  chengdu_warehouse_to_warehouse_days INT UNSIGNED NULL COMMENT '成都仓到仓时间，单位：天',
  chengdu_qc_outbound_days INT UNSIGNED NULL COMMENT '成都质检出仓时间，单位：天',
  overseas_transit_to_listing_days INT UNSIGNED NULL COMMENT '海外在途到上架时间，单位：天',
  create_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '创建人',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '更新人',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_replenishment_v2_lead_time_site_sku (site,sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0站点SKU人工时效配置表';

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_warehouse_rent (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '仓租汇总记录主键',
  site VARCHAR(100) NOT NULL COMMENT '由仓库代码映射得到的站点',
  sku VARCHAR(255) NOT NULL COMMENT '去除JMH-前缀后的完整库存SKU',
  warehouse_codes VARCHAR(255) NOT NULL DEFAULT '' COMMENT '参与汇总的仓库代码，多个代码以英文逗号分隔',
  source_row_count INT UNSIGNED NOT NULL COMMENT '该站点SKU对应的源文件明细行数',
  warehouse_rent_amount_cny DECIMAL(18,4) NOT NULL COMMENT '按固定汇率换算并汇总的总金额人民币值，不含税且包含附加费',
  import_batch_id CHAR(32) NOT NULL COMMENT '本次整表导入批次编号',
  source_file_name VARCHAR(255) NOT NULL COMMENT '本次导入的Excel源文件名',
  imported_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '导入操作人',
  import_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导入时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_replenishment_v2_warehouse_rent_site_sku (site,sku),
  KEY idx_ebay_replenishment_v2_warehouse_rent_batch (import_batch_id),
  KEY idx_ebay_replenishment_v2_warehouse_rent_time (import_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0站点SKU仓租明细总费用人民币聚合表';

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_warehouse_rent_import_lock (
  id TINYINT UNSIGNED NOT NULL COMMENT '固定控制行ID',
  lock_key VARCHAR(64) NOT NULL COMMENT '仓租增量导入锁标识',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '最后锁定时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_ebay_replenishment_v2_rent_lock_key (lock_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0仓租按仓库、商品编码和账单日增量覆盖并发控制表';

INSERT INTO ebay_replenishment_v2_warehouse_rent_import_lock(id,lock_key)
VALUES (1,'warehouse_rent_import')
ON DUPLICATE KEY UPDATE lock_key=VALUES(lock_key);

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_warehouse_rent_detail (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '仓租源明细主键',
  order_no VARCHAR(128) NULL COMMENT '仓租单号，仅用于来源追溯，不参与覆盖键',
  warehouse_code VARCHAR(64) NOT NULL COMMENT '仓库代码',
  product_code VARCHAR(255) NOT NULL COMMENT '商品编码',
  goods_barcode VARCHAR(255) NULL COMMENT '商品条码',
  product_name VARCHAR(500) NULL COMMENT '商品名称',
  reference_no VARCHAR(255) NULL COMMENT '参考号',
  billing_time_text VARCHAR(100) NULL COMMENT '计费时间原始文本',
  listing_time_text VARCHAR(100) NULL COMMENT '上架时间原始文本',
  dimensions_text VARCHAR(255) NULL COMMENT '尺寸原始文本',
  quantity_text VARCHAR(100) NULL COMMENT '数量原始文本',
  volume_m3_text VARCHAR(100) NULL COMMENT '体积原始文本',
  product_weight_kg_text VARCHAR(100) NULL COMMENT '重量原始文本',
  warehouse_rent_excl_tax_text VARCHAR(100) NULL COMMENT '仓租不含税原始文本',
  billing_currency VARCHAR(32) NULL COMMENT '计费币种',
  inventory_age_days_text VARCHAR(100) NULL COMMENT '库龄天数原始文本',
  goods_type VARCHAR(100) NULL COMMENT '货物类型',
  billing_type VARCHAR(100) NULL COMMENT '计费类型',
  storage_physical_form VARCHAR(100) NULL COMMENT '存储物理形态',
  peak_season_surcharge_excl_tax_text VARCHAR(100) NULL COMMENT '旺季附加费不含税原始文本',
  over_age_surcharge_excl_tax_text VARCHAR(100) NULL COMMENT '超龄附加费不含税原始文本',
  oversized_surcharge_excl_tax_text VARCHAR(100) NULL COMMENT '超尺寸附加费不含税原始文本',
  total_amount_excl_tax_text VARCHAR(100) NULL COMMENT '总金额不含税原始文本',
  site VARCHAR(100) NOT NULL COMMENT '仓库代码映射后的站点',
  sku VARCHAR(255) NOT NULL COMMENT '去除JMH-前缀后的完整库存SKU',
  exchange_rate DECIMAL(18,6) NOT NULL COMMENT '导入时使用的人民币汇率',
  exchange_rate_month VARCHAR(7) NULL COMMENT '所用汇率月份，当月缺失时记录回退月份',
  warehouse_rent_amount_cny DECIMAL(18,4) NOT NULL COMMENT '该明细人民币仓租费用',
  import_batch_id CHAR(32) NOT NULL COMMENT '导入批次编号',
  source_file_name VARCHAR(255) NOT NULL COMMENT 'Excel源文件名',
  source_sheet_name VARCHAR(128) NOT NULL COMMENT '固定仓租明细Sheet名',
  source_row_num INT UNSIGNED NOT NULL COMMENT 'Excel源行号',
  imported_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '导入操作人',
  import_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导入时间',
  PRIMARY KEY (id),
  KEY idx_ebay_replenishment_v2_rent_detail_order (order_no),
  KEY idx_ebay_replenishment_v2_rent_detail_warehouse_product_billing (warehouse_code,product_code,billing_time_text),
  KEY idx_ebay_replenishment_v2_rent_detail_site_sku (site,sku),
  KEY idx_ebay_replenishment_v2_rent_detail_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0仓租明细Sheet结构化源数据，按仓库、商品编码和账单日增量覆盖';

SET @operations_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=0 AND menu_type='M'
    AND (path='operations' OR menu_name='运营中心')
  ORDER BY CASE WHEN path='operations' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay',@operations_id,2,'ebay',NULL,NULL,'',
       1,0,'M','0','0','','shopping','SYSTEM',NOW(),'运营中心eBay业务目录'
WHERE @operations_id IS NOT NULL AND @ebay_dir_id IS NULL;
SET @ebay_dir_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@operations_id AND menu_type='M'
    AND (LOWER(path)='ebay' OR LOWER(menu_name)='ebay')
  ORDER BY CASE WHEN LOWER(path)='ebay' THEN 0 ELSE 1 END,menu_id LIMIT 1
);

SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '店铺分析',@ebay_dir_id,20,'store-analysis',NULL,NULL,'',
       1,0,'M','0','0','','shop','SYSTEM',NOW(),'eBay店铺分析业务目录'
WHERE @ebay_dir_id IS NOT NULL AND @store_analysis_id IS NULL;
SET @store_analysis_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@ebay_dir_id AND menu_type='M'
    AND (path='store-analysis' OR menu_name='店铺分析')
  ORDER BY CASE WHEN path='store-analysis' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_dir_id,menu_name='店铺分析',order_num=20,
    path='store-analysis',component=NULL,query=NULL,route_name='',
    is_frame=1,is_cache=0,menu_type='M',visible='0',status='0',
    perms='',icon='shop',update_by='SYSTEM',update_time=NOW(),
    remark='eBay店铺分析业务目录'
WHERE menu_id=@store_analysis_id;

SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT 'eBay补货2.0',@store_analysis_id,4,'replenishment-v2',
       'operations/ebay/replenishmentV2/index',NULL,'EbayReplenishmentV2',
       1,0,'C','0','0','operations:ebayReplenishmentV2:list','shopping',
       'SYSTEM',NOW(),'eBay补货2.0近三个月销量、毛利与退货分析'
WHERE @store_analysis_id IS NOT NULL AND @ebay_replenishment_v2_id IS NULL;
SET @ebay_replenishment_v2_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C' AND (
    perms='operations:ebayReplenishmentV2:list'
    OR component='operations/ebay/replenishmentV2/index'
    OR route_name='EbayReplenishmentV2'
    OR (parent_id=@store_analysis_id AND path='replenishment-v2')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:list' THEN 0
    WHEN component='operations/ebay/replenishmentV2/index' THEN 1
    WHEN route_name='EbayReplenishmentV2' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@store_analysis_id,menu_name='eBay补货2.0',order_num=4,
    path='replenishment-v2',component='operations/ebay/replenishmentV2/index',
    query=NULL,route_name='EbayReplenishmentV2',is_frame=1,is_cache=0,
    menu_type='C',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:list',icon='shopping',
    update_by='SYSTEM',update_time=NOW(),
    remark='eBay补货2.0近三个月销量、毛利与退货分析'
WHERE menu_id=@ebay_replenishment_v2_id AND @store_analysis_id IS NOT NULL;

SET @lead_time_edit_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:editLeadTime'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='维护补货时效')
  )
  ORDER BY CASE WHEN perms='operations:ebayReplenishmentV2:editLeadTime' THEN 0 ELSE 1 END,
           menu_id
  LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '维护补货时效',@ebay_replenishment_v2_id,1,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:editLeadTime','',
       'SYSTEM',NOW(),'按站点和完整SKU维护三个补货时效天数'
WHERE @ebay_replenishment_v2_id IS NOT NULL AND @lead_time_edit_id IS NULL;
SET @lead_time_edit_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:editLeadTime'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='维护补货时效')
  )
  ORDER BY CASE WHEN perms='operations:ebayReplenishmentV2:editLeadTime' THEN 0 ELSE 1 END,
           menu_id
  LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_replenishment_v2_id,menu_name='维护补货时效',order_num=1,
    path='',component=NULL,query=NULL,route_name='',is_frame=1,is_cache=0,
    menu_type='F',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:editLeadTime',icon='',
    update_by='SYSTEM',update_time=NOW(),
    remark='按站点和完整SKU维护三个补货时效天数'
WHERE menu_id=@lead_time_edit_id AND @ebay_replenishment_v2_id IS NOT NULL;

SET @warehouse_rent_import_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:importWarehouseRent'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='上传仓租明细')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:importWarehouseRent' THEN 0 ELSE 1
  END,menu_id
  LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '上传仓租明细',@ebay_replenishment_v2_id,2,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:importWarehouseRent','',
       'SYSTEM',NOW(),'上传仓租明细Excel，按仓库、商品编码和账单日增量覆盖明细并重建站点SKU汇总'
WHERE @ebay_replenishment_v2_id IS NOT NULL
  AND @warehouse_rent_import_id IS NULL;
SET @warehouse_rent_import_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND (
    perms='operations:ebayReplenishmentV2:importWarehouseRent'
    OR (parent_id=@ebay_replenishment_v2_id AND menu_name='上传仓租明细')
  )
  ORDER BY CASE
    WHEN perms='operations:ebayReplenishmentV2:importWarehouseRent' THEN 0 ELSE 1
  END,menu_id
  LIMIT 1
);
UPDATE sys_menu
SET parent_id=@ebay_replenishment_v2_id,menu_name='上传仓租明细',order_num=2,
    path='',component=NULL,query=NULL,route_name='',is_frame=1,is_cache=0,
    menu_type='F',visible='0',status='0',
    perms='operations:ebayReplenishmentV2:importWarehouseRent',icon='',
    update_by='SYSTEM',update_time=NOW(),
    remark='上传仓租明细Excel，按仓库、商品编码和账单日增量覆盖明细并重建站点SKU汇总'
WHERE menu_id=@warehouse_rent_import_id
  AND @ebay_replenishment_v2_id IS NOT NULL;

-- 非管理员动态路由从根节点递归构建，四级菜单必须全部授权。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,target.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN (
  SELECT @operations_id AS menu_id
  UNION ALL SELECT @ebay_dir_id
  UNION ALL SELECT @store_analysis_id
  UNION ALL SELECT @ebay_replenishment_v2_id
  UNION ALL SELECT @lead_time_edit_id
  UNION ALL SELECT @warehouse_rent_import_id
) target ON target.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,route_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@ebay_replenishment_v2_id,@lead_time_edit_id,@warehouse_rent_import_id)
ORDER BY parent_id,order_num,menu_id;

SELECT u.user_name,r.role_id,r.role_name,m.menu_id,m.parent_id,m.menu_name,m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu'
  AND m.menu_id IN (@operations_id,@ebay_dir_id,@store_analysis_id,@ebay_replenishment_v2_id,@lead_time_edit_id,@warehouse_rent_import_id)
ORDER BY r.role_id,m.parent_id,m.order_num,m.menu_id;
