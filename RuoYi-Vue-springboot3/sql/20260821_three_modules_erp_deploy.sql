-- 脚本菜单、月度库存数据表、售后数据：ERP库统一部署入口
-- 目标库：jmh_data_platform
-- 执行方式：必须在项目根目录使用 mysql 客户端执行本文件，因为使用了相对路径 SOURCE。
-- 安全性：不清空业务表；只创建/更新菜单、权限、源数据表和Quartz任务。

SET NAMES utf8mb4;
USE `jmh_data_platform`;

-- 一、售后数据菜单、AMZ周任务及 eBay 上传权限。
SOURCE RuoYi-Vue-springboot3/sql/20260807_amz_sop_after_sales_menu_job.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260811_ebay_sop_after_sales_import_permission.sql;

-- 二、脚本菜单迁移为Python统一工作台，并只保留图片SOP组件。
SOURCE RuoYi-Vue-springboot3/sql/20260817_move_image_sop_to_script_tools.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260819_python_script_workbench_menu.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260820_image_sop_security_hardening.sql;

-- 三、月度库存菜单与Quartz调度链路。
SOURCE RuoYi-Vue-springboot3/sql/20260817_monthly_inventory_report_menu.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260814_monthly_inventory_report_source_job.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260818_monthly_inventory_sales_volume_job.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260818_monthly_inventory_opening_inventory_job.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260818_goodcang_inventory_age_lingxing_product_procurement.sql;
SOURCE RuoYi-Vue-springboot3/sql/20260818_amz_ebay_inventory_age_chain.sql;

-- 四、删除已废弃的“导入上月库存成本”菜单权限（不删业务数据表）。
SOURCE RuoYi-Vue-springboot3/sql/20260820_remove_clearance_cost_import.sql;

-- 五、以当前最终业务口径覆盖旧SQL中的时间和说明。
-- 实际达成及销量：每月11日23:00拉取上一个完整自然月。
UPDATE `sys_job`
SET `job_name`='月度库存实际达成及销量填充',
    `job_group`='DATA_CENTER',
    `invoke_target`='pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()',
    `cron_expression`='0 0 23 11 * ?',
    `misfire_policy`='2',
    `concurrent`='1',
    `status`='0',
    `update_by`='SYSTEM',
    `update_time`=NOW(),
    `remark`='每月11日23:00拉取上一个完整自然月Amazon订单利润amount和volume，覆盖Python ODS并重建实际达成及销量DWD；eBay销量按payment_time汇总'
WHERE `invoke_target` IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume',
    'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()'
);

-- AMZ售后：每周刷新当月；进入新月后首次任务强制重拉上一个完整自然月。
UPDATE `sys_job`
SET `job_name`='AMZ-SOP售后链路',
    `job_group`='SOP',
    `invoke_target`='amzSopAfterSalesTask.runWeekly()',
    `cron_expression`='0 30 22 ? * SUN',
    `misfire_policy`='2',
    `concurrent`='1',
    `status`='0',
    `update_by`='SYSTEM',
    `update_time`=NOW(),
    `remark`='每周日22:30刷新当前自然月；进入新月份后的第一次任务强制重拉上一个完整自然月；随后重建可按月区间实时计算的售后汇总'
WHERE `invoke_target` IN (
    'amzSopAfterSalesTask.runWeekly',
    'amzSopAfterSalesTask.runWeekly()'
) OR `job_name`='AMZ-SOP售后链路';

-- 六、最终验证。
SELECT `menu_id`,`parent_id`,`menu_name`,`menu_type`,`path`,`component`,`perms`,`status`,`visible`
FROM `sys_menu`
WHERE `perms` IN (
    'sop:scriptTools:view','sop:imageSop:use',
    'finance:monthlyInventoryReport:list','finance:monthlyInventoryReport:edit',
    'sop:afterSales:list','sop:afterSales:sync',
    'sop:afterSales:export','sop:afterSales:import'
)
ORDER BY `parent_id`,`order_num`,`menu_id`;

SELECT `job_id`,`job_name`,`job_group`,`invoke_target`,`cron_expression`,
       `misfire_policy`,`concurrent`,`status`,`remark`
FROM `sys_job`
WHERE `invoke_target` IN (
    'amzSopAfterSalesTask.runWeekly()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()',
    'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory()',
    'pythonFbaInventoryTask.syncCurrentMonth()'
)
ORDER BY `job_id`;

SELECT u.`user_name`,r.`role_id`,r.`role_name`,m.`menu_name`,m.`perms`
FROM `sys_user` u
JOIN `sys_user_role` ur ON ur.`user_id`=u.`user_id`
JOIN `sys_role` r ON r.`role_id`=ur.`role_id`
JOIN `sys_role_menu` rm ON rm.`role_id`=r.`role_id`
JOIN `sys_menu` m ON m.`menu_id`=rm.`menu_id`
WHERE u.`user_name`='leiyongyu'
  AND m.`perms` IN (
      'sop:scriptTools:view','sop:imageSop:use',
      'finance:monthlyInventoryReport:list','finance:monthlyInventoryReport:edit',
      'sop:afterSales:list','sop:afterSales:sync',
      'sop:afterSales:export','sop:afterSales:import'
  )
ORDER BY r.`role_id`,m.`perms`;
