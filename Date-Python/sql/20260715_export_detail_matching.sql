-- 报关资料商品与报关单 PDF 商品匹配所需的增量字段。
USE export_tax_refund;

ALTER TABLE customs_declaration_excel_item
    ADD COLUMN export_invoice_no VARCHAR(100) NULL COMMENT '报关资料商业发票号码'
    AFTER product_sequence_normalized;

ALTER TABLE export_detail
    ADD COLUMN customs_excel_item_id BIGINT NULL COMMENT '匹配的报关资料Excel商品主键'
        AFTER id,
    ADD COLUMN statutory_quantity DECIMAL(20,6) NULL COMMENT '报关资料法定数量'
        AFTER export_quantity,
    ADD COLUMN statutory_unit VARCHAR(50) NULL COMMENT '报关资料法定单位'
        AFTER statutory_quantity,
    ADD COLUMN customs_match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED'
        COMMENT '报关资料匹配状态' AFTER remark,
    ADD COLUMN customs_match_message VARCHAR(1000) NULL COMMENT '匹配差异或异常说明'
        AFTER customs_match_status,
    ADD KEY idx_export_excel_item (customs_excel_item_id);
