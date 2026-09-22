-- ============================================================================
-- eBay库存明细：产品等级改为计算字段 —— 部署机需要执行的全部SQL
--
-- 对应提交：feat(ebay-inventory): 新增利润率与历史最大月销，等级改为按规则计算
-- 目标库：Python库 `date-project`（不是 jmh_data_platform）
--
-- 执行顺序很重要：第1步必须在重启Python服务之前或之后立刻执行都可以
-- （代码对该表缺失做了容错，读取按空处理，不会报错）；
-- 第3步删表必须等页面确认正常之后再执行，且不可逆。
--
-- 本文件不包含菜单/权限SQL：页面、权限标识、按钮权限都沿用原有的
-- operations:ebayInventoryDetail:*，本次没有新增或删除菜单项。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4;


-- ============================================================================
-- 第1步【必须执行】新建历史最大月销高水位表
--
-- 为什么需要：订单表 dwd_ebay_sku_analysis_order 是Excel导入累积的，目前只有
-- 2026-05 起的数据，更早的历史高点重算不出来。业务口径是"只有某个自然月的总
-- 销量超过当前值时才更新"，即只升不降，必须落库保存。
--
-- 键与页面合并口径一致：有合法数字中间码时按"站点+中间码"，否则退回
-- "站点+完整SKU"。页面点「重新计算」时用 GREATEST 抬高，查询路径只读。
-- ============================================================================

CREATE TABLE IF NOT EXISTS dws_ebay_inventory_max_monthly_sales (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    site VARCHAR(100) NOT NULL COMMENT '归一站点：德国、英国、美国、法国',
    product_key_type VARCHAR(16) NOT NULL COMMENT '键类型：MIDDLE=站点+中间码，SKU=站点+完整SKU（无合法中间码时）',
    product_key VARCHAR(255) NOT NULL COMMENT 'product_key_type为MIDDLE时是数字中间码文本（保留前导零）；为SKU时是大写完整SKU',
    max_monthly_sales DECIMAL(30,6) NOT NULL COMMENT '历史最大自然月销量；只升不降，仅当某月总销量超过此值时更新',
    peak_month CHAR(7) NULL COMMENT '产生当前高点的自然月YYYY-MM；种入的初值可为空',
    value_source VARCHAR(16) NOT NULL DEFAULT 'CALCULATED' COMMENT '当前值来源：CALCULATED=订单表算出，SEEDED=业务表格种入',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_max_monthly_sales_product (site, product_key_type, product_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Ebay库存明细历史最大月销高水位，按站点+中间码保存，只升不降';


-- ============================================================================
-- 第2步【只读验证】重启服务 + 点击页面「重新计算」之后执行
--
-- 预期：
--   建表行数 > 0（开发库实测1469行）
--   峰值月份里不应出现当前未结束的月份
--   等级不应全为空
-- ============================================================================

-- 2.1 高水位是否已写入
SELECT COUNT(*) AS 高水位行数,
       SUM(value_source = 'CALCULATED') AS 算出的,
       SUM(value_source = 'SEEDED')     AS 种入的,
       MAX(updated_at)                  AS 最后更新
FROM dws_ebay_inventory_max_monthly_sales;

-- 2.2 峰值月份分布；不应包含当前未结束的自然月
SELECT peak_month AS 峰值月, COUNT(*) AS 行数
FROM dws_ebay_inventory_max_monthly_sales
GROUP BY peak_month ORDER BY peak_month;

-- 2.3 本次「重新计算」是否落了快照
SELECT stat_date AS 统计日, generated_at AS 生成时间,
       trigger_type AS 触发方式, item_count AS 行数
FROM ebay_inventory_pivot_snapshot
ORDER BY generated_at DESC LIMIT 3;

-- 2.4 等级是否算出来了（开发库实测 E:624 --:614 D:370 C:221 A:62 S:20 B:15）
SELECT COALESCE(JSON_UNQUOTE(JSON_EXTRACT(h.item_json, '$.values.grade')), '--') AS 等级,
       COUNT(*) AS 行数
FROM ebay_inventory_detail_history h
JOIN ebay_inventory_pivot_snapshot s ON s.id = h.snapshot_id
WHERE s.stat_date = CURDATE()
GROUP BY 等级 ORDER BY 行数 DESC;


-- ============================================================================
-- 第3步【不可逆】删除旧的人工上传等级表
--
-- ！！执行前务必先导出留底 ！！
-- 开发库里这张表有1273行，其中192行（15%）是「刷单」「刷单E」「刷单C」
-- 「新品」这类人工业务标注。新公式只输出 S/A/B/C/D/E，删表后这些标注不再
-- 有任何载体，也无法从计算结果还原。业务方若仍需要这些标记，先另行导出保存。
--
-- 留底（在部署机命令行执行，不是SQL）：
--   mysqldump -u<用户> -p date-project ebay_inventory_detail_grade > grade_backup.sql
--
-- 该表已无任何代码读写：Python的 /grades/import 与 upsert_grades、Java的
-- importGrades、前端「导入产品等级」入口均已随本次提交下线；历史透视行在
-- 生成当天已把等级写进快照JSON，不回查此表。
-- ============================================================================

DROP TABLE IF EXISTS ebay_inventory_detail_grade;


-- ============================================================================
-- 第4步【只读验证】删表之后确认页面仍正常
--
-- 该表已无代码读写，删除后页面行数、等级分布都不应变化。
-- 开发库实测：删表前后均为1926行，等级分布
-- E:624 --:614 D:370 C:221 A:62 S:20 B:15，完全一致。
-- ============================================================================

-- 4.1 表确实不存在了（应返回空结果）
SHOW TABLES LIKE 'ebay_inventory_detail_grade';

-- 4.2 页面行数与等级分布不应变化（与第2.4步的结果比对）
SELECT COALESCE(JSON_UNQUOTE(JSON_EXTRACT(h.item_json, '$.values.grade')), '--') AS 等级,
       COUNT(*) AS 行数
FROM ebay_inventory_detail_history h
JOIN ebay_inventory_pivot_snapshot s ON s.id = h.snapshot_id
WHERE s.stat_date = CURDATE()
GROUP BY 等级 ORDER BY 行数 DESC;
