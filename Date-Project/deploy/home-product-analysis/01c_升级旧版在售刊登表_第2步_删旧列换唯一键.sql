-- ============================================================================
-- 【只有旧库需要】把 2026-09-18 版的在售刊登表升级成按月累积的结构 · 第2步
--
-- 在 Python 业务库 date-project 执行。可重复执行。
--
-- ⚠️⚠️ 本脚本会**永久删除** raw_xml / response_meta_json / normalized_json
--       三列的内容。执行前必须满足两个条件：
--         1. 已有数据库备份
--         2. 01b 第4步的五个数全是 0、第5步两段都返回空结果
--       不满足就不要执行，先把 01b 的结果发回来。
--
-- ----------------------------------------------------------------------------
-- 为什么这些列必须删，不能留着
-- ----------------------------------------------------------------------------
-- 它们在旧表里是 NOT NULL 且没有默认值（JSON 列也不允许有默认值）。新版同步
-- 代码只写扁平列和 variations_json，不再写这三列，所以只要它们还在，
-- **下一次「eBay店铺商品信息每月同步」会直接报 1364 字段没有默认值**，
-- 一行都写不进去。source_page、api_total 同理。
--
-- 顺带也省地方：开发机实测这三列占 91MB 里的 57MB，按月累积一年就是 1.2GB，
-- 而抽样 3000 行核对过，normalized_json 除 variations 外的键全部与扁平列重复。
-- 接口返回的是当前在售状态、随时能重拉，原始XML留着的边际价值很低。
--
-- ----------------------------------------------------------------------------
-- 唯一键为什么要换
-- ----------------------------------------------------------------------------
-- 旧键 (账号, ItemID) 意味着同一个商品全库只能有一行 —— 那是"整表覆盖"时代的
-- 设计。改成 (月份, 账号, ItemID) 之后，同一个商品每个月各留一行，才谈得上
-- 趋势；同月同账号同商品仍然只能有一行，重复写入会直接报错，不会悄悄多一份。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @db = DATABASE();
SET SESSION group_concat_max_len = 65535;


-- ============================================================================
-- 第0步【闸门 · 只读】再确认一次能不能往下走
--
-- 「结论」必须是「可以执行」。是「不要执行」就停下来，把 01b 的结果发回来。
-- ============================================================================
-- 判断条件要按列是否存在分步求值：MySQL 会解析整条 IF 链，
-- 升级完 normalized_json 没了，写死在里面会直接 1054，重跑就报错。
SET @has_tbl  = EXISTS(SELECT 1 FROM information_schema.TABLES
                       WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest');
SET @has_norm = EXISTS(SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                         AND COLUMN_NAME='normalized_json');
SET @has_var  = EXISTS(SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                         AND COLUMN_NAME='variations_json');
SET @has_mon  = EXISTS(SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                         AND COLUMN_NAME='stat_month');
SET @null_month = 0;
SET @bad_var = 0;

SET @sql = IF(@has_tbl AND @has_mon,
  'SELECT COUNT(*) INTO @null_month FROM ods_ebay_store_listing_latest WHERE stat_month IS NULL',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(@has_tbl AND @has_norm AND @has_var,
  'SELECT IFNULL(SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,''$.variations'')),0)'
  ' <> COALESCE(JSON_LENGTH(variations_json),0)),0) INTO @bad_var'
  ' FROM ods_ebay_store_listing_latest',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT
  IF(NOT @has_tbl,     '表不存在 → 本脚本不用执行',
  IF(NOT @has_norm,    '已经升级过 → 本脚本会全部跳过，跑完看第5步验收即可',
  IF(NOT @has_var,     '不要执行 → 还没跑 01b，变体数组尚未抽出来，现在删会永久丢失',
  IF(@null_month > 0,  '不要执行 → 还有行的 stat_month 是空的，先把 01b 跑完',
  IF(@bad_var > 0,     '不要执行 → 变体数对不上，回填有问题，先查 01b 第4步',
                       '可以执行'))))) AS 结论,
  @null_month AS 月份为空的行, @bad_var AS 变体数对不上的行;


-- ============================================================================
-- 第1步 stat_month 改成 NOT NULL
-- ============================================================================
SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                       AND COLUMN_NAME='stat_month' AND IS_NULLABLE='YES'),
  'ALTER TABLE ods_ebay_store_listing_latest MODIFY COLUMN stat_month CHAR(7) NOT NULL COMMENT ''留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份''',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_state'
                       AND COLUMN_NAME='stat_month' AND IS_NULLABLE='YES'),
  'ALTER TABLE ods_ebay_store_listing_state MODIFY COLUMN stat_month CHAR(7) NOT NULL COMMENT ''留档月份YYYY-MM''',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ============================================================================
-- 第2步 删掉五个旧列
--
-- 存在哪几个就删哪几个，拼成一条 ALTER 一次做完（分多条会多次重建表）。
-- 全都已经删过时 @drops 是 NULL，整段跳过。
-- ============================================================================
SET @drops = (SELECT GROUP_CONCAT(CONCAT('DROP COLUMN `', COLUMN_NAME, '`') SEPARATOR ', ')
              FROM information_schema.COLUMNS
              WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                AND COLUMN_NAME IN ('raw_xml','response_meta_json','normalized_json',
                                    'source_page','api_total'));
SET @sql = IF(@drops IS NULL, 'DO 0',
              CONCAT('ALTER TABLE ods_ebay_store_listing_latest ', @drops));
SELECT IFNULL(@sql,'DO 0') AS 本次将执行的删列语句;
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ============================================================================
-- 第3步 换唯一键与索引
--
-- 旧 uk_seller_item(账号,ItemID) → uk_month_seller_item(月份,账号,ItemID)
-- 两件事必须在同一条 ALTER 里做：先删后建会有一瞬间没有唯一约束。
-- ============================================================================
SET @has_old_uk = EXISTS(SELECT 1 FROM information_schema.STATISTICS
                         WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                           AND INDEX_NAME='uk_seller_item');
SET @has_new_uk = EXISTS(SELECT 1 FROM information_schema.STATISTICS
                         WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                           AND INDEX_NAME='uk_month_seller_item');
SET @sql = IF(@has_new_uk, 'DO 0',
              CONCAT('ALTER TABLE ods_ebay_store_listing_latest ',
                     IF(@has_old_uk, 'DROP INDEX uk_seller_item, ', ''),
                     'ADD UNIQUE KEY uk_month_seller_item(stat_month,seller_user_id,item_id)'));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 两个按月查的辅助索引
SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                       AND INDEX_NAME='idx_month'),
  'DO 0', 'ALTER TABLE ods_ebay_store_listing_latest ADD KEY idx_month(stat_month)');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                       AND INDEX_NAME='idx_seller_month'),
  'DO 0', 'ALTER TABLE ods_ebay_store_listing_latest ADD KEY idx_seller_month(seller_user_id,stat_month)');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 表注释也刷一下，免得以后有人照旧注释理解这张表
ALTER TABLE ods_ebay_store_listing_latest
  COMMENT='ODS-eBay官方Trading在售商品，按月累积；每账号每月一份，键(月份,账号,ItemID)。不存原始XML与响应元数据，多规格变体见variations_json';


-- ============================================================================
-- 第4步 state 表换主键
--
-- 旧主键 (账号) → (月份, 账号)：每个账号每月一行。
-- row_count=0 也要留行，趋势图才能区分"当月空店"和"当月没同步"。
-- ============================================================================
SET @state_pk_cols = (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
                      FROM information_schema.STATISTICS
                      WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_state'
                        AND INDEX_NAME='PRIMARY');
SET @sql = IF(@state_pk_cols = 'stat_month,seller_user_id', 'DO 0',
  CONCAT('ALTER TABLE ods_ebay_store_listing_state ',
         IF(@state_pk_cols IS NULL, '', 'DROP PRIMARY KEY, '),
         'ADD PRIMARY KEY (stat_month,seller_user_id)'));
SELECT IFNULL(@state_pk_cols,'(无主键)') AS state表当前主键, @sql AS 本次将执行;
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_state'
                       AND INDEX_NAME='idx_month'),
  'DO 0', 'ALTER TABLE ods_ebay_store_listing_state ADD KEY idx_month(stat_month)');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

ALTER TABLE ods_ebay_store_listing_state
  COMMENT='ODS-eBay店铺每月同步状态，每账号每月一行；row_count=0代表当月确实空店，缺行代表当月没同步';


-- ============================================================================
-- 第5步【只读】验收
-- ============================================================================

-- 5.1 行数与变体，必须与 01b 第1步记的底数完全一致
SELECT COUNT(*) AS 行数, COUNT(DISTINCT stat_month) AS 月份数,
       MIN(stat_month) AS 最早月份, MAX(stat_month) AS 最晚月份,
       SUM(variations_json IS NOT NULL) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(variations_json),0)) AS 变体总数
FROM ods_ebay_store_listing_latest;

-- 5.2 旧列确实没了（预期：返回空结果）
SELECT COLUMN_NAME AS 不该存在的列
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
  AND COLUMN_NAME IN ('raw_xml','response_meta_json','normalized_json','source_page','api_total');

-- 5.3 键对不对（预期：uk_month_seller_item 三列、state 主键两列）
SELECT TABLE_NAME AS 表, INDEX_NAME AS 索引,
       GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS 列,
       IF(NON_UNIQUE=0,'唯一','普通') AS 类型
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA=@db
  AND TABLE_NAME IN ('ods_ebay_store_listing_latest','ods_ebay_store_listing_state')
GROUP BY TABLE_NAME, INDEX_NAME, NON_UNIQUE
ORDER BY TABLE_NAME, INDEX_NAME;

-- 5.4 每月每账号的条数与 state 对得上（预期：对得上_应为1 全是 1）
SELECT s.stat_month AS 月份, COUNT(*) AS 账号数, SUM(s.row_count) AS 状态表条数,
       (SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
        WHERE l.stat_month=s.stat_month) AS 明细条数,
       SUM(s.row_count)=(SELECT COUNT(*) FROM ods_ebay_store_listing_latest l
                         WHERE l.stat_month=s.stat_month) AS 对得上_应为1
FROM ods_ebay_store_listing_state s GROUP BY s.stat_month ORDER BY s.stat_month;

-- 5.5 容量（旧结构约 91MB/份，裁剪后约 34MB/月）
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND(DATA_LENGTH/1024/1024,1) AS 数据MB, ROUND(INDEX_LENGTH/1024/1024,1) AS 索引MB,
       ROUND(DATA_FREE/1024/1024,1) AS 碎片MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA=@db AND TABLE_NAME LIKE 'ods_ebay_store_listing%';

-- 注：DROP COLUMN 是 INSTANT 操作，腾出来的空间暂时留在「碎片MB」里，
-- 后续写入会复用，不必特意 OPTIMIZE TABLE（那会锁表重建 18000 行）。
