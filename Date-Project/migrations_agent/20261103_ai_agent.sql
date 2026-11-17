-- AI 数据助手：后台运行记录、工具调用日志、用户长期记忆。目标库：AI 助手专用库（AI_AGENT_DATABASE，默认 jmh_ai_agent）。

CREATE TABLE IF NOT EXISTS ai_agent_run (
    run_id CHAR(36) NOT NULL COMMENT '运行ID（UUID）',
    conversation_uuid CHAR(36) NOT NULL COMMENT '所属会话UUID，对应 ai_conversations.conversation_uuid',
    erp_user_id BIGINT NOT NULL COMMENT '发起人ERP用户ID',
    erp_username VARCHAR(100) NOT NULL COMMENT '发起人ERP用户名',
    question TEXT NOT NULL COMMENT '用户提问原文',
    status VARCHAR(16) NOT NULL COMMENT '状态：running 执行中 / completed 完成 / failed 失败',
    plan_json JSON NULL COMMENT '模型规划的步骤清单及各步状态',
    results_json JSON NULL COMMENT '各工具返回的表格结果（截断后，用于页面展示）',
    thinking_json JSON NULL COMMENT '思考模式下每轮模型的思考过程（按轮次保存，单轮截断）',
    answer MEDIUMTEXT NULL COMMENT '最终回答',
    error_message VARCHAR(1000) NULL COMMENT '失败原因',
    rounds INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '模型调用轮次',
    tool_calls INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '工具调用次数',
    prompt_tokens INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计输入Token',
    completion_tokens INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计输出Token',
    model VARCHAR(100) NULL COMMENT '使用的模型',
    request_id VARCHAR(100) NULL COMMENT '请求ID，用于串联Java/Python日志',
    started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '开始时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后更新时间',
    completed_at DATETIME(3) NULL COMMENT '结束时间',
    PRIMARY KEY (run_id),
    KEY idx_ai_agent_run_user_started (erp_user_id, started_at),
    KEY idx_ai_agent_run_conversation (conversation_uuid, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI数据助手运行记录';

CREATE TABLE IF NOT EXISTS ai_agent_step (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    run_id CHAR(36) NOT NULL COMMENT '运行ID，对应 ai_agent_run.run_id',
    seq INT UNSIGNED NOT NULL COMMENT '运行内调用序号',
    round_no INT UNSIGNED NOT NULL COMMENT '第几轮模型调用发起',
    tool_name VARCHAR(64) NOT NULL COMMENT '工具名称',
    arguments_json JSON NULL COMMENT '经校验的调用参数（不含密钥）',
    status VARCHAR(16) NOT NULL COMMENT '状态：completed 成功 / failed 失败 / denied 无权限 / invalid 参数不合法',
    row_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '返回明细行数',
    duration_ms INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '耗时（毫秒）',
    error_message VARCHAR(1000) NULL COMMENT '失败原因',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_agent_step_run_seq (run_id, seq),
    KEY idx_ai_agent_step_tool (tool_name, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI数据助手工具调用日志';

CREATE TABLE IF NOT EXISTS ai_user_memory (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    erp_user_id BIGINT NOT NULL COMMENT '记忆所属ERP用户ID',
    category VARCHAR(32) NOT NULL DEFAULT 'preference' COMMENT '类别：preference 偏好 / fact 业务事实 / instruction 工作习惯',
    content VARCHAR(500) NOT NULL COMMENT '记忆内容',
    source_run_id CHAR(36) NULL COMMENT '产生该记忆的运行ID',
    deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除：1已删除',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ai_user_memory_user (erp_user_id, deleted, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI数据助手用户长期记忆（偏好与业务事实，不影响权限）';
