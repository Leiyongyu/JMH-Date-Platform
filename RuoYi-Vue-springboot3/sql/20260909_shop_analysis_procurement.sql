-- ============================================================================
-- 06_店铺分析与采购优化.sql
-- 目标库：jmh_data_platform（ERP 库；补货2.0 的全部配置表都在这个库）
-- 用途  ：本轮四项改动所需的全部 DDL 与菜单权限
-- 特性  ：幂等，可重复执行；不删除任何业务数据
-- 生成  ：2026-09-09
--
-- 【本轮四项改动】
--   1) 补货2.0「产品等级」改为点击字段头可编辑规则   -> 需要新表（本文件）
--   2) SKU分析新增成都/海外在途与可售 4 个字段        -> 纯代码，无 SQL
--   3) 待采购页新增删除按钮                           -> 需要新按钮权限（本文件）
--   5) 新增「安全库存2」「建议补货量2」               -> 纯代码，无 SQL
--
--   改动 2 直接复用 jmh_data_platform.warehouse_inventory_detail，
--   由现有定时任务维护；分页后批量匹配，避免库存与订单JOIN导致重复累计。
--
--   改动 5 复用现有 ebay_replenishment_v2_formula 的 S/A/B/C 系数，
--   共用同一个编辑弹窗，第二组日销为「未取整预估销量2 / 30」，
--   所以既不建表也不加权限。
-- ============================================================================

USE `jmh_data_platform`;
SET NAMES utf8mb4;
-- DDL仍可能等待元数据锁。设置短等待；遇到任何错误必须停止并检查。
SET SESSION lock_wait_timeout = 15;
SET SESSION innodb_lock_wait_timeout = 15;

-- ---------------------------------------------------------------------------
-- 一、产品等级规则表（改动 1）
--
-- 现状：等级由 ebay_replenishment_v2_service.py 的 _product_level() 硬编码，
--       6 个阈值写死在 if 链里，运营改不了。
--       该函数的 docstring 写的是「按用户给定的 1→9 优先级」——
--       原始需求本来就是 9 条规则，只是被压成了 if 链。本表把它还原回 9 条。
--
-- 设计：结构完全对齐已经在跑的 ebay_replenishment_v2_forecast_rule（13条规则，
--       预估销量2 用的那张），复用同一套 AST 白名单表达式引擎
--       backend/services/ebay_forecast_rule_engine.py，
--       前端弹窗复用 components/ForecastRuleDialog.vue 的形态。
--       按 rule_no 从小到大匹配，第一条命中即返回，与现有 if 链语义一致。
--
-- 可用变量（全部为小数比率，不是百分数）：
--   return_rate        退货率 = 近3月退货量合计 / 近3月销量合计
--   profit_rate        利润率 = 近3月毛利合计 / 近3月已支付金额合计
--   sell_through_ratio 动销比 = 预估销量 / 海外可售
--
-- 空值语义（必须与现状一致，否则等级会凭空变出来）：
--   现状 _product_level() 在 return_rate 为空时直接返回 None（页面显示 --），
--   在规则 1 之后 profit_rate 为空返回 None，规则 3 之后 sell_through_ratio
--   为空返回 None。规则引擎必须保留这个行为：
--   表达式引用到值为 None 的变量时，该行等级返回 None（显示 --），
--   不能当成 0 继续往下匹配。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ebay_replenishment_v2_level_rule` (
  `rule_no` TINYINT UNSIGNED NOT NULL COMMENT '规则序号，同时决定匹配顺序，从小到大取第一个命中',
  `condition_expr` VARCHAR(500) NOT NULL COMMENT '条件表达式，恒真写 true；可用变量 return_rate/profit_rate/sell_through_ratio',
  `result_level` VARCHAR(8) NOT NULL COMMENT '命中后的产品等级：S/A/B/C',
  `remark` VARCHAR(255) NULL COMMENT '规则说明',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
  `update_by` VARCHAR(64) NULL COMMENT '最后修改人',
  `update_time` DATETIME NULL COMMENT '最后修改时间',
  PRIMARY KEY (`rule_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='eBay补货2.0产品等级规则：9条，条件与结果等级均可直接改本表';

-- 初始 9 条：与当前 _product_level() 硬编码逻辑逐条等价，部署后等级不会变。
-- ON DUPLICATE KEY UPDATE rule_no=rule_no 是刻意的空更新：
-- 重复执行只补缺失行，绝不覆盖运营已经手工调过的条件和等级。
START TRANSACTION;
INSERT INTO `ebay_replenishment_v2_level_rule`
  (rule_no, condition_expr, result_level, remark, status, update_by, update_time)
VALUES
  (1, 'return_rate > 0.06',                        'C', '退货率高于6%直接判C',                     1, 'SYSTEM', NOW()),
  (2, 'return_rate >= 0.03 and profit_rate < 0.18','C', '退货率3%~6%且利润率低于18%判C',           1, 'SYSTEM', NOW()),
  (3, 'return_rate >= 0.03',                       'B', '退货率3%~6%且利润率不低于18%判B（长尾并入B）', 1, 'SYSTEM', NOW()),
  (4, 'profit_rate < 0.12 and sell_through_ratio <= 0.12', 'C', '退货率低于3%，利润率低于12%且动销比不高于12%判C', 1, 'SYSTEM', NOW()),
  (5, 'profit_rate < 0.12',                        'B', '退货率低于3%，利润率低于12%但动销比高于12%判B', 1, 'SYSTEM', NOW()),
  (6, 'profit_rate < 0.22 and sell_through_ratio < 0.12',  'B', '利润率12%~22%且动销比低于12%判B',   1, 'SYSTEM', NOW()),
  (7, 'profit_rate < 0.22',                        'A', '利润率12%~22%且动销比不低于12%判A',        1, 'SYSTEM', NOW()),
  (8, 'sell_through_ratio < 0.15',                 'B', '利润率不低于22%但动销比低于15%判B',        1, 'SYSTEM', NOW()),
  (9, 'true',                                      'S', '利润率不低于22%且动销比不低于15%判S（兜底）', 1, 'SYSTEM', NOW())
ON DUPLICATE KEY UPDATE rule_no = rule_no;

-- ---------------------------------------------------------------------------
-- 二、待采购删除按钮权限（改动 3）
--
-- 待采购页由权限串查询，不依赖各环境不同的menu_id。
-- 已有两个按钮权限
--         procurement:pendingPurchase:add     采购确认
--         procurement:pendingPurchase:export  导出待采购
--       本轮补第三个 remove。
--
-- 不自动给任何角色授权；07_仅只读核对，授权在「系统管理-角色管理」手工勾选。
-- ---------------------------------------------------------------------------
SET @pending_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE perms = 'procurement:pendingPurchase:list' AND menu_type = 'C'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO `sys_menu`
  (menu_name, parent_id, order_num, path, component, query, route_name,
   is_frame, is_cache, menu_type, visible, status, perms, icon,
   create_by, create_time, remark)
SELECT '删除待采购', @pending_menu_id, 3, '', NULL, NULL, '',
       1, 0, 'F', '0', '0', 'procurement:pendingPurchase:remove', '#',
       'SYSTEM', NOW(), '待采购列表勾选后批量删除；只允许删除未导出的待采购记录'
WHERE @pending_menu_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms = 'procurement:pendingPurchase:remove');

COMMIT;

SELECT IF(@pending_menu_id IS NULL,
          '★ 错误：未找到待采购页面菜单(procurement:pendingPurchase:list)，请先部署采购中心再重跑本脚本',
          '待采购父菜单已找到') AS `提示`;

-- ---------------------------------------------------------------------------
-- 三、核对
-- ---------------------------------------------------------------------------
SELECT '=== 产品等级规则（应 9 行，按 rule_no 顺序匹配）===' AS `提示`;
SELECT rule_no AS `序号`, condition_expr AS `条件`, result_level AS `等级`,
       status AS `启用`, remark AS `说明`
FROM `ebay_replenishment_v2_level_rule` ORDER BY rule_no;

SELECT '=== 待采购菜单及三个按钮权限（应 4 行）===' AS `提示`;
SELECT menu_id AS `菜单ID`, parent_id AS `父级`, menu_name AS `名称`,
       order_num AS `排序`, perms AS `权限串`
FROM sys_menu WHERE perms LIKE 'procurement:pendingPurchase:%'
ORDER BY order_num, menu_id;

SELECT '06 脚本执行完毕' AS `结果`;

