-- 目标库：jmh_data_platform（Java ERP 数据库）。
-- 新增顶级“采购中心 / 待采购”菜单、待采购业务表及接口权限。
-- 可重复执行；采购中心与运营中心同级，给admin和leiyongyu的有效角色补齐权限。
USE jmh_data_platform;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS procurement_pending_purchase (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '待采购记录主键',
  site VARCHAR(100) NOT NULL COMMENT '站点',
  sku VARCHAR(255) NOT NULL COMMENT '库存SKU',
  purchase_quantity INT UNSIGNED NOT NULL COMMENT '最终采购量',
  purchase_time DATETIME NOT NULL COMMENT '采购确认时间',
  status CHAR(1) NOT NULL DEFAULT '0' COMMENT '采购状态：0待采购，1已采购',
  pending_flag TINYINT NULL DEFAULT 1 COMMENT '待采购唯一标记：待采购为1，已采购为空',
  export_time DATETIME NULL COMMENT '导出并转为已采购的时间',
  create_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '创建人',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  update_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '更新人',
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_pending_site_sku (site, sku, pending_flag),
  KEY idx_status_purchase_time (status, purchase_time),
  KEY idx_site_sku (site, sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采购中心待采购清单';

-- 采购中心必须与运营中心同级；若部署库尚无运营中心，则回退为顶级目录。
SET @procurement_peer_parent_id := COALESCE((
  SELECT parent_id FROM sys_menu
  WHERE menu_type='M' AND (path='operations' OR menu_name='运营中心')
  ORDER BY CASE WHEN path='operations' THEN 0 ELSE 1 END,menu_id LIMIT 1
),0);

SET @procurement_center_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='M'
    AND (path='procurement'
         OR (parent_id=@procurement_peer_parent_id AND menu_name='采购中心'))
  ORDER BY CASE WHEN path='procurement' THEN 0 ELSE 1 END,
           CASE WHEN parent_id=@procurement_peer_parent_id THEN 0 ELSE 1 END,
           menu_id LIMIT 1
);
SET @procurement_order := (
  SELECT COALESCE(MAX(order_num),0) + 1 FROM sys_menu
  WHERE parent_id=@procurement_peer_parent_id
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '采购中心',@procurement_peer_parent_id,@procurement_order,'procurement',NULL,NULL,'',
       1,0,'M','0','0','','shopping','SYSTEM',NOW(),'采购业务顶级目录'
WHERE @procurement_center_id IS NULL;
SET @procurement_center_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='M'
    AND (path='procurement'
         OR (parent_id=@procurement_peer_parent_id AND menu_name='采购中心'))
  ORDER BY CASE WHEN path='procurement' THEN 0 ELSE 1 END,
           CASE WHEN parent_id=@procurement_peer_parent_id THEN 0 ELSE 1 END,
           menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@procurement_peer_parent_id,menu_name='采购中心',path='procurement',component=NULL,query=NULL,
    route_name='',is_frame=1,is_cache=0,menu_type='M',visible='0',status='0',
    perms='',icon='shopping',update_by='SYSTEM',update_time=NOW(),remark='采购业务顶级目录'
WHERE menu_id=@procurement_center_id;

SET @pending_purchase_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C'
    AND (component='procurement/pending/index'
         OR perms='procurement:pendingPurchase:list'
         OR (parent_id=@procurement_center_id AND (path='pending-purchase' OR menu_name='待采购')))
  ORDER BY CASE
    WHEN path='pending-purchase' THEN 0
    WHEN component='procurement/pending/index' THEN 1
    WHEN perms='procurement:pendingPurchase:list' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '待采购',@procurement_center_id,1,'pending-purchase','procurement/pending/index',NULL,
       'PendingPurchase',1,0,'C','0','0','procurement:pendingPurchase:list','list',
       'SYSTEM',NOW(),'待采购记录查询及导出'
WHERE @procurement_center_id IS NOT NULL AND @pending_purchase_id IS NULL;
SET @pending_purchase_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='C'
    AND (component='procurement/pending/index'
         OR perms='procurement:pendingPurchase:list'
         OR (parent_id=@procurement_center_id AND (path='pending-purchase' OR menu_name='待采购')))
  ORDER BY CASE
    WHEN path='pending-purchase' THEN 0
    WHEN component='procurement/pending/index' THEN 1
    WHEN perms='procurement:pendingPurchase:list' THEN 2 ELSE 3
  END,menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@procurement_center_id,menu_name='待采购',order_num=1,path='pending-purchase',
    component='procurement/pending/index',query=NULL,route_name='PendingPurchase',
    is_frame=1,is_cache=0,menu_type='C',visible='0',status='0',
    perms='procurement:pendingPurchase:list',icon='list',update_by='SYSTEM',update_time=NOW(),
    remark='待采购记录查询及导出'
WHERE menu_id=@pending_purchase_id AND @procurement_center_id IS NOT NULL;

SET @pending_add_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:add'
  ORDER BY menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '采购确认',@pending_purchase_id,1,'',NULL,NULL,'',
       1,0,'F','0','0','procurement:pendingPurchase:add','#',
       'SYSTEM',NOW(),'从补货页面确认最终采购量'
WHERE @pending_purchase_id IS NOT NULL AND @pending_add_id IS NULL;
SET @pending_add_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:add'
  ORDER BY menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@pending_purchase_id,menu_name='采购确认',order_num=1,path='',component=NULL,
    query=NULL,route_name='',is_frame=1,is_cache=0,menu_type='F',visible='0',status='0',
    perms='procurement:pendingPurchase:add',icon='#',update_by='SYSTEM',update_time=NOW(),
    remark='从补货页面确认最终采购量'
WHERE menu_id=@pending_add_id AND @pending_purchase_id IS NOT NULL;

SET @pending_export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:export'
  ORDER BY menu_id LIMIT 1
);
INSERT INTO sys_menu(
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导出待采购',@pending_purchase_id,2,'',NULL,NULL,'',
       1,0,'F','0','0','procurement:pendingPurchase:export','#',
       'SYSTEM',NOW(),'导出选中记录并转为已采购'
WHERE @pending_purchase_id IS NOT NULL AND @pending_export_id IS NULL;
SET @pending_export_id := (
  SELECT menu_id FROM sys_menu
  WHERE menu_type='F' AND perms='procurement:pendingPurchase:export'
  ORDER BY menu_id LIMIT 1
);
UPDATE sys_menu
SET parent_id=@pending_purchase_id,menu_name='导出待采购',order_num=2,path='',component=NULL,
    query=NULL,route_name='',is_frame=1,is_cache=0,menu_type='F',visible='0',status='0',
    perms='procurement:pendingPurchase:export',icon='#',update_by='SYSTEM',update_time=NOW(),
    remark='导出选中记录并转为已采购'
WHERE menu_id=@pending_export_id AND @pending_purchase_id IS NOT NULL;

-- 显式给有效admin角色授权。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,target.menu_id
FROM sys_role r
JOIN (
  SELECT @procurement_center_id AS menu_id
  UNION ALL SELECT @pending_purchase_id
  UNION ALL SELECT @pending_add_id
  UNION ALL SELECT @pending_export_id
) target ON target.menu_id IS NOT NULL
WHERE r.role_key='admin' AND r.status='0' AND r.del_flag='0';

-- leiyongyu当前拥有的全部有效角色获得采购中心完整权限。
INSERT IGNORE INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT ur.role_id,target.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN (
  SELECT @procurement_center_id AS menu_id
  UNION ALL SELECT @pending_purchase_id
  UNION ALL SELECT @pending_add_id
  UNION ALL SELECT @pending_export_id
) target ON target.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu'
  AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0';

SELECT menu_id,parent_id,menu_name,order_num,path,component,route_name,menu_type,perms
FROM sys_menu
WHERE menu_id IN (@procurement_center_id,@pending_purchase_id,@pending_add_id,@pending_export_id)
ORDER BY parent_id,order_num,menu_id;

SELECT u.user_name,r.role_id,r.role_name,m.menu_id,m.parent_id,m.menu_name,m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=r.role_id
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE u.user_name='leiyongyu'
  AND m.menu_id IN (@procurement_center_id,@pending_purchase_id,@pending_add_id,@pending_export_id)
ORDER BY r.role_id,m.parent_id,m.order_num,m.menu_id;
