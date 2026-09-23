-- Python业务库 date-project：飞书多维表格「不良交易刊登」落本地表。
--
-- 来源：https://scnmv3if5x1t.feishu.cn/base/UjvXbOPJTalrRKsmZKpcUjQ5nEe
--       ?table=tbl4j735kfsuqcHl&view=vewohlM1T4
-- 业务节奏：每周三更新一批，按「登记日期」区分批次。实测全表 10655 条、
--           26 个登记日期（2026-03-31 起每周一批，每批 350~490 条）。
--
-- 列名用英文 snake_case、注释写飞书原字段名，与本库其它表一致；
-- 类型按飞书字段类型一一对应，不擅自改写：
--   飞书「日期」-> DATE（接口给的是毫秒时间戳，写库前换算成北京时区日期）
--   飞书「多行文本」-> VARCHAR，即使内容看着是数字或日期也照样存文本。
--     表里「总交易额」「不良交易率」「评估日期」这些在飞书就是文本字段，
--     强行转成 DECIMAL/DATE 会在空串、'-'、格式不一致时丢数据或报错；
--     要算数时在查询里 CAST，源表保真。
--   飞书「关联」-> JSON（父记录，全表仅79条有值）
--
-- 增量：主键是飞书的 record_id（稳定不变）。同步按 record_id upsert，
-- 内容没变的行不写、只更新同步时间；默认只拉视图那一批（当周约370条），
-- 不是每次拉全表。详见 backend/services/feishu_bad_transaction_sync_service.py。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ods_feishu_bad_transaction_listing (
  record_id            VARCHAR(32)  NOT NULL COMMENT '飞书记录ID，表内唯一且稳定，作为增量更新的主键',
  reg_date             DATE         NULL     COMMENT '飞书字段「登记日期」；批次标识，每周三一批。实测全表有419条为空',
  shop                 VARCHAR(128) NULL     COMMENT '飞书字段「店铺」',
  evaluate_date        VARCHAR(32)  NULL     COMMENT '飞书字段「评估日期」；飞书侧是文本不是日期，原样存',
  item_id              VARCHAR(32)  NULL     COMMENT '飞书字段「物品编号」；eBay ItemID',
  title                VARCHAR(255) NULL     COMMENT '飞书字段「刊登标题」；实测最长80字符',
  listing_status       VARCHAR(8)   NULL     COMMENT '飞书字段「刊登状态：Y=在线，N=已下线」；单选',
  sku                  VARCHAR(64)  NULL     COMMENT '飞书字段「SKU」',
  total_amount         VARCHAR(32)  NULL     COMMENT '飞书字段「总交易额」；飞书侧是文本，算数时CAST',
  total_qty            VARCHAR(16)  NULL     COMMENT '飞书字段「总交易量」；飞书侧是文本',
  defect_qty           VARCHAR(16)  NULL     COMMENT '飞书字段「不良交易量」；飞书侧是文本',
  inr_qty              VARCHAR(16)  NULL     COMMENT '飞书字段「物品未收到纠纷数量」；飞书侧是文本',
  snad_qty             VARCHAR(16)  NULL     COMMENT '飞书字段「物品与描述不符退货数量」；飞书侧是文本',
  neutral_negative_qty VARCHAR(16)  NULL     COMMENT '飞书字段「中差评数量」；飞书侧是文本',
  low_dsr_qty          VARCHAR(16)  NULL     COMMENT '飞书字段「物品描述评分低分数量」；飞书侧是文本',
  oos_cancel_qty       VARCHAR(16)  NULL     COMMENT '飞书字段「因缺货而取消的交易数量」；飞书侧是文本',
  defect_rate          VARCHAR(16)  NULL     COMMENT '飞书字段「不良交易率」；飞书侧是文本，算数时CAST',
  parent_json          JSON         NULL     COMMENT '飞书字段「父记录」，关联类型原样存；全表仅79条有值',
  spare_date_1         DATE         NULL     COMMENT '飞书字段「字段 1」；日期型占位列，全表仅4条有值',
  spare_date_2         DATE         NULL     COMMENT '飞书字段「字段 2」；日期型占位列，全表仅4条有值',
  spare_date_3         DATE         NULL     COMMENT '飞书字段「字段 3」；日期型占位列，全表仅4条有值',
  spare_text_4         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 4」；文本占位列，全表仅2条有值',
  spare_text_5         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 5」；文本占位列，全表仅2条有值',
  spare_text_6         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 6」；文本占位列，全表仅1条有值',
  spare_text_7         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 7」；文本占位列，全表仅1条有值',
  spare_text_8         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 8」；文本占位列，全表仅4条有值',
  feishu_created_at    DATETIME     NULL     COMMENT '飞书记录创建时间，取自接口automatic_fields，北京时间',
  feishu_updated_at    DATETIME     NULL     COMMENT '飞书记录最后更新时间，同上；表里没有可见的更新时间字段，判断有没有变只能靠它',
  content_hash         CHAR(64)     NOT NULL COMMENT '业务字段的SHA256指纹；与库里一致就跳过写入，用来区分"更新"和"没变"',
  first_synced_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '本行首次同步进来的时间',
  last_synced_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最后一次被同步看到的时间；即使内容没变也会更新',
  last_changed_at      DATETIME     NULL     COMMENT '最后一次内容真正发生变化的时间；内容没变时不动',
  PRIMARY KEY (record_id),
  -- 按批次查是主要用法：某一周的不良交易刊登。
  KEY idx_reg_date (reg_date),
  KEY idx_shop_reg (shop, reg_date),
  KEY idx_sku (sku),
  KEY idx_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='飞书多维表格「不良交易刊登」本地副本；按飞书record_id增量upsert，每周三更新一批';


-- 同步任务登记。cron 每周三 09:30（北京时间），业务方周三更新完之后再拉。
INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
VALUES('feishu_bad_transaction_sync','飞书不良交易刊登每周同步','0 30 9 ? * WED',1,
 '每周三北京时间09:30。默认只拉飞书视图vewohlM1T4那一批（当周约370条），'
 '按record_id增量upsert，内容未变的行不写。全量回填用 scripts/feishu_bad_transaction_backfill.py。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name),cron_expression=VALUES(cron_expression),
                        description=VALUES(description);


-- ============================================================================
-- 只读验证（首次同步之后执行）
-- ============================================================================

-- 总量与批次分布；预期每个登记日期 350~490 条
SELECT COUNT(*) AS 总行数, COUNT(DISTINCT reg_date) AS 批次数,
       MIN(reg_date) AS 最早批次, MAX(reg_date) AS 最晚批次,
       SUM(reg_date IS NULL) AS 无登记日期的行
FROM ods_feishu_bad_transaction_listing;

SELECT reg_date AS 登记日期, COUNT(*) AS 行数, COUNT(DISTINCT shop) AS 店铺数,
       MAX(last_synced_at) AS 最后同步
FROM ods_feishu_bad_transaction_listing
GROUP BY reg_date ORDER BY reg_date DESC LIMIT 10;

-- 主键没重复（应无结果）
SELECT record_id, COUNT(*) FROM ods_feishu_bad_transaction_listing
GROUP BY record_id HAVING COUNT(*) > 1 LIMIT 5;

-- 文本列里存的数字能不能算：抽最新一批看不良交易率分布
SELECT reg_date AS 登记日期, COUNT(*) AS 行数,
       ROUND(AVG(CAST(NULLIF(defect_rate,'') AS DECIMAL(10,6))),4) AS 平均不良交易率,
       SUM(CAST(NULLIF(defect_qty,'') AS UNSIGNED)) AS 不良交易量合计
FROM ods_feishu_bad_transaction_listing
WHERE reg_date = (SELECT MAX(reg_date) FROM ods_feishu_bad_transaction_listing)
GROUP BY reg_date;
