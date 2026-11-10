-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：「eBay在售刊登与价格分析每日同步」改为每周同步，并在拉完 listing 之后、刷表之前加拉谷仓库存：
--       invoke_target 由 pythonEbayStoreListingSyncTask.runDaily() 改为 runWeekly()，
--       cron 改为每周一 04:30（0 30 4 ? * MON），job_name / remark 同步改。
-- 依赖：20261110_ebay_price_analysis_menu.sql（建出 runDaily() 那条任务）；
--       需部署包含 PythonEbayStoreListingSyncTask.runWeekly() 的新版 Java，以及 Python 侧
--       goodcang_product_inventory_sync 任务。Java 新版里 runDaily() 已不存在，请与新版 Java 同批上线，
--       执行后重启 Java（或在定时任务页面暂停再启用该任务）使 Quartz 重新加载。
-- 幂等：按 invoke_target 定位，不写死 job_id。已改过（只剩 runWeekly()）时更新 0 行；
--       不改任务启用/暂停状态，不动「单独拉取（排查用）」任务和其他任何任务。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

UPDATE sys_job
SET invoke_target='pythonEbayStoreListingSyncTask.runWeekly()',
    job_name='eBay在售刊登、谷仓库存与价格分析每周同步',
    cron_expression='0 30 4 ? * MON',
    update_by='SYSTEM',
    update_time=NOW(),
    remark='每周一北京时间04:30；依次拉 eBay listing（覆盖 ods_ebay_store_listing_latest）、谷仓区域仓库存（覆盖 ods_goodcang_product_inventory_latest）、刷价格分析DWS。listing 失败整任务失败；谷仓失败单独告警、继续用上一份谷仓快照刷表；刷表遇锁冲突重试一次。服务器时区须为Asia/Shanghai。'
WHERE invoke_target='pythonEbayStoreListingSyncTask.runDaily()'
  AND NOT EXISTS (
      SELECT 1 FROM (
          SELECT job_id FROM sys_job
          WHERE invoke_target='pythonEbayStoreListingSyncTask.runWeekly()'
      ) weekly
  );

-- 校验：应返回 1 行 runWeekly()（cron 0 30 4 ? * MON），且不再有 runDaily()。
SELECT job_id,job_name,invoke_target,cron_expression,status
FROM sys_job
WHERE invoke_target IN (
  'pythonEbayStoreListingSyncTask.runDaily()',
  'pythonEbayStoreListingSyncTask.runWeekly()'
)
ORDER BY job_id;
