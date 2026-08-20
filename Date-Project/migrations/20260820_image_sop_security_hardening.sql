-- 目标库：Date-Project（Python数据库）。
-- 图片SOP草稿按ERP用户隔离；已有历史草稿归入owner_user_id=0，不再被普通用户恢复。

SET @owner_user_id_exists := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema=DATABASE()
      AND table_name='image_sop_draft'
      AND column_name='owner_user_id'
);
SET @owner_user_id_sql := IF(
    @owner_user_id_exists=0,
    'ALTER TABLE image_sop_draft ADD COLUMN owner_user_id BIGINT NOT NULL DEFAULT 0 COMMENT ''ERP用户ID，草稿数据隔离依据'' AFTER id',
    'SELECT 1'
);
PREPARE owner_user_id_stmt FROM @owner_user_id_sql;
EXECUTE owner_user_id_stmt;
DEALLOCATE PREPARE owner_user_id_stmt;

SET @owner_username_exists := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema=DATABASE()
      AND table_name='image_sop_draft'
      AND column_name='owner_username'
);
SET @owner_username_sql := IF(
    @owner_username_exists=0,
    'ALTER TABLE image_sop_draft ADD COLUMN owner_username VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''ERP登录账号，便于审计'' AFTER owner_user_id',
    'SELECT 1'
);
PREPARE owner_username_stmt FROM @owner_username_sql;
EXECUTE owner_username_stmt;
DEALLOCATE PREPARE owner_username_stmt;

SET @owner_index_exists := (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema=DATABASE()
      AND table_name='image_sop_draft'
      AND index_name='idx_image_sop_draft_owner'
);
SET @owner_index_sql := IF(
    @owner_index_exists=0,
    'CREATE INDEX idx_image_sop_draft_owner ON image_sop_draft(owner_user_id,created_at)',
    'SELECT 1'
);
PREPARE owner_index_stmt FROM @owner_index_sql;
EXECUTE owner_index_stmt;
DEALLOCATE PREPARE owner_index_stmt;
