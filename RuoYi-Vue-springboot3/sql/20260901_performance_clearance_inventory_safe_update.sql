-- 绩效排名、滞销清货、月度库存数据表：2026-09-01 安全部署补丁。
-- 目标实例同时包含 jmh_data_platform（Java ERP）和 Date-Project（Python）。
-- 安全性：本脚本不包含 DROP、TRUNCATE、DELETE，不修改任何业务数据；
--         只对齐“月度库存实际达成及销量填充”的任务时间和说明。

SET NAMES utf8mb4;
START TRANSACTION;

USE `jmh_data_platform`;

UPDATE `sys_job`
SET `job_name` = '月度库存实际达成及销量填充',
    `job_group` = 'DATA_CENTER',
    `invoke_target` = 'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()',
    `cron_expression` = '0 0 12 1 * ?',
    `misfire_policy` = '2',
    `concurrent` = '1',
    `status` = '0',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = '每月1日12:00拉取上个完整自然月Amazon订单利润amount和volume，按月份覆盖月度库存订单利润ODS并重建实际达成及销量DWD；eBay销量按payment_time汇总'
WHERE `invoke_target` IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume',
    'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()'
);

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `invoke_target`, `cron_expression`,
    `misfire_policy`, `concurrent`, `status`,
    `create_by`, `create_time`, `remark`
)
SELECT
    '月度库存实际达成及销量填充',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()',
    '0 0 12 1 * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每月1日12:00拉取上个完整自然月Amazon订单利润amount和volume，按月份覆盖月度库存订单利润ODS并重建实际达成及销量DWD；eBay销量按payment_time汇总'
WHERE NOT EXISTS (
    SELECT 1
    FROM `sys_job`
    WHERE `invoke_target` IN (
        'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume',
        'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()',
        'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume',
        'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()'
    )
);

USE `Date-Project`;

INSERT INTO `scheduler_task` (
    `task_code`, `task_name`, `cron_expression`, `enabled`, `description`
) VALUES (
    'monthly_inventory_report_sales_volume_sync',
    '月度库存实际达成及销量填充',
    '0 0 12 1 * ?',
    1,
    '每月1日12:00拉取上个完整自然月Amazon订单利润amount和volume，按月份覆盖月度库存订单利润ODS并重建实际达成及销量DWD；eBay销量按payment_time汇总'
)
ON DUPLICATE KEY UPDATE
    `task_name` = VALUES(`task_name`),
    `cron_expression` = VALUES(`cron_expression`),
    `enabled` = VALUES(`enabled`),
    `description` = VALUES(`description`);

COMMIT;

-- 部署后核验：两端任务必须都是每月1日12:00。
USE `jmh_data_platform`;
SELECT `job_id`, `job_name`, `invoke_target`, `cron_expression`, `status`, `remark`
FROM `sys_job`
WHERE `invoke_target` = 'pythonMonthlyInventoryReportTask.syncPreviousMonthSalesVolume()';

USE `Date-Project`;
SELECT `task_code`, `task_name`, `cron_expression`, `enabled`, `description`
FROM `scheduler_task`
WHERE `task_code` = 'monthly_inventory_report_sales_volume_sync';
