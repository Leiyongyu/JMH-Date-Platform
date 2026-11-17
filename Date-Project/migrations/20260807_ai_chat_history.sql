-- AI助手对话持久化。目标库：Python服务 MYSQL_DATABASE（默认 Date-Project）。

CREATE TABLE IF NOT EXISTS ai_conversations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    conversation_uuid CHAR(36) NOT NULL,
    erp_user_id BIGINT NOT NULL,
    erp_username VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '新对话',
    message_count INT UNSIGNED NOT NULL DEFAULT 0,
    last_message_preview VARCHAR(500) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_conversations_uuid (conversation_uuid),
    KEY idx_ai_conversations_user_updated (erp_user_id,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI助手用户会话';

CREATE TABLE IF NOT EXISTS ai_messages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    conversation_id BIGINT UNSIGNED NOT NULL,
    role VARCHAR(16) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    is_error TINYINT(1) NOT NULL DEFAULT 0,
    request_id VARCHAR(100) NULL,
    model VARCHAR(100) NULL,
    prompt_tokens INT UNSIGNED NOT NULL DEFAULT 0,
    completion_tokens INT UNSIGNED NOT NULL DEFAULT 0,
    total_tokens INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_ai_messages_conversation_created (conversation_id,created_at),
    KEY idx_ai_messages_request (request_id),
    CONSTRAINT fk_ai_messages_conversation
        FOREIGN KEY (conversation_id) REFERENCES ai_conversations (id)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI助手会话消息';
