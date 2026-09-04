-- 目标库：jmh_data_platform。
-- eBay补货2.0“预估销量2”公式配置；复用现有公式维护权限。
USE jmh_data_platform;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS ebay_replenishment_v2_forecast_formula (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  rule_group VARCHAR(16) NOT NULL COMMENT '规则组：OLD_7D、OLD_15D、MISC',
  tier TINYINT NOT NULL COMMENT '档位序号；MISC组固定为1',
  threshold_ratio DECIMAL(10,4) NULL COMMENT '相对近30天日均的下限；兜底档为NULL',
  weight_7d DECIMAL(10,4) NULL COMMENT '近7天日均权重',
  weight_15d DECIMAL(10,4) NULL COMMENT '近15天日均权重',
  weight_30d DECIMAL(10,4) NULL COMMENT '近30天日均权重',
  month_days DECIMAL(10,4) NULL COMMENT '日均折算月销天数；仅MISC使用',
  new_age_cap DECIMAL(10,4) NULL COMMENT '新品库龄分母封顶值；仅MISC使用',
  old_fallback_ratio DECIMAL(10,4) NULL COMMENT '无近期销量回退系数；仅MISC使用',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  remark VARCHAR(255) NULL COMMENT '备注',
  update_by VARCHAR(64) NULL COMMENT '最后修改人',
  update_time DATETIME NULL COMMENT '最后修改时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_group_tier (rule_group,tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay补货2.0预估销量2公式配置';

-- 重复部署只补缺失档位，不覆盖运营人员已经调整的公式数值。
INSERT INTO ebay_replenishment_v2_forecast_formula
  (rule_group,tier,threshold_ratio,weight_7d,weight_15d,weight_30d,
   month_days,new_age_cap,old_fallback_ratio,status,remark,update_by,update_time)
VALUES
  ('OLD_7D', 1,1.2000,0.7000,0.2000,0.1000,NULL,NULL,NULL,1,'规则2','SYSTEM',NOW()),
  ('OLD_7D', 2,1.0000,0.6000,0.2500,0.1500,NULL,NULL,NULL,1,'规则3','SYSTEM',NOW()),
  ('OLD_7D', 3,0.8000,0.5000,0.3000,0.2000,NULL,NULL,NULL,1,'规则4','SYSTEM',NOW()),
  ('OLD_7D', 4,0.5000,0.3500,0.3500,0.3000,NULL,NULL,NULL,1,'规则5','SYSTEM',NOW()),
  ('OLD_7D', 5,NULL,  0.2000,0.3000,0.5000,NULL,NULL,NULL,1,'规则6 兜底','SYSTEM',NOW()),
  ('OLD_15D',1,1.3000,NULL,  0.6000,0.4000,NULL,NULL,NULL,1,'规则7','SYSTEM',NOW()),
  ('OLD_15D',2,1.1000,NULL,  0.5000,0.5000,NULL,NULL,NULL,1,'规则8','SYSTEM',NOW()),
  ('OLD_15D',3,0.9000,NULL,  0.4000,0.6000,NULL,NULL,NULL,1,'规则9','SYSTEM',NOW()),
  ('OLD_15D',4,0.6000,NULL,  0.3000,0.7000,NULL,NULL,NULL,1,'规则10','SYSTEM',NOW()),
  ('OLD_15D',5,NULL,  NULL,  0.2000,0.8000,NULL,NULL,NULL,1,'规则11 兜底','SYSTEM',NOW()),
  ('MISC',   1,NULL,  NULL,  NULL,  NULL,  30.0000,999999.0000,1.0000,1,'规则1与规则12全局系数；新品库龄默认不封顶','SYSTEM',NOW())
ON DUPLICATE KEY UPDATE rule_group=VALUES(rule_group);

-- 兼容已经执行过旧版脚本且仍保留SYSTEM默认值的环境；不覆盖人工配置。
UPDATE ebay_replenishment_v2_forecast_formula
SET new_age_cap=999999.0000,
    remark='规则1与规则12全局系数；新品库龄默认不封顶',
    update_time=NOW()
WHERE rule_group='MISC' AND tier=1
  AND new_age_cap=30.0000
  AND COALESCE(update_by,'SYSTEM')='SYSTEM';

SELECT rule_group,tier,threshold_ratio,weight_7d,weight_15d,weight_30d,
       month_days,new_age_cap,old_fallback_ratio,status
FROM ebay_replenishment_v2_forecast_formula
ORDER BY FIELD(rule_group,'OLD_7D','OLD_15D','MISC'),tier;
