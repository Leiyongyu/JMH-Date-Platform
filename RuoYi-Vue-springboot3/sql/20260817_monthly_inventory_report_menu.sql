-- 目标库：jmh_data_platform（Java ERP数据库）。
-- 在“数据中心”下新增“月度库存数据表”菜单，并将全部权限授予 leiyongyu 当前绑定的角色。

SET @inventory_parent_id := (
    SELECT menu_id FROM sys_menu
    WHERE menu_name='数据中心'
      AND menu_type='M'
      AND status='0'
    ORDER BY IF(menu_id=2101, 0, 1), menu_id
    LIMIT 1
);

SET @inventory_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE component='finance/monthlyInventoryReport/index'
       OR perms='finance:monthlyInventoryReport:list'
    ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '月度库存数据表',@inventory_parent_id,5,'monthly-inventory-report',
    'finance/monthlyInventoryReport/index',NULL,'MonthlyInventoryReport',
    1,0,'C','0','0','finance:monthlyInventoryReport:list','chart',
    'SYSTEM',NOW(),'展示本地仓、海外仓和FBA仓月度库存汇总及清洗明细'
WHERE @inventory_parent_id IS NOT NULL
  AND @inventory_menu_id IS NULL;

SET @inventory_menu_id := COALESCE(
    @inventory_menu_id,
    (
        SELECT menu_id FROM sys_menu
        WHERE component='finance/monthlyInventoryReport/index'
        ORDER BY menu_id DESC LIMIT 1
    )
);

UPDATE sys_menu
SET menu_name='月度库存数据表',
    parent_id=@inventory_parent_id,
    order_num=5,
    path='monthly-inventory-report',
    component='finance/monthlyInventoryReport/index',
    route_name='MonthlyInventoryReport',
    is_frame=1,
    is_cache=0,
    menu_type='C',
    visible='0',
    status='0',
    perms='finance:monthlyInventoryReport:list',
    icon='chart',
    update_by='SYSTEM',
    update_time=NOW(),
    remark='展示本地仓、海外仓和FBA仓月度库存汇总及清洗明细'
WHERE menu_id=@inventory_menu_id;

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '月度库存查询',@inventory_menu_id,1,'',NULL,NULL,NULL,
    1,0,'F','0','0','finance:monthlyInventoryReport:list','#',
    'SYSTEM',NOW(),'查询月度库存汇总与清洗明细'
WHERE @inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@inventory_menu_id
        AND perms='finance:monthlyInventoryReport:list'
  );

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '月度库存重新清洗',@inventory_menu_id,2,'',NULL,NULL,NULL,
    1,0,'F','0','0','finance:monthlyInventoryReport:edit','#',
    'SYSTEM',NOW(),'使用现有ODS数据重新生成DWD和DWS报表'
WHERE @inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@inventory_menu_id
        AND perms='finance:monthlyInventoryReport:edit'
  );

-- leiyongyu 登录后需要先进入“数据中心”，因此同时补齐父菜单权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@inventory_parent_id
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
WHERE user_info.user_name='leiyongyu'
  AND user_info.del_flag='0'
  AND user_info.status='0'
  AND role_info.status='0'
  AND @inventory_parent_id IS NOT NULL;

-- 授予页面菜单权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@inventory_menu_id
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
WHERE user_info.user_name='leiyongyu'
  AND user_info.del_flag='0'
  AND user_info.status='0'
  AND role_info.status='0'
  AND @inventory_menu_id IS NOT NULL;

-- 授予该页面下的查询、重新清洗全部按钮权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,button.menu_id
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
JOIN sys_menu button ON button.parent_id=@inventory_menu_id
WHERE user_info.user_name='leiyongyu'
  AND user_info.del_flag='0'
  AND user_info.status='0'
  AND role_info.status='0'
  AND button.perms IN (
      'finance:monthlyInventoryReport:list',
      'finance:monthlyInventoryReport:edit'
  );

SELECT menu_id,menu_name,parent_id,order_num,path,component,perms,menu_type,status
FROM sys_menu
WHERE menu_id=@inventory_menu_id OR parent_id=@inventory_menu_id
ORDER BY menu_type,order_num,menu_id;

SELECT user_info.user_name,role_info.role_id,role_info.role_name,
       menu_info.menu_id,menu_info.menu_name,menu_info.perms
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=role_info.role_id
JOIN sys_menu menu_info ON menu_info.menu_id=rm.menu_id
WHERE user_info.user_name='leiyongyu'
  AND (menu_info.menu_id=@inventory_parent_id
       OR menu_info.menu_id=@inventory_menu_id
       OR menu_info.parent_id=@inventory_menu_id)
ORDER BY role_info.role_id,menu_info.menu_type,menu_info.order_num,menu_info.menu_id;
