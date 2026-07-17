-- 清理 export_tax_refund 中当前Python服务未使用的表和字段。
-- 执行前应先完成整库备份。
USE export_tax_refund;

-- 当前代码无引用且均为空的预留/旧表。
DROP TABLE IF EXISTS export_purchase_allocation;
DROP TABLE IF EXISTS declaration_task;
DROP TABLE IF EXISTS sku_unit_conversion;
DROP TABLE IF EXISTS forex_receipt_old;

-- 当前报关Excel解析器已直接保存拆分字段，不再使用三段原始拼接文本。
ALTER TABLE customs_declaration_excel_item
    DROP COLUMN product_description_raw,
    DROP COLUMN quantity_unit_raw,
    DROP COLUMN unit_price_total_currency_raw;

-- 新版Sheet1不再提供“未回款余额”，O列为回款级“差额”。
ALTER TABLE forex_export_receivable
    DROP COLUMN unreceived_balance_usd;

-- 新版Sheet1按核心流水号分组，不保存合并区域和结汇时间。
ALTER TABLE forex_receipt
    DROP INDEX idx_receipt_group,
    DROP COLUMN receipt_group_key,
    DROP COLUMN settlement_time_raw,
    DROP COLUMN merge_anchor,
    ADD COLUMN difference_usd DECIMAL(20,2) NULL
        COMMENT '收汇总额与关联报关单回款金额的差额USD'
        AFTER receipt_date;
