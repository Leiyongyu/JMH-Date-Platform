ALTER TABLE scheduler_task_run
    ADD COLUMN sync_batch_id VARCHAR(64) NULL COMMENT 'ODS同步批次ID' AFTER source_rows,
    ADD COLUMN extract_rows INT NOT NULL DEFAULT 0 COMMENT '领星抽取行数' AFTER sync_batch_id,
    ADD COLUMN ods_rows INT NOT NULL DEFAULT 0 COMMENT 'ODS追加行数' AFTER extract_rows,
    ADD COLUMN deleted_rows INT NOT NULL DEFAULT 0 COMMENT '整月替换删除行数' AFTER updated_rows,
    ADD COLUMN skipped_rows INT NOT NULL DEFAULT 0 COMMENT '无效或重复跳过行数' AFTER deleted_rows,
    ADD COLUMN amz_ranking_rows INT NOT NULL DEFAULT 0 COMMENT 'AMZ排名行数' AFTER skipped_rows,
    ADD COLUMN combined_ranking_rows INT NOT NULL DEFAULT 0 COMMENT '综合排名行数' AFTER amz_ranking_rows,
    ADD COLUMN etl_stage VARCHAR(32) NULL COMMENT '当前或失败阶段' AFTER combined_ranking_rows;
