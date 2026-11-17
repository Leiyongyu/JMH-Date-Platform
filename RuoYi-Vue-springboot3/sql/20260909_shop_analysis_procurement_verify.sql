-- ============================================================================
-- 07_店铺分析与采购优化_验证_只读.sql
-- 用途：06 执行后的核对。纯 SELECT，不改任何数据。
-- 用法：进入 MySQL 客户端后执行
--         SOURCE D:/JMH/项目/部署sql/07_店铺分析与采购优化_验证_只读.sql;
-- 生成：2026-09-09
-- ============================================================================

USE `jmh_data_platform`;

SELECT '========== 检查 1：产品等级规则表建成且为 9 条 ==========' AS ``;
-- 期望：9 行，rule_no 连续 1~9；初次初始化status全为1，人工停用后允许为0。
SELECT rule_no AS `序号`, condition_expr AS `条件`, result_level AS `等级`,
       status AS `启用`, update_by AS `修改人`, remark AS `说明`
FROM ebay_replenishment_v2_level_rule ORDER BY rule_no;

SELECT '========== 检查 2：规则完整性自检（初始配置四项应为 OK）==========' AS ``;
SELECT '规则条数为9'   AS `检查项`, IF(COUNT(*)=9,'OK',CONCAT('★ 实际 ',COUNT(*),' 条')) AS `结论`
FROM ebay_replenishment_v2_level_rule
UNION ALL
SELECT '序号1-9连续', IF(MIN(rule_no)=1 AND MAX(rule_no)=9 AND COUNT(DISTINCT rule_no)=9,'OK','★ 序号不连续')
FROM ebay_replenishment_v2_level_rule
UNION ALL
SELECT '存在恒真兜底', IF(SUM(TRIM(LOWER(condition_expr))='true' AND status=1)>=1,'OK',
                        '★ 没有启用的恒真兜底规则，条件都不命中的SKU等级会是--')
FROM ebay_replenishment_v2_level_rule
UNION ALL
SELECT '等级取值合法', IF(SUM(result_level NOT IN ('S','A','B','C'))=0,'OK',
                        '★ 存在 S/A/B/C 之外的等级，系数表匹配不上会导致安全库存显示--')
FROM ebay_replenishment_v2_level_rule;

SELECT '========== 检查 3：等级与系数表能对上 ==========' AS ``;
-- 规则表产出的等级必须在系数表里都有对应行，否则安全库存和建议补货量会显示 --
SELECT DISTINCT r.result_level AS `规则产出等级`,
       IF(f.product_level IS NULL,'★ 系数表缺此等级','OK') AS `结论`
FROM ebay_replenishment_v2_level_rule r
LEFT JOIN ebay_replenishment_v2_formula f
       ON f.product_level = r.result_level AND f.status = 1
WHERE r.status = 1
ORDER BY r.result_level;

SELECT '========== 检查 4：安全库存系数表（改动5复用它，应 4 行）==========' AS ``;
-- 改动5「安全库存2/建议补货量2」不新建配置，共用这张表的同一套系数
SELECT product_level AS `等级`, safety_coefficient AS `安全系数`,
       suggest_coefficient AS `补货系数`, status AS `启用`
FROM ebay_replenishment_v2_formula ORDER BY product_level;

SELECT '========== 检查 5：待采购四条菜单权限 ==========' AS ``;
-- 期望：list / add / export / remove 四行，remove 是本轮新增
SELECT menu_id AS `菜单ID`, parent_id AS `父级`, menu_name AS `名称`,
       menu_type AS `类型`, order_num AS `排序`, perms AS `权限串`, status AS `状态`
FROM sys_menu WHERE perms LIKE 'procurement:pendingPurchase:%'
ORDER BY order_num, menu_id;

SELECT '========== 检查 6：删除按钮的授权情况 ==========' AS ``;
-- 0 行表示还没给任何角色授权，页面上看不到删除按钮，属正常待办
SELECT r.role_id AS `角色ID`, r.role_name AS `角色名`
FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id AND m.perms = 'procurement:pendingPurchase:remove'
JOIN sys_role r ON r.role_id = rm.role_id
ORDER BY r.role_id;

SELECT '========== 检查 7：待采购数据现状（删除只允许删 status=0）==========' AS ``;
SELECT status AS `状态`,
       CASE status WHEN '0' THEN '待采购（可删）' WHEN '1' THEN '已采购（禁止删）' ELSE '未知' END AS `含义`,
       COUNT(*) AS `行数`
FROM procurement_pending_purchase GROUP BY status ORDER BY status;

SELECT '========== 检查 8：改动2的数据源可用性 ==========' AS ``;
-- SKU分析新增的4个字段直接读这张表，与补货2.0同源，不新建表
SELECT COUNT(*) AS `库存明细行数`, COUNT(DISTINCT wid) AS `仓库数`,
       IF(COUNT(*)>0,'OK','★ 表为空，SKU分析4个字段会全是0') AS `结论`
FROM warehouse_inventory_detail
WHERE wid IN (18674,18675,18676,18699,18700,18701,18702);

SELECT '========== 检查 9：还缺什么（应返回 0 行）==========' AS ``;
SELECT '缺表' AS `缺失类型`, 'ebay_replenishment_v2_level_rule' AS `名称`
WHERE NOT EXISTS (SELECT 1 FROM information_schema.TABLES
  WHERE TABLE_SCHEMA='jmh_data_platform' AND TABLE_NAME='ebay_replenishment_v2_level_rule')
UNION ALL
SELECT '缺权限', 'procurement:pendingPurchase:remove'
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='procurement:pendingPurchase:remove')
UNION ALL
SELECT '缺规则', CONCAT('产品等级规则只有 ',
  (SELECT COUNT(*) FROM ebay_replenishment_v2_level_rule), ' 条，应为 9 条')
WHERE (SELECT COUNT(*) FROM ebay_replenishment_v2_level_rule) <> 9;

SELECT '验证脚本执行完毕' AS `结果`;

