-- ERP 库：为月度库存数据表增加三个独立查看权限。
-- 首次执行时，已有页面查询权限的角色默认获得全部三个维度；之后可在角色管理中收紧。
-- 可重复执行。先确认在 ERP 数据库执行；末尾应查出恰好三个权限菜单。
-- 执行后让相关用户重新登录以刷新权限缓存。

START TRANSACTION;

SET @monthly_inventory_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE component = 'finance/monthlyInventoryReport/index'
      AND menu_type = 'C'
    ORDER BY menu_id LIMIT 1
);

-- 全部三个权限菜单已存在时不再次自动授权，避免覆盖管理员后续的收紧配置。
SET @initialize_monthly_inventory_grants := (
    SELECT COUNT(*) < 3 FROM sys_menu
    WHERE parent_id=@monthly_inventory_menu_id
      AND perms IN (
          'finance:monthlyInventoryReport:viewGroup',
          'finance:monthlyInventoryReport:viewStore',
          'finance:monthlyInventoryReport:viewOwner'
      )
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT '查看组别维度',@monthly_inventory_menu_id,3,'',NULL,NULL,NULL,
       1,0,'F','0','0','finance:monthlyInventoryReport:viewGroup','#',
       'SYSTEM',NOW(),'查看和导出月度库存组别维度'
WHERE @monthly_inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@monthly_inventory_menu_id
        AND perms='finance:monthlyInventoryReport:viewGroup'
  );

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT '查看店铺维度',@monthly_inventory_menu_id,4,'',NULL,NULL,NULL,
       1,0,'F','0','0','finance:monthlyInventoryReport:viewStore','#',
       'SYSTEM',NOW(),'查看和导出月度库存店铺维度'
WHERE @monthly_inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@monthly_inventory_menu_id
        AND perms='finance:monthlyInventoryReport:viewStore'
  );

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT '查看个人维度',@monthly_inventory_menu_id,5,'',NULL,NULL,NULL,
       1,0,'F','0','0','finance:monthlyInventoryReport:viewOwner','#',
       'SYSTEM',NOW(),'查看和导出月度库存个人维度'
WHERE @monthly_inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@monthly_inventory_menu_id
        AND perms='finance:monthlyInventoryReport:viewOwner'
  );

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT existing_role.role_id, dimension_menu.menu_id
FROM sys_role_menu existing_role
JOIN sys_menu existing_menu ON existing_menu.menu_id=existing_role.menu_id
JOIN sys_menu dimension_menu ON dimension_menu.parent_id=@monthly_inventory_menu_id
WHERE existing_menu.perms='finance:monthlyInventoryReport:list'
  AND existing_menu.menu_type IN ('C','F')
  AND @initialize_monthly_inventory_grants=1
  AND dimension_menu.perms IN (
      'finance:monthlyInventoryReport:viewGroup',
      'finance:monthlyInventoryReport:viewStore',
      'finance:monthlyInventoryReport:viewOwner'
  );

COMMIT;

SELECT @monthly_inventory_menu_id AS monthly_inventory_page_menu_id;

SELECT menu_id,menu_name,perms,status
FROM sys_menu
WHERE parent_id=@monthly_inventory_menu_id
  AND perms IN (
      'finance:monthlyInventoryReport:viewGroup',
      'finance:monthlyInventoryReport:viewStore',
      'finance:monthlyInventoryReport:viewOwner'
  )
ORDER BY order_num;
