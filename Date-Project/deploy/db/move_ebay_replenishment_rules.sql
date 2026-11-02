-- =====================================================================
-- 把 eBay 补货 2.0 的 5 张 Python 自有表从 ERP 库迁到 Date-Project 库
-- （架构审查第 8 条：Java 不读写这些表，留在 ERP 库导致备份口径、权限和迁移归属分裂）
--
-- 停机窗口内手动执行（复核备注表有用户实时写入）：
--   1. 停止 Python 服务（restart-all 前先停，或在无人使用的时段执行）
--   2. 用 migrator 账号执行本脚本，核对末尾的行数对比，两列必须相等
--   3. Python .env 增加 EBAY_REPLENISHMENT_RULE_DATABASE=Date-Project，启动 Python
--   4. 页面核对补货规则、备注、销售类型均正常后，旧表观察一周再按需删除
--
-- 回滚：删掉 .env 中 EBAY_REPLENISHMENT_RULE_DATABASE 并重启 Python，即回到读写 ERP 库旧表。
-- =====================================================================

CREATE TABLE IF NOT EXISTS `Date-Project`.`ebay_replenishment_v2_formula`       LIKE `jmh_data_platform`.`ebay_replenishment_v2_formula`;
CREATE TABLE IF NOT EXISTS `Date-Project`.`ebay_replenishment_v2_level_rule`    LIKE `jmh_data_platform`.`ebay_replenishment_v2_level_rule`;
CREATE TABLE IF NOT EXISTS `Date-Project`.`ebay_replenishment_v2_forecast_rule` LIKE `jmh_data_platform`.`ebay_replenishment_v2_forecast_rule`;
CREATE TABLE IF NOT EXISTS `Date-Project`.`ebay_replenishment_v2_sales_type`    LIKE `jmh_data_platform`.`ebay_replenishment_v2_sales_type`;
CREATE TABLE IF NOT EXISTS `Date-Project`.`ebay_replenishment_v2_review`        LIKE `jmh_data_platform`.`ebay_replenishment_v2_review`;

-- LIKE 不复制表注释，补回中文注释（项目规范：所有表必须有中文表注释）
ALTER TABLE `Date-Project`.`ebay_replenishment_v2_formula`       COMMENT = 'eBay补货2.0公式配置';
ALTER TABLE `Date-Project`.`ebay_replenishment_v2_level_rule`    COMMENT = 'eBay补货2.0等级规则';
ALTER TABLE `Date-Project`.`ebay_replenishment_v2_forecast_rule` COMMENT = 'eBay补货2.0预估销量规则';
ALTER TABLE `Date-Project`.`ebay_replenishment_v2_sales_type`    COMMENT = 'eBay补货2.0销售类型';
ALTER TABLE `Date-Project`.`ebay_replenishment_v2_review`        COMMENT = 'eBay补货2.0运营/开发复核备注';

START TRANSACTION;
DELETE FROM `Date-Project`.`ebay_replenishment_v2_formula`;
DELETE FROM `Date-Project`.`ebay_replenishment_v2_level_rule`;
DELETE FROM `Date-Project`.`ebay_replenishment_v2_forecast_rule`;
DELETE FROM `Date-Project`.`ebay_replenishment_v2_sales_type`;
DELETE FROM `Date-Project`.`ebay_replenishment_v2_review`;
INSERT INTO `Date-Project`.`ebay_replenishment_v2_formula`       SELECT * FROM `jmh_data_platform`.`ebay_replenishment_v2_formula`;
INSERT INTO `Date-Project`.`ebay_replenishment_v2_level_rule`    SELECT * FROM `jmh_data_platform`.`ebay_replenishment_v2_level_rule`;
INSERT INTO `Date-Project`.`ebay_replenishment_v2_forecast_rule` SELECT * FROM `jmh_data_platform`.`ebay_replenishment_v2_forecast_rule`;
INSERT INTO `Date-Project`.`ebay_replenishment_v2_sales_type`    SELECT * FROM `jmh_data_platform`.`ebay_replenishment_v2_sales_type`;
INSERT INTO `Date-Project`.`ebay_replenishment_v2_review`        SELECT * FROM `jmh_data_platform`.`ebay_replenishment_v2_review`;
COMMIT;

-- 行数核对：source_rows 与 target_rows 必须逐行相等
SELECT 'formula' AS table_name,
       (SELECT COUNT(*) FROM `jmh_data_platform`.`ebay_replenishment_v2_formula`) AS source_rows,
       (SELECT COUNT(*) FROM `Date-Project`.`ebay_replenishment_v2_formula`) AS target_rows
UNION ALL SELECT 'level_rule',
       (SELECT COUNT(*) FROM `jmh_data_platform`.`ebay_replenishment_v2_level_rule`),
       (SELECT COUNT(*) FROM `Date-Project`.`ebay_replenishment_v2_level_rule`)
UNION ALL SELECT 'forecast_rule',
       (SELECT COUNT(*) FROM `jmh_data_platform`.`ebay_replenishment_v2_forecast_rule`),
       (SELECT COUNT(*) FROM `Date-Project`.`ebay_replenishment_v2_forecast_rule`)
UNION ALL SELECT 'sales_type',
       (SELECT COUNT(*) FROM `jmh_data_platform`.`ebay_replenishment_v2_sales_type`),
       (SELECT COUNT(*) FROM `Date-Project`.`ebay_replenishment_v2_sales_type`)
UNION ALL SELECT 'review',
       (SELECT COUNT(*) FROM `jmh_data_platform`.`ebay_replenishment_v2_review`),
       (SELECT COUNT(*) FROM `Date-Project`.`ebay_replenishment_v2_review`);
