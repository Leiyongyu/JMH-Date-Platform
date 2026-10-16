-- 首页内“商品分析 / 销售看板”按钮切换页面。保留独立路由及授权，不在侧栏重复显示。
USE jmh_data_platform;
START TRANSACTION;
INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,icon,create_by,create_time)
SELECT '销售看板',0,99,'sales-dashboard','M','1','0',1,0,'chart','admin',NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE parent_id=0 AND path IN ('home-sales-dashboard-permissions','sales-dashboard'));
SET @sales_parent = (SELECT menu_id FROM sys_menu WHERE parent_id=0 AND path IN ('home-sales-dashboard-permissions','sales-dashboard') ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET menu_name='销售看板',path='sales-dashboard',menu_type='M',visible='1',status='0',
    update_by='admin',update_time=NOW() WHERE menu_id=@sales_parent;
INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,create_by,create_time)
SELECT '销售看板查看',@sales_parent,1,'#','F','0','0',1,0,'finance:salesDashboard:list','admin',NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='finance:salesDashboard:list');
SET @sales_page = (SELECT menu_id FROM sys_menu WHERE perms='finance:salesDashboard:list' ORDER BY menu_id LIMIT 1);
UPDATE sys_menu SET menu_name='销售看板',parent_id=@sales_parent,path='index',component='finance/salesDashboard/index',
    route_name='SalesDashboard',menu_type='C',visible='1',status='0',is_cache=1,icon='chart',
    update_by='admin',update_time=NOW() WHERE menu_id=@sales_page;
INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,create_by,create_time)
SELECT '销售历史上传',@sales_page,2,'#','F','0','0',1,0,'finance:salesDashboard:import','admin',NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='finance:salesDashboard:import');
UPDATE sys_menu SET parent_id=@sales_page,update_by='admin',update_time=NOW() WHERE perms='finance:salesDashboard:import';
-- 保留旧版本已获查看权限角色的路由祖先授权。
INSERT INTO sys_role_menu (role_id,menu_id)
SELECT rm.role_id,@sales_parent FROM sys_role_menu rm WHERE rm.menu_id=@sales_page
  AND NOT EXISTS (SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=rm.role_id AND existing.menu_id=@sales_parent);
-- 默认仅系统管理员角色获得这两个新权限；其他角色由管理员勾选。
INSERT INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,m.menu_id FROM sys_role r CROSS JOIN sys_menu m
WHERE r.role_key='admin' AND r.status='0' AND r.del_flag='0'
  AND (m.menu_id=@sales_parent OR m.perms IN ('finance:salesDashboard:list','finance:salesDashboard:import'))
  AND NOT EXISTS (SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=r.role_id AND rm.menu_id=m.menu_id);
COMMIT;
