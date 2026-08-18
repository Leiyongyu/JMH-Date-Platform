-- 目标库：Date-Project Python业务库。
-- 功能：增加次月月初库存快照字段，并注册每月2日23:00自动回填任务。

SET @ddl_opening_inventory := IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'dws_inventory_report_department_summary'
          AND column_name = 'next_month_opening_inventory_qty'
    ),
    'SELECT 1',
    'ALTER TABLE `dws_inventory_report_department_summary` ADD COLUMN `next_month_opening_inventory_qty` DECIMAL(24,6) NULL DEFAULT NULL COMMENT ''次月月初库存数量，取本月海外仓与FBA仓期末库存数量之和'' AFTER `fba_end_in_transit_total_cost`'
);
PREPARE stmt_opening_inventory FROM @ddl_opening_inventory;
EXECUTE stmt_opening_inventory;
DEALLOCATE PREPARE stmt_opening_inventory;

INSERT INTO `scheduler_task` (
    task_code, task_name, cron_expression, enabled, description
) VALUES (
    'monthly_inventory_report_opening_inventory_fill',
    '月度库存次月月初库存填充',
    '0 0 23 2 * ?',
    1,
    '每月2日23:00将上月海外仓与FBA仓期末库存数量之和回填为次月月初库存数量'
)
ON DUPLICATE KEY UPDATE
    task_name = VALUES(task_name),
    cron_expression = VALUES(cron_expression),
    description = VALUES(description);

SELECT column_name,column_type,is_nullable,column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'dws_inventory_report_department_summary'
  AND column_name = 'next_month_opening_inventory_qty';

SELECT task_code,task_name,cron_expression,enabled,description
FROM scheduler_task
WHERE task_code = 'monthly_inventory_report_opening_inventory_fill';
