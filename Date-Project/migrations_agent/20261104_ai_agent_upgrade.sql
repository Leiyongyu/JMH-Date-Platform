-- AI 数据助手升级：数字核对结果、运行来源、记忆确认状态、会话滚动摘要、用户反馈、定时简报。
-- 目标库：AI 助手专用库（AI_AGENT_DATABASE，默认 jmh_ai_agent）。只新增字段和表，不修改已有数据。

ALTER TABLE ai_agent_run
    ADD COLUMN verification_json JSON NULL COMMENT '回答数字核对结果：status passed 通过 / warned 有不一致 / skipped 未查数据，unmatched 为对不上的数字' AFTER thinking_json,
    ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'chat' COMMENT '发起来源：chat 对话提问 / brief 定时简报' AFTER request_id;

ALTER TABLE ai_user_memory
    ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态：active 已生效 / pending 助手推断、待用户确认' AFTER content;

ALTER TABLE ai_conversations
    ADD COLUMN summary TEXT NULL COMMENT '较早消息的滚动摘要（最近若干条原文另行带给模型）' AFTER last_message_preview,
    ADD COLUMN summary_message_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '摘要已覆盖的消息条数（按时间顺序从第一条算起）' AFTER summary;

CREATE TABLE IF NOT EXISTS ai_agent_feedback (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    run_id CHAR(36) NOT NULL COMMENT '运行ID，对应 ai_agent_run.run_id',
    erp_user_id BIGINT NOT NULL COMMENT '评价人ERP用户ID（只能评价自己的运行）',
    rating TINYINT NOT NULL COMMENT '评价：1 有帮助 / -1 没帮助',
    comment VARCHAR(500) NULL COMMENT '用户补充的意见',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_agent_feedback_run_user (run_id, erp_user_id),
    KEY idx_ai_agent_feedback_rating (rating, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI数据助手回答反馈';

CREATE TABLE IF NOT EXISTS ai_scheduled_brief (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    erp_user_id BIGINT NOT NULL COMMENT '所属ERP用户ID（执行时按该用户当前权限查询）',
    erp_username VARCHAR(100) NOT NULL COMMENT '所属ERP用户名',
    title VARCHAR(60) NOT NULL COMMENT '简报名称',
    question VARCHAR(1000) NOT NULL COMMENT '每次执行时向助手提的问题',
    frequency VARCHAR(16) NOT NULL COMMENT '周期：daily 每天 / weekly 每周 / monthly 每月',
    weekday TINYINT UNSIGNED NULL COMMENT '每周执行的星期（1=周一 … 7=周日），仅 weekly 使用',
    month_day TINYINT UNSIGNED NULL COMMENT '每月执行的日期（1~28），仅 monthly 使用',
    run_hour TINYINT UNSIGNED NOT NULL DEFAULT 9 COMMENT '执行整点（北京时间 0~23）',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用：1启用 0停用',
    conversation_uuid CHAR(36) NULL COMMENT '简报结果写入的会话UUID',
    last_run_id CHAR(36) NULL COMMENT '最近一次运行ID',
    last_run_at DATETIME NULL COMMENT '最近一次执行时间（北京时间）',
    next_run_at DATETIME NULL COMMENT '下次执行时间（北京时间），停用时为空',
    deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除：1已删除',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ai_scheduled_brief_user (erp_user_id, deleted),
    KEY idx_ai_scheduled_brief_due (enabled, deleted, next_run_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI数据助手定时简报';
