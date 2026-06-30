-- eBay补货公式配置: 扩展字段 + 默认种子数据
-- 可重复执行; 新增列和种子数据, 不删除已有配置

-- 1. 扩展字段
SET @has_lower_bound := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'ebay_replenish_formula' AND column_name = 'lower_bound');
SET @sql := IF(@has_lower_bound = 0, 'ALTER TABLE ebay_replenish_formula ADD COLUMN lower_bound DECIMAL(10,4) NULL COMMENT ''阈值下限'' AFTER condition_desc', 'SELECT 1'); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_upper_bound := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'ebay_replenish_formula' AND column_name = 'upper_bound');
SET @sql := IF(@has_upper_bound = 0, 'ALTER TABLE ebay_replenish_formula ADD COLUMN upper_bound DECIMAL(10,4) NULL COMMENT ''阈值上限'' AFTER lower_bound', 'SELECT 1'); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_compare_metric := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'ebay_replenish_formula' AND column_name = 'compare_metric');
SET @sql := IF(@has_compare_metric = 0, 'ALTER TABLE ebay_replenish_formula ADD COLUMN compare_metric VARCHAR(10) NULL COMMENT ''D7_AVG/D15_AVG/NONE'' AFTER upper_bound', 'SELECT 1'); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_multiply_30 := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'ebay_replenish_formula' AND column_name = 'multiply_30');
SET @sql := IF(@has_multiply_30 = 0, 'ALTER TABLE ebay_replenish_formula ADD COLUMN multiply_30 TINYINT NOT NULL DEFAULT 1 COMMENT ''结果乘30'' AFTER multiplier', 'SELECT 1'); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_rule_group := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'ebay_replenish_formula' AND column_name = 'rule_group');
SET @sql := IF(@has_rule_group = 0, 'ALTER TABLE ebay_replenish_formula ADD COLUMN rule_group VARCHAR(30) NULL COMMENT ''NEW_PRODUCT/OLD_D7_POSITIVE/OLD_D7_ZERO_D15_POSITIVE/OLD_NO_SALES'' AFTER product_nature', 'SELECT 1'); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @has_remark := (SELECT COUNT(1) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'ebay_replenish_formula' AND column_name = 'remark');
SET @sql := IF(@has_remark = 0, 'ALTER TABLE ebay_replenish_formula ADD COLUMN remark VARCHAR(500) NULL COMMENT '''' AFTER multiply_30', 'SELECT 1'); PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 2. 种子数据 (IF NOT EXISTS 风格)
INSERT IGNORE INTO ebay_replenish_formula
(id, rule_group, product_nature, scenario_order, name, condition_desc, compare_metric, lower_bound, upper_bound, weight_7d, weight_15d, weight_30d, multiplier, multiply_30, status, remark)
VALUES
-- 新品: result = d30 * 30 / age
(1,  'NEW_PRODUCT',    0, 1, '新品-按仓库龄折算',  '新品：30天销量 × 30 ÷ 海外仓库龄', 'NONE', NULL, NULL, 0, 0, 1.0, 1, 0, 1, '新品不走加权平均, 直接用d30*30/age'),

-- 老品 d7>0: 按 d7_avg 与 d30_avg 的比例分5档
(2,  'OLD_D7_POSITIVE', 1, 2, '老品-7天上升期(≥1.2)',   '7日均销 ≥ 30日均销 × 1.2', 'D7_AVG', 1.2,  NULL, 0.70, 0.20, 0.10, 1, 1, 1, 'd7_avg >= d30_avg*1.2'),
(3,  'OLD_D7_POSITIVE', 1, 3, '老品-7天平稳期(1.0~1.2)','7日均销 ∈ [1.0, 1.2) × 30日均销', 'D7_AVG', 1.0, 1.2, 0.60, 0.25, 0.15, 1, 1, 1, 'd7_avg >= d30_avg*1.0'),
(4,  'OLD_D7_POSITIVE', 1, 4, '老品-7天微降期(0.8~1.0)','7日均销 ∈ [0.8, 1.0) × 30日均销', 'D7_AVG', 0.8, 1.0, 0.50, 0.30, 0.20, 1, 1, 1, 'd7_avg >= d30_avg*0.8'),
(5,  'OLD_D7_POSITIVE', 1, 5, '老品-7天下降期(0.5~0.8)','7日均销 ∈ [0.5, 0.8) × 30日均销', 'D7_AVG', 0.5, 0.8, 0.35, 0.35, 0.30, 1, 1, 1, 'd7_avg >= d30_avg*0.5'),
(6,  'OLD_D7_POSITIVE', 1, 6, '老品-7天低谷期(<0.5)',    '7日均销 < 30日均销 × 0.5', 'D7_AVG', NULL, 0.5, 0.20, 0.30, 0.50, 1, 1, 1, 'd7_avg < d30_avg*0.5'),

-- 老品 d7=0 d15>0: 按 d15_avg 与 d30_avg 的比例分5档
(7,  'OLD_D7_ZERO_D15_POSITIVE', 1, 7, '老品-15天上升期(≥1.3)',   '15日均销 ≥ 30日均销 × 1.3', 'D15_AVG', 1.3,  NULL, 0, 0.60, 0.40, 1, 1, 1, 'd7=0, d15_avg >= d30_avg*1.3'),
(8,  'OLD_D7_ZERO_D15_POSITIVE', 1, 8, '老品-15天平稳期(1.1~1.3)','15日均销 ∈ [1.1, 1.3) × 30日均销', 'D15_AVG', 1.1, 1.3, 0, 0.50, 0.50, 1, 1, 1, 'd7=0, d15_avg >= d30_avg*1.1'),
(9,  'OLD_D7_ZERO_D15_POSITIVE', 1, 9, '老品-15天微降期(0.9~1.1)','15日均销 ∈ [0.9, 1.1) × 30日均销', 'D15_AVG', 0.9, 1.1, 0, 0.40, 0.60, 1, 1, 1, 'd7=0, d15_avg >= d30_avg*0.9'),
(10, 'OLD_D7_ZERO_D15_POSITIVE', 1,10, '老品-15天下降期(0.6~0.9)','15日均销 ∈ [0.6, 0.9) × 30日均销', 'D15_AVG', 0.6, 0.9, 0, 0.30, 0.70, 1, 1, 1, 'd7=0, d15_avg >= d30_avg*0.6'),
(11, 'OLD_D7_ZERO_D15_POSITIVE', 1,11, '老品-15天低谷期(<0.6)',    '15日均销 < 30日均销 × 0.6', 'D15_AVG', NULL, 0.6, 0, 0.20, 0.80, 1, 1, 1, 'd7=0, d15_avg < d30_avg*0.6'),

-- 老品 d7=0 d15=0
(12, 'OLD_NO_SALES', 1, 12, '老品-仅30天有销量', '7天=0, 15天=0, 30天>0: 30天销量', 'NONE', NULL, NULL, 0, 0, 1.0, 1, 1, 1, 'd7=0,d15=0,d30>0: d30'),
(13, 'OLD_NO_SALES', 1, 13, '老品-全部无销量',   '7天=0, 15天=0, 30天=0: 结果=0', 'NONE', NULL, NULL, 0, 0, 0, 1, 0, 1, 'd7=0,d15=0,d30=0: 0');
