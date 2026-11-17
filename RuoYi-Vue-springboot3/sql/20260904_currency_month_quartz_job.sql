-- 目标库：jmh_data_platform（Java ERP / Quartz 数据库）。
-- 用途：把已经存在于 Python scheduler_task 的独立汇率任务注册到
--       RuoYi「系统管理 -> 定时任务」页面。
-- 安全性：不删除业务数据；首次新增时默认暂停，重复执行保留现有启停状态。

SET NAMES utf8mb4;
USE `jmh_data_platform`;

START TRANSACTION;

UPDATE `sys_job`
SET `job_name` = '领星月度汇率同步',
    `job_group` = 'DATA_CENTER',
    `invoke_target` = 'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency()',
    `cron_expression` = '0 0 6 1 * ?',
    `misfire_policy` = '2',
    `concurrent` = '1',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = '独立拉取领星currencyMonth全部币种的当月汇率；默认暂停，可手动执行；月度库存源数据任务仍会链式同步汇率。'
WHERE `invoke_target` IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency()'
);

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `invoke_target`, `cron_expression`,
    `misfire_policy`, `concurrent`, `status`,
    `create_by`, `create_time`, `remark`
)
SELECT
    '领星月度汇率同步',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency()',
    '0 0 6 1 * ?',
    '2', '1', '1',
    'SYSTEM', NOW(),
    '独立拉取领星currencyMonth全部币种的当月汇率；默认暂停，可手动执行；月度库存源数据任务仍会链式同步汇率。'
WHERE NOT EXISTS (
    SELECT 1
    FROM `sys_job`
    WHERE `invoke_target` IN (
        'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency',
        'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency()'
    )
);

COMMIT;

SELECT `job_id`, `job_name`, `job_group`, `invoke_target`,
       `cron_expression`, `status`, `remark`
FROM `sys_job`
WHERE `invoke_target` IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthCurrency()'
);
