-- 目标库：Date-Project（Python 业务库）。扩容本地仓个人归属来源字段。
-- 仅手工执行一次表结构扩容；不修改现有记录的字段值。
ALTER TABLE `dwd_inventory_report_local_detail`
    MODIFY COLUMN `principal_match_source` VARCHAR(64) NOT NULL
    DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源';
