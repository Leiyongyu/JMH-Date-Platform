-- 售后原因分类字典。原属已下线的「售后数据」页面（20260807_amz_sop_after_sales.sql），
-- 现仅供 eBay SKU 分析使用，单独保留建表与初始数据。全部语句幂等。

CREATE TABLE IF NOT EXISTS dim_amz_sop_after_sales_category (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    big_category VARCHAR(50) NOT NULL COMMENT '售后原因大类',
    small_category VARCHAR(100) NOT NULL COMMENT '售后原因小类',
    responsible_party VARCHAR(100) NULL COMMENT '责任部门或责任方',
    classification_description TEXT NULL COMMENT '分类判定说明',
    priority INT NOT NULL DEFAULT 100 COMMENT '规则匹配优先级，数值越小越优先',
    rule_version VARCHAR(32) NOT NULL DEFAULT '2026-08-07' COMMENT '分类规则版本',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用：1启用，0停用',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_amz_sop_category (big_category,small_category),
    KEY idx_amz_sop_category_enabled (enabled,priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DIM-AMZ SOP售后分类规则';

INSERT IGNORE INTO dim_amz_sop_after_sales_category
    (big_category,small_category,responsible_party,classification_description,priority)
VALUES
('产品质量问题','产品质量差','采购部','产品质量差、做工差、与合理质量预期不符。',10),
('产品质量问题','产品无法使用','采购部','产品存在功能故障或无法正常使用。',20),
('国内物流部','组套产品漏发','国内物流部','组合或套装商品缺件、漏发其中一个产品。',30),
('供应商加强包装','到货破损','国内物流部&采购部','运输或包装防护不足导致到货破损。',40),
('国内物流部','产品缺少配件','国内物流部','主商品到达但包装内配件缺失。',50),
('不适配','产品不适配','开发部','尺寸、型号、车型、接口等不匹配。',60),
('不适配','listing货描不符','开发部','实物与Listing标题、图片或描述不一致。',70),
('其他','我方取消订单','运营部','由我方主动取消订单。',80),
('补偿','补差价','运营部','价格差、运费差等差额补偿。',90),
('补偿','返折扣优惠','运营部','通过退款或返现提供折扣优惠。',100),
('其他','其他','运营部','无法从现有信息可靠判断的情况。',110),
('补偿','客户不满意补偿','运营部','为处理客户不满而给予部分补偿。',120),
('退货已损坏','退货未上架','海外仓','退回商品损坏或不可售，未重新上架。',130),
('海外仓问题','海外仓发错货','海外仓','海外仓错发SKU、数量或包裹。',140),
('物流商问题','物流异常退回','海外物流商','运输异常导致包裹退回。',150),
('物流商问题','物流断更','海外物流商','物流轨迹长时间无更新。',160),
('物流商问题','物流延迟补偿','返折扣优惠','物流延误产生的补偿。',170),
('客户自身原因','客户主观退换货','客户自身','不喜欢、不需要、改变主意等主观原因。',180),
('客户自身原因','客户主动取消订单','客户自身','客户主动取消订单。',190),
('客户自身原因','客户拒收包裹','客户自身','客户拒收或未领取包裹。',200);
