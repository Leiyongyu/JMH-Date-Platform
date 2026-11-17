-- Target DB: date-project (Python). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- Finance center "project profit statement": the monthly group statement (ebay / EU / US1 / US2 / US3) and the
-- AMZ store (legal entity) statement. AMZ figures are computed on read from ods_lingxing_profit_report_msku_month;
-- this migration only stores what is not in the system:
--   fin_project_profit_item         one value per month / group / item: the eBay column read from the uploaded
--                                   finance eBay profit workbook, and the hand entered items of every group
--                                   (labour, allocations, rent, removal, transit credit ...). Edits overwrite.
--   fin_project_profit_ebay_upload  the last eBay workbook uploaded for each month (file name, who, check figures).
-- Only creates the two tables; idempotent, changes nothing else.
USE `date-project`;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fin_project_profit_item` (
  `stat_month` CHAR(7) NOT NULL COMMENT 'YYYY-MM',
  `group_code` VARCHAR(8) NOT NULL COMMENT 'EBAY / EU / US1 / US2 / US3',
  `item_code` VARCHAR(40) NOT NULL COMMENT 'statement item, see project_profit_service.ITEMS',
  `amount` DECIMAL(18,6) NOT NULL COMMENT 'CNY as shown on the statement (costs negative); counts and rates as is',
  `source` VARCHAR(8) NOT NULL DEFAULT 'MANUAL' COMMENT 'UPLOAD = read from the eBay workbook, MANUAL = typed in',
  `updated_by` VARCHAR(64) NULL,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`stat_month`, `group_code`, `item_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Project profit statement: eBay column and hand entered items';

CREATE TABLE IF NOT EXISTS `fin_project_profit_ebay_upload` (
  `stat_month` CHAR(7) NOT NULL,
  `file_name` VARCHAR(255) NOT NULL,
  `uploaded_by` VARCHAR(64) NULL,
  `uploaded_at` DATETIME NOT NULL,
  `check_json` JSON NULL COMMENT 'figures read from the workbook for checking (income, gross profit, order rows ...)',
  PRIMARY KEY (`stat_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Project profit statement: last eBay profit workbook uploaded per month';
