-- 「数据中心 > 售后数据」页面已下线，删除只被该页面使用的 16 张表（不可恢复，执行前确认当日备份已完成）。
--
-- 保留 dim_amz_sop_after_sales_category：eBay SKU 分析页面的退货分类仍在读取它。
-- 逐表核对过引用：以下表只出现在已删除的 amz_sop_* / ebay_sop_* / after_sales_state 模块中，
-- 没有视图、Java 代码或其他 Python 模块引用。

DROP TABLE IF EXISTS ods_amz_sop_after_sales;
DROP TABLE IF EXISTS ods_amz_sop_sales_daily;
DROP TABLE IF EXISTS dwd_amz_sop_after_sales;
DROP TABLE IF EXISTS dwd_amz_sop_sales_daily;
DROP TABLE IF EXISTS dws_amz_sop_after_sales_summary;
DROP TABLE IF EXISTS dim_amz_sop_classification_cache;

DROP TABLE IF EXISTS ods_ebay_sop_order_raw;
DROP TABLE IF EXISTS ods_ebay_sop_sales_history;
DROP TABLE IF EXISTS ods_ebay_sop_after_sales_history;
DROP TABLE IF EXISTS dwd_ebay_sop_after_sales;
DROP TABLE IF EXISTS dwd_ebay_sop_sales_daily;
DROP TABLE IF EXISTS dwd_ebay_sop_sales_monthly;
DROP TABLE IF EXISTS dws_ebay_sop_after_sales_summary;
DROP TABLE IF EXISTS etl_ebay_sop_import_batch;

DROP TABLE IF EXISTS etl_after_sales_month_state;
DROP TABLE IF EXISTS etl_after_sales_range_state;

-- Python 内部调度任务定义；运行记录 scheduler_task_run 作为历史保留
DELETE FROM scheduler_task WHERE task_code = 'amz_sop_after_sales_chain';
