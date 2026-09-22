-- Python数据库；"历史最大月销"由自然月口径改为滚动30天窗口口径。
--
-- 原口径：把销量按自然月汇总，取最高的那个月，当月未结束不参与。
-- 新口径：窗口 [统计日期-30, 统计日期)，不含当天，与页面「近30天销量」同一个窗口；
--         历史最大 = 所有可能窗口里的最大值。窗口可以跨月，不再按月边界切分。
--
-- 因此 peak_month（YYYY-MM）不再能表达峰值位置，新增 peak_window_end 记录窗口右端。
--
-- 本脚本只新增列、不删列，目的是让部署顺序在任何时刻都不中断：
--   旧代码写 peak_month（该列仍在，可继续写）
--   新代码写 peak_window_end（该列已建好，可直接写）
-- 两边都不会因为缺列报错，先执行本脚本还是先发代码都安全。
-- peak_month 作为遗留列保留，确认页面正常后再按文件末尾的可选步骤删除。
USE `date-project`;
SET NAMES utf8mb4;

ALTER TABLE dws_ebay_inventory_max_monthly_sales
  ADD COLUMN peak_window_end DATE NULL
    COMMENT '产生当前高点的30天窗口右端（开区间）；窗口为[本列-30, 本列)，种入的初值可为空'
    AFTER max_monthly_sales;

ALTER TABLE dws_ebay_inventory_max_monthly_sales
  COMMENT='Ebay库存明细历史最大30天滚动销量高水位，按站点+中间码保存，只升不降';


-- ============================================================================
-- 可选：确认页面正常、且不再需要旧口径的峰值月份后，再执行下面这行。
-- peak_month 已无任何代码读写；内容由订单表派生，回填脚本会重新写满
-- peak_window_end，删除不造成数据损失。
-- ============================================================================
-- ALTER TABLE dws_ebay_inventory_max_monthly_sales DROP COLUMN peak_month;
