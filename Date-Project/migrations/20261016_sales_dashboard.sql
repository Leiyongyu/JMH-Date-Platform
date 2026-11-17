-- 在 Python 应用数据库 date-project 中执行；只新建两张表，不改动现有业务表。
USE `date-project`;

CREATE TABLE IF NOT EXISTS ods_sales_dashboard_ebay_monthly (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  stat_month CHAR(7) NOT NULL COMMENT 'Excel行年月 YYYY-MM，不按文件名',
  group_code VARCHAR(64) NOT NULL COMMENT '原表站点，作为平台内组别',
  platform_income DECIMAL(24,8) NULL COMMENT '平台收入-总(RMB)',
  platform_expense DECIMAL(24,8) NULL COMMENT '平台支出(RMB)-总',
  gross_profit DECIMAL(24,8) NULL COMMENT '毛利(RMB)',
  gross_margin DECIMAL(24,8) NULL COMMENT '毛利率，原始小数',
  net_amount DECIMAL(24,8) NULL COMMENT '净额（人民币），业绩指标',
  gross_sales DECIMAL(24,8) NULL COMMENT '销售总额',
  refund_amount DECIMAL(24,8) NULL COMMENT '退款',
  compensation DECIMAL(24,8) NULL COMMENT '赔偿',
  transaction_fee DECIMAL(24,8) NULL COMMENT '成交费',
  penalty DECIMAL(24,8) NULL COMMENT '罚款',
  advertising_fee DECIMAL(24,8) NULL COMMENT '广告费',
  listing_fee DECIMAL(24,8) NULL COMMENT '刊登/副标题',
  other_fee DECIMAL(24,8) NULL COMMENT '其它费用',
  source_file VARCHAR(255) NOT NULL,
  source_sheet VARCHAR(64) NOT NULL,
  source_row INT NOT NULL,
  source_sha256 CHAR(64) NOT NULL,
  raw_data JSON NOT NULL COMMENT '完整原表列名、值、公式；额外列也保留',
  imported_by VARCHAR(64) NOT NULL,
  imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_month_group (stat_month, group_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='销售看板ebay历史；同平台月份整片事务替换，其他年月保留';

CREATE TABLE IF NOT EXISTS ods_sales_dashboard_amz_monthly (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  stat_month CHAR(7) NOT NULL COMMENT 'Excel行年月 YYYY-MM，不按文件名',
  group_code VARCHAR(64) NOT NULL COMMENT '原表站点，作为平台内组别',
  platform_income DECIMAL(24,8) NULL COMMENT '平台收入-总(RMB)',
  platform_expense DECIMAL(24,8) NULL COMMENT '平台支出(RMB)-总',
  gross_profit DECIMAL(24,8) NULL COMMENT '毛利(RMB)',
  gross_margin DECIMAL(24,8) NULL COMMENT '毛利率，原始小数',
  total_receipts DECIMAL(24,8) NULL COMMENT '总收款（人民币），业绩指标',
  gross_sales DECIMAL(24,8) NULL COMMENT '总销售额（人民币）',
  refund_amount DECIMAL(24,8) NULL COMMENT '退款金额（人民币）',
  commission DECIMAL(24,8) NULL COMMENT '平台佣金（人民币）',
  shipping_fee DECIMAL(24,8) NULL COMMENT '发货费（人民币）',
  advertising_fee DECIMAL(24,8) NULL COMMENT '广告和推广费（人民币）',
  source_file VARCHAR(255) NOT NULL,
  source_sheet VARCHAR(64) NOT NULL,
  source_row INT NOT NULL,
  source_sha256 CHAR(64) NOT NULL,
  raw_data JSON NOT NULL COMMENT '完整原表列名、值、公式；额外列也保留',
  imported_by VARCHAR(64) NOT NULL,
  imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_month_group (stat_month, group_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='销售看板amz历史；同平台月份整片事务替换，其他年月保留';
