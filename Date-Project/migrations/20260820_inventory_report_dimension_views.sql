-- 目标库：Date-Project（Python数据库）。不要在jmh_data_platform执行。
-- 月度库存报表增加店铺与负责人双维度汇总；表结构沿用现有DWS维度汇总表。

ALTER TABLE `dws_inventory_report_dimension_summary`
    MODIFY COLUMN `dimension_type` VARCHAR(16) NOT NULL
        COMMENT '汇总维度：STORE店铺或OWNER负责人',
    MODIFY COLUMN `dimension_value` VARCHAR(255) NOT NULL
        COMMENT '店铺名称或负责人姓名';
