-- AI 助手会话与消息。目标库：AI 助手专用库（AI_AGENT_DATABASE，默认 jmh_ai_agent）。
-- 结构与业务库原 ai_conversations / ai_messages 一致，补齐字段中文注释；
-- 存量聊天记录用 deploy/db/move_ai_history_to_agent_db.sql 一次性复制过来。

CREATE TABLE IF NOT EXISTS ai_conversations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    conversation_uuid CHAR(36) NOT NULL COMMENT '会话UUID，对外使用的会话标识',
    erp_user_id BIGINT NOT NULL COMMENT '会话所属ERP用户ID',
    erp_username VARCHAR(100) NOT NULL COMMENT '会话所属ERP用户名',
    title VARCHAR(200) NOT NULL DEFAULT '新对话' COMMENT '会话标题（取首条提问）',
    message_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '消息条数',
    last_message_preview VARCHAR(500) NULL COMMENT '最近一条消息预览',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_conversations_uuid (conversation_uuid),
    KEY idx_ai_conversations_user_updated (erp_user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI助手用户会话';

CREATE TABLE IF NOT EXISTS ai_messages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    conversation_id BIGINT UNSIGNED NOT NULL COMMENT '所属会话ID，对应 ai_conversations.id',
    role VARCHAR(16) NOT NULL COMMENT '角色：user 用户 / assistant 助手',
    content MEDIUMTEXT NOT NULL COMMENT '消息内容',
    is_error TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为错误提示：1是',
    request_id VARCHAR(100) NULL COMMENT '请求ID，用于串联Java/Python日志',
    model VARCHAR(100) NULL COMMENT '生成该回答的模型',
    prompt_tokens INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '输入Token数',
    completion_tokens INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '输出Token数',
    total_tokens INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '总Token数',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_ai_messages_conversation_created (conversation_id, created_at),
    KEY idx_ai_messages_request (request_id),
    CONSTRAINT fk_ai_messages_conversation
        FOREIGN KEY (conversation_id) REFERENCES ai_conversations (id)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI助手会话消息';
