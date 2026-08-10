-- 仅用于测试阶段重建 AMZ-SOP 结构化表。
-- 警告：会清空以下7张AMZ-SOP表；不会操作其他表。
-- 执行后重启 Python，backend/database.py 会按新版结构重建并初始化分类规则。

DROP TABLE IF EXISTS dws_amz_sop_after_sales_summary;
DROP TABLE IF EXISTS dwd_amz_sop_after_sales;
DROP TABLE IF EXISTS dim_amz_sop_classification_cache;
DROP TABLE IF EXISTS dim_amz_sop_after_sales_category;
DROP TABLE IF EXISTS ods_amz_sop_after_sales;
DROP TABLE IF EXISTS dwd_amz_sop_sales_daily;
DROP TABLE IF EXISTS ods_amz_sop_sales_daily;
