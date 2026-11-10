-- ============================================================
-- 【本脚本含 DROP TABLE，由用户本人执行】
-- ============================================================
-- 功能：彻底清理 eBay 价格分析页面「刷新数据源」按钮的登记链路。
--       该按钮只往 dws_ebay_price_analysis_refresh_request 插一条 PENDING 记录就返回，
--       既不拉 eBay 也不刷表；代码侧已删除 POST /refresh 及权限，这里清掉已入库的部分。
-- 背景：20261110_ebay_price_analysis_menu.sql 与 Date-Project/migrations/20261110_ebay_price_analysis.sql
--       已执行过，改原脚本对已入库的权限和表无效，所以另出本清理脚本。
-- 不动：定时任务 ebay_price_analysis_refresh（刷 DWS）、eBay在售刊登每周同步任务、
--       dws_ebay_price_analysis 数据表、价格分析页面/导出权限，全部保留。
-- 幂等：两段都可重复执行；没有可删的内容时删除 0 行 / 表不存在不报错。
-- 分两段，分别在两个库执行（同一连接内用 USE 切换）。

-- ============================================================
-- 第 1 段：在 jmh_data_platform 库（Java ERP）执行
--          删除按钮权限 operations:ebayPriceAnalysis:refresh 及其角色授权。
--          按 perms 精确定位，不写死 menu_id。
-- ============================================================
USE `jmh_data_platform`;
SET NAMES utf8mb4;

START TRANSACTION;
DELETE rm FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE m.perms='operations:ebayPriceAnalysis:refresh' AND m.menu_type='F';

DELETE FROM sys_menu
WHERE perms='operations:ebayPriceAnalysis:refresh' AND menu_type='F';
COMMIT;

-- 校验：两项都应为 0。
SELECT
  (SELECT COUNT(*) FROM sys_menu WHERE perms='operations:ebayPriceAnalysis:refresh') AS refresh_menu_left,
  (SELECT COUNT(*) FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id=rm.menu_id
    WHERE m.perms='operations:ebayPriceAnalysis:refresh') AS refresh_grant_left;

-- ============================================================
-- 第 2 段：在 date-project 库（Python 应用库）执行
--          删除只用于登记页面刷新请求的表（执行前约 1 条 PENDING，无业务数据）。
-- ============================================================
USE `date-project`;

DROP TABLE IF EXISTS dws_ebay_price_analysis_refresh_request;

-- 校验：应为 0（表已不存在）；dws_ebay_price_analysis 应为 1（保留）。
SELECT
  (SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema='date-project' AND table_name='dws_ebay_price_analysis_refresh_request') AS request_table_left,
  (SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema='date-project' AND table_name='dws_ebay_price_analysis') AS analysis_table_kept;
