-- =====================================================================
-- 应用数据库账号拆分（替代 root 连库）
--
-- 由 DBA 在部署机 MySQL 上手动执行一次。执行前把三个 <...> 占位符替换成
-- 新生成的强密码，密码只写进部署机的环境变量 / .env，不要提交到仓库。
--
--   erp_app   Java 服务：jmh_data_platform 读写，无 DDL
--   py_app    Python 服务：Date-Project 读写；jmh_data_platform 只读，
--             外加 Python 自己维护的 6 张规则/配置表的写权限
--   migrator  仅执行 python -m backend.cli db-migrate / db-baseline 时使用，持有 DDL
--
-- 切换步骤见 Date-Project/deploy/db/README.md。
-- =====================================================================

CREATE USER IF NOT EXISTS 'erp_app'@'localhost' IDENTIFIED BY '<ERP_APP_PASSWORD>';
CREATE USER IF NOT EXISTS 'erp_app'@'127.0.0.1' IDENTIFIED BY '<ERP_APP_PASSWORD>';
CREATE USER IF NOT EXISTS 'py_app'@'localhost' IDENTIFIED BY '<PY_APP_PASSWORD>';
CREATE USER IF NOT EXISTS 'py_app'@'127.0.0.1' IDENTIFIED BY '<PY_APP_PASSWORD>';
CREATE USER IF NOT EXISTS 'migrator'@'localhost' IDENTIFIED BY '<MIGRATOR_PASSWORD>';
CREATE USER IF NOT EXISTS 'migrator'@'127.0.0.1' IDENTIFIED BY '<MIGRATOR_PASSWORD>';

-- ---------------------------------------------------------------------
-- erp_app：Java 核心服务
-- ---------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE TEMPORARY TABLES, LOCK TABLES, EXECUTE
    ON `jmh_data_platform`.* TO 'erp_app'@'localhost', 'erp_app'@'127.0.0.1';
-- 若依「清空日志」使用 TRUNCATE，需要这三张表的 DROP 权限
GRANT DROP ON `jmh_data_platform`.`sys_job_log`    TO 'erp_app'@'localhost', 'erp_app'@'127.0.0.1';
GRANT DROP ON `jmh_data_platform`.`sys_logininfor` TO 'erp_app'@'localhost', 'erp_app'@'127.0.0.1';
GRANT DROP ON `jmh_data_platform`.`sys_oper_log`   TO 'erp_app'@'localhost', 'erp_app'@'127.0.0.1';

-- ---------------------------------------------------------------------
-- py_app：Python 数据服务
-- ---------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE TEMPORARY TABLES, LOCK TABLES, EXECUTE
    ON `Date-Project`.* TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
-- ERP 库默认只读（店铺、商品、Listing、库存等共享基础数据）
GRANT SELECT ON `jmh_data_platform`.* TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
-- Python 自己维护、但建在 ERP 库里的表：eBay 补货 2.0 规则/复核/销售类型，以及报关插件商品表。
-- Java 不读写这些表。按 move_ebay_replenishment_rules.sql 迁到 Date-Project 后，前 5 条可 REVOKE。
GRANT INSERT, UPDATE, DELETE ON `jmh_data_platform`.`ebay_replenishment_v2_formula`       TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
GRANT INSERT, UPDATE, DELETE ON `jmh_data_platform`.`ebay_replenishment_v2_level_rule`    TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
GRANT INSERT, UPDATE, DELETE ON `jmh_data_platform`.`ebay_replenishment_v2_forecast_rule` TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
GRANT INSERT, UPDATE, DELETE ON `jmh_data_platform`.`ebay_replenishment_v2_sales_type`    TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
GRANT INSERT, UPDATE, DELETE ON `jmh_data_platform`.`ebay_replenishment_v2_review`        TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
GRANT INSERT, UPDATE, DELETE ON `jmh_data_platform`.`products`                            TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
-- AI 助手专用库（会话、消息、运行记录、调用日志、记忆）
GRANT SELECT, INSERT, UPDATE, DELETE ON `jmh_ai_agent`.* TO 'py_app'@'localhost', 'py_app'@'127.0.0.1';
-- 启动时只读检查 ERP 库迁移历史（db-status），无需写权限，已被上面的 SELECT 覆盖

-- ---------------------------------------------------------------------
-- migrator：结构变更专用
-- ---------------------------------------------------------------------
GRANT ALL PRIVILEGES ON `jmh_data_platform`.* TO 'migrator'@'localhost', 'migrator'@'127.0.0.1';
GRANT ALL PRIVILEGES ON `Date-Project`.*      TO 'migrator'@'localhost', 'migrator'@'127.0.0.1';
GRANT ALL PRIVILEGES ON `jmh_ai_agent`.*      TO 'migrator'@'localhost', 'migrator'@'127.0.0.1';

FLUSH PRIVILEGES;

-- 验证：
-- SHOW GRANTS FOR 'erp_app'@'localhost';
-- SHOW GRANTS FOR 'py_app'@'localhost';
-- SHOW GRANTS FOR 'migrator'@'localhost';
