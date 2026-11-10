-- 目标库：date-project（Python）。
-- 功能：在 scheduler_task 登记价格分析这一批新增的两个 Python 任务，和其他任务保持一致，
--       使它们出现在任务清单里、可以在那里启停。
--       注意：执行入口只校验代码里的 TASK_SPECS，不看这张表，所以这一步不影响任务能否运行。
-- 计时：两个任务都不由 Python 自己计时，由 Java 每周任务
--       pythonEbayStoreListingSyncTask.runWeekly()（每周一 04:30）依次触发：
--       拉 eBay listing → goodcang_product_inventory_sync → ebay_price_analysis_refresh。
--       cron_expression 只是登记用，Quartz 是唯一计时器。
-- 幂等：ON DUPLICATE KEY UPDATE，可重复执行；不改已有任务。
-- 本脚本是库写操作，须用户逐条审批后执行。

USE `date-project`;
SET NAMES utf8mb4;

START TRANSACTION;
INSERT INTO scheduler_task (task_code, task_name, cron_expression, enabled, description)
VALUES ('goodcang_product_inventory_sync', '谷仓区域仓库存同步', '0 30 4 ? * MON', 1,
 '每周一04:30由Java每周任务在拉完eBay listing后触发；分页拉谷仓get_product_inventory全量，V1校验，空快照判失败，单事务整表替换ods_goodcang_product_inventory_latest。Quartz为唯一计时器。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name), cron_expression=VALUES(cron_expression),
 description=VALUES(description);

INSERT INTO scheduler_task (task_code, task_name, cron_expression, enabled, description)
VALUES ('ebay_price_analysis_refresh', 'eBay价格分析刷表', '0 30 4 ? * MON', 1,
 '每周一04:30由Java每周任务在谷仓同步之后触发；读最新在售刊登与谷仓/领星库存，算状态后整表事务替换dws_ebay_price_analysis；谷仓表不存在或为空时拒绝刷表，看板保持上一次结果。Quartz为唯一计时器。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name), cron_expression=VALUES(cron_expression),
 description=VALUES(description);
COMMIT;

-- 校验：应返回 2 行，enabled=1。
SELECT task_code, task_name, cron_expression, enabled
FROM scheduler_task
WHERE task_code IN ('goodcang_product_inventory_sync', 'ebay_price_analysis_refresh')
ORDER BY task_code;
