-- 将首页销售看板移至独立“财务中心 -> BI看板”。
-- 复用原销售看板菜单ID、查看及上传权限，授权给leiyongyu对应的有效角色；不修改现有“数据中心”(path=finance)。
-- 仅调整菜单数据，可重复执行；无需修改业务表结构。执行后重新登录以刷新路由。
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @sales_finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND menu_type='M'
    AND path IN ('finance-center','sales-dashboard','home-sales-dashboard-permissions')
  ORDER BY CASE WHEN path='finance-center' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,route_name,menu_type,visible,status,is_frame,is_cache,icon,create_by,create_time)
SELECT '财务中心',0,5,'finance-center','FinanceCenter','M','0','0',1,0,'money','SYSTEM',NOW()
WHERE @sales_finance_root IS NULL;
SET @sales_finance_root := COALESCE(@sales_finance_root,(
  SELECT menu_id FROM sys_menu WHERE parent_id=0 AND path='finance-center' AND menu_type='M' ORDER BY menu_id LIMIT 1
));
UPDATE sys_menu SET menu_name='财务中心',path='finance-center',route_name='FinanceCenter',
  component=NULL,visible='0',status='0',icon='money',order_num=5,update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@sales_finance_root;

INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT 'BI看板',@sales_finance_root,1,'bi-dashboard','finance/salesDashboard/index','SalesDashboard','C','0','0',1,1,
  'finance:salesDashboard:list','chart','SYSTEM',NOW()
WHERE NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:salesDashboard:list');
SET @sales_bi_page := (
  SELECT menu_id FROM sys_menu WHERE perms='finance:salesDashboard:list'
  ORDER BY CASE WHEN menu_type='C' THEN 0 ELSE 1 END,menu_id LIMIT 1
);
UPDATE sys_menu SET menu_name='BI看板',parent_id=@sales_finance_root,order_num=1,path='bi-dashboard',
  component='finance/salesDashboard/index',route_name='SalesDashboard',menu_type='C',visible='0',status='0',
  is_frame=1,is_cache=1,icon='chart',update_by='SYSTEM',update_time=NOW()
WHERE menu_id=@sales_bi_page;
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT '销售历史上传',@sales_bi_page,2,'#','F','0','0',1,0,'finance:salesDashboard:import','#','SYSTEM',NOW()
WHERE NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='finance:salesDashboard:import');
UPDATE sys_menu SET parent_id=@sales_bi_page,update_by='SYSTEM',update_time=NOW()
WHERE perms='finance:salesDashboard:import' AND parent_id<>@sales_bi_page;

-- 只补充既有查看权限角色的父目录权限，不扩大销售数据查看或上传权限。
INSERT INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT rm.role_id,@sales_finance_root FROM sys_role_menu rm WHERE rm.menu_id=@sales_bi_page
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=rm.role_id AND existing.menu_id=@sales_finance_root);

-- 按账户关联角色授权，不硬编码角色ID；同角色所有用户均生效。仅补齐本模块三项权限。
INSERT INTO sys_role_menu(role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN sys_role r ON r.role_id=ur.role_id
JOIN sys_menu m ON m.menu_id IN (@sales_finance_root,@sales_bi_page)
                  OR (m.parent_id=@sales_bi_page AND m.perms='finance:salesDashboard:import')
WHERE u.user_name='leiyongyu' AND u.status='0' AND u.del_flag='0'
  AND r.status='0' AND r.del_flag='0' AND m.status='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id);
COMMIT;
