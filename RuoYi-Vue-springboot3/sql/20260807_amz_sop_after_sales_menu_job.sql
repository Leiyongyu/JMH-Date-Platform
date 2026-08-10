-- AMZ-SOP售后数据页面、按钮权限及每周链路任务。
-- 在 jmh_data_platform 库执行；可重复执行，不删除业务数据。

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = 0 AND menu_type = 'M'
    AND (path = 'sop' OR menu_name = 'SOP')
  ORDER BY CASE WHEN path = 'sop' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT
  'SOP',0,5,'sop',NULL,NULL,'Sop',
  1,0,'M','0','0',NULL,'guide',
  'SYSTEM',NOW(),'标准作业流程与业务数据处理'
WHERE @sop_menu_id IS NULL;

SET @sop_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = 0 AND menu_type = 'M'
    AND (path = 'sop' OR menu_name = 'SOP')
  ORDER BY CASE WHEN path = 'sop' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

UPDATE sys_menu
SET menu_name='SOP',path='sop',route_name='Sop',visible='0',status='0',
    icon='guide',update_by='SYSTEM',update_time=NOW(),
    remark='标准作业流程与业务数据处理'
WHERE menu_id=@sop_menu_id;

SET @after_sales_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id
    AND (path='after-sales' OR component='sop/afterSales/index')
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT
  '售后数据',@sop_menu_id,1,'after-sales','sop/afterSales/index',NULL,'SopAfterSales',
  1,0,'C','0','0','sop:afterSales:list','data-analysis',
  'SYSTEM',NOW(),'AMZ订单利润与售后订单清洗、分类及售后率汇总'
WHERE @sop_menu_id IS NOT NULL AND @after_sales_menu_id IS NULL;

SET @after_sales_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id=@sop_menu_id
    AND (path='after-sales' OR component='sop/afterSales/index')
  ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name='售后数据',order_num=1,path='after-sales',
    component='sop/afterSales/index',route_name='SopAfterSales',
    menu_type='C',visible='0',status='0',perms='sop:afterSales:list',
    icon='data-analysis',update_by='SYSTEM',update_time=NOW(),
    remark='AMZ订单利润与售后订单清洗、分类及售后率汇总'
WHERE menu_id=@after_sales_menu_id;

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '查询售后数据',@after_sales_menu_id,1,'',NULL,NULL,'',
       1,0,'F','0','0','sop:afterSales:list','#','SYSTEM',NOW(),''
WHERE @after_sales_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:afterSales:list' AND menu_type='F');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '执行AMZ售后链路',@after_sales_menu_id,2,'',NULL,NULL,'',
       1,0,'F','0','0','sop:afterSales:sync','#','SYSTEM',NOW(),''
WHERE @after_sales_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:afterSales:sync');

INSERT INTO sys_menu (
  menu_name,parent_id,order_num,path,component,query,route_name,
  is_frame,is_cache,menu_type,visible,status,perms,icon,
  create_by,create_time,remark
)
SELECT '导出AMZ售后表',@after_sales_menu_id,3,'',NULL,NULL,'',
       1,0,'F','0','0','sop:afterSales:export','#','SYSTEM',NOW(),''
WHERE @after_sales_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='sop:afterSales:export');

SET @after_sales_sync_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:afterSales:sync' ORDER BY menu_id LIMIT 1
);
SET @after_sales_export_id := (
  SELECT menu_id FROM sys_menu WHERE perms='sop:afterSales:export' ORDER BY menu_id LIMIT 1
);

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT r.role_id,m.menu_id
FROM sys_role r
JOIN (
  SELECT @sop_menu_id AS menu_id
  UNION ALL SELECT @after_sales_menu_id
  UNION ALL SELECT @after_sales_sync_id
  UNION ALL SELECT @after_sales_export_id
) m ON m.menu_id IS NOT NULL
WHERE r.role_key='admin' AND r.status='0';

INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id=u.user_id
JOIN (
  SELECT @sop_menu_id AS menu_id
  UNION ALL SELECT @after_sales_menu_id
  UNION ALL SELECT @after_sales_sync_id
  UNION ALL SELECT @after_sales_export_id
) m ON m.menu_id IS NOT NULL
WHERE u.user_name='leiyongyu';

UPDATE sys_job
SET job_name='AMZ-SOP售后链路',job_group='SOP',
    invoke_target='amzSopAfterSalesTask.runWeekly()',
    cron_expression='0 30 22 ? * SUN',misfire_policy='2',concurrent='1',status='0',
    update_by='SYSTEM',update_time=NOW(),
    remark='每周日22:30执行；源表为空拉取当前自然年，否则增量刷新最近7天；去重后完成清洗分类和售后率汇总；错过后补跑；禁止并发'
WHERE invoke_target IN (
  'amzSopAfterSalesTask.runWeekly','amzSopAfterSalesTask.runWeekly()'
) OR job_name='AMZ-SOP售后链路';

INSERT INTO sys_job (
  job_name,job_group,invoke_target,cron_expression,
  misfire_policy,concurrent,status,create_by,create_time,remark
)
SELECT
  'AMZ-SOP售后链路','SOP','amzSopAfterSalesTask.runWeekly()',
  '0 30 22 ? * SUN','2','1','0','SYSTEM',NOW(),
  '每周日22:30执行；源表为空拉取当前自然年，否则增量刷新最近7天；去重后完成清洗分类和售后率汇总；错过后补跑；禁止并发'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target IN (
    'amzSopAfterSalesTask.runWeekly','amzSopAfterSalesTask.runWeekly()'
  ) OR job_name='AMZ-SOP售后链路'
);

SELECT menu_id,parent_id,menu_name,path,component,menu_type,perms,status
FROM sys_menu
WHERE menu_id IN (@sop_menu_id,@after_sales_menu_id,@after_sales_sync_id,@after_sales_export_id)
ORDER BY parent_id,order_num;

SELECT job_id,job_name,job_group,invoke_target,cron_expression,
       misfire_policy,concurrent,status,remark
FROM sys_job
WHERE job_name='AMZ-SOP售后链路';
