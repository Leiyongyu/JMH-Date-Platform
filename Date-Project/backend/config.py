from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# 这些前缀的配置以本项目 .env 为准，即使系统里存在同名环境变量（例如其他项目在 Windows 用户
# 环境变量里设置了 DASHSCOPE_API_KEY）。其余配置仍是「已有环境变量优先」，部署方式不变。
DOTENV_OVERRIDE_PREFIXES = ("DASHSCOPE_", "DEEPSEEK_", "AI_AGENT_", "LINGXING_MCP_")


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        name = key.strip()
        if name.startswith(DOTENV_OVERRIDE_PREFIXES):
            os.environ[name] = normalized_value
        else:
            os.environ.setdefault(name, normalized_value)


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "Date-Project")
    # 迁移专用账号：持有 DDL 权限，只在执行 db-migrate 时使用；未配置时沿用应用账号。
    mysql_migrator_user: str = os.getenv("MYSQL_MIGRATOR_USER", "")
    mysql_migrator_password: str = os.getenv("MYSQL_MIGRATOR_PASSWORD", "")
    # 启动时是否自动执行历史建表脚本。生产保持 false，结构变更统一走 db-migrate。
    database_auto_migrate: bool = _env_bool("DATABASE_AUTO_MIGRATE", False)
    erp_sql_dir: str = os.getenv("ERP_SQL_DIR") or str(
        PROJECT_ROOT.parent / "RuoYi-Vue-springboot3" / "sql"
    )
    template_dir: str = os.getenv(
        "TEMPLATE_DIR",
        r"D:\JMH\出口业务收汇情况表\外汇退税\数据源\模版",
    )
    export_output_dir: str = os.getenv(
        "EXPORT_OUTPUT_DIR", str(PROJECT_ROOT / "exports")
    )
    sku_validation_file: str = os.getenv(
        "SKU_VALIDATION_FILE",
        r"D:\JMH\外汇退税\数据\SKU核对效验.xlsx",
    )
    payer_name: str = os.getenv("PAYER_NAME", "Hong Kong Cammy Yeson Limited")
    lingxing_endpoint: str = os.getenv(
        "LINGXING_ENDPOINT",
        os.getenv("LINGXING_HOST", "https://api.lingxing.com"),
    )
    lingxing_app_id: str = os.getenv("LINGXING_APP_ID", "")
    lingxing_app_secret: str = os.getenv("LINGXING_APP_SECRET", "")
    lingxing_token_refresh_before_sec: int = int(
        os.getenv("LINGXING_TOKEN_REFRESH_BEFORE_SEC", "300")
    )
    lingxing_request_timeout_sec: int = int(
        os.getenv("LINGXING_REQUEST_TIMEOUT_SEC", "30")
    )
    lingxing_max_retries: int = int(os.getenv("LINGXING_MAX_RETRIES", "3"))
    lingxing_page_size: int = int(os.getenv("LINGXING_PAGE_SIZE", "100"))
    lingxing_sign_key: str = os.getenv("LINGXING_SIGN_KEY", "app_id")
    goodcang_endpoint: str = os.getenv("GOODCANG_ENDPOINT", "https://oms.goodcang.net/public_open")
    goodcang_app_token: str = field(default_factory=lambda: os.getenv("GOODCANG_APP_TOKEN", ""), repr=False)
    goodcang_app_key: str = field(default_factory=lambda: os.getenv("GOODCANG_APP_KEY", ""), repr=False)
    goodcang_request_timeout_sec: int = int(os.getenv("GOODCANG_REQUEST_TIMEOUT_SEC", "30"))
    goodcang_min_request_interval_sec: float = float(os.getenv("GOODCANG_MIN_REQUEST_INTERVAL_SEC", "1.2"))
    goodcang_max_retries: int = int(os.getenv("GOODCANG_MAX_RETRIES", "3"))
    # 飞书开放平台（多维表格）。自建应用用 app_id/app_secret 换 tenant_access_token。
    # 国际版租户把 FEISHU_ENDPOINT 改成 https://open.larksuite.com。
    feishu_endpoint: str = os.getenv("FEISHU_ENDPOINT", "https://open.feishu.cn")
    feishu_app_id: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""), repr=False)
    feishu_app_secret: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""), repr=False)
    # 提前多少秒把令牌当作过期，避免卡在边界上用到刚失效的令牌。
    feishu_token_refresh_before_sec: int = int(os.getenv("FEISHU_TOKEN_REFRESH_BEFORE_SEC", "300"))
    feishu_request_timeout_sec: int = int(os.getenv("FEISHU_REQUEST_TIMEOUT_SEC", "30"))
    feishu_min_request_interval_sec: float = float(os.getenv("FEISHU_MIN_REQUEST_INTERVAL_SEC", "0.2"))
    feishu_max_retries: int = int(os.getenv("FEISHU_MAX_RETRIES", "3"))
    # 多维表格「查询记录」单页上限就是500。
    feishu_page_size: int = int(os.getenv("FEISHU_PAGE_SIZE", "500"))
    # 卖家级别表：取自多维表格地址 /base/<app_token>?table=<table_id>&view=<view_id>
    feishu_seller_level_app_token: str = os.getenv("FEISHU_SELLER_LEVEL_APP_TOKEN", "")
    feishu_seller_level_table_id: str = os.getenv("FEISHU_SELLER_LEVEL_TABLE_ID", "")
    feishu_seller_level_view_id: str = os.getenv("FEISHU_SELLER_LEVEL_VIEW_ID", "")
    # 不良交易刊登表。视图筛的是当周那一批，增量同步只拉它；全量回填才不带视图。
    # 负责人映射表（飞书多维表格，6 张数据表与「负责人划分.xlsx」的 6 个 Sheet 同名同结构）
    feishu_owner_rule_app_token: str = os.getenv("FEISHU_OWNER_RULE_APP_TOKEN", "Y9xEbDuoVauS9MseULQcL48FnQk")
    feishu_bad_transaction_app_token: str = os.getenv(
        "FEISHU_BAD_TRANSACTION_APP_TOKEN", "UjvXbOPJTalrRKsmZKpcUjQ5nEe")
    feishu_bad_transaction_table_id: str = os.getenv(
        "FEISHU_BAD_TRANSACTION_TABLE_ID", "tbl4j735kfsuqcHl")
    feishu_bad_transaction_view_id: str = os.getenv(
        "FEISHU_BAD_TRANSACTION_VIEW_ID", "vewohlM1T4")
    # 汽配订单（MACH数据系统V2，开了高级权限：应用「店铺巡查」须在角色里授权这张表）。
    # 整表同步，不用视图——视图的筛选条件会被人改掉。
    feishu_auto_parts_order_app_token: str = os.getenv(
        "FEISHU_AUTO_PARTS_ORDER_APP_TOKEN", "JPxQb2riHagsafsX7QVc6rSjn8f")
    feishu_auto_parts_order_table_id: str = os.getenv(
        "FEISHU_AUTO_PARTS_ORDER_TABLE_ID", "tblXybb1irZdGxGG")
    shop_source_database: str = os.getenv("SHOP_SOURCE_DATABASE", "jmh_data_platform")
    # eBay 补货 2.0 的规则/复核/销售类型表只由 Python 读写。留空时仍在 ERP 库（历史位置）；
    # 按 deploy/db/move_ebay_replenishment_rules.sql 迁到本库后设为 Date-Project。
    ebay_replenishment_rule_database: str = os.getenv("EBAY_REPLENISHMENT_RULE_DATABASE", "")
    python_internal_api_token: str = os.getenv(
        "PYTHON_INTERNAL_API_TOKEN",
        os.getenv("PYTHON_PERFORMANCE_INTERNAL_TOKEN", ""),
    )
    python_performance_internal_token: str = python_internal_api_token
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    ).rstrip("/")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    deepseek_request_timeout_sec: int = int(
        os.getenv("DEEPSEEK_REQUEST_TIMEOUT_SEC", "180")
    )
    deepseek_max_tokens: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "2048"))
    deepseek_thinking_enabled: bool = _env_bool(
        "DEEPSEEK_THINKING_ENABLED", False
    )
    # 数据助手（工具调用）的执行预算：超过任一上限即停止调用工具、基于已有结果作答。
    # 数据助手的模型提供方：dashscope=阿里云百炼（测试阶段），deepseek=DeepSeek（上线）。只改这一项即可切换。
    ai_agent_provider: str = (os.getenv("AI_AGENT_PROVIDER") or "deepseek").strip().lower()
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    # 百炼 OpenAI 兼容地址；使用业务空间专属地址时改为 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
    dashscope_base_url: str = os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = os.getenv("DASHSCOPE_MODEL") or "qwen3.7-max-2026-06-08"
    # AI 助手专用库：会话、消息、运行记录、工具调用日志、用户记忆都放这里，与业务数据分开。
    ai_agent_database: str = os.getenv("AI_AGENT_DATABASE") or "jmh_ai_agent"
    # 思考模式：模型先输出思考过程再调用工具或作答，思考内容逐轮保存并在助手面板展示。
    ai_agent_thinking_enabled: bool = _env_bool("AI_AGENT_THINKING_ENABLED", True)
    # 思考内容计入输出 token，助手单独使用更大的上限，避免思考过长导致回答被截断。
    ai_agent_max_tokens: int = int(os.getenv("AI_AGENT_MAX_TOKENS", "8192"))
    # auto=简单问题（寒暄、无数据意图的短句）关闭思考，可配轻量模型；on=始终思考；off=始终关闭
    ai_agent_thinking_mode: str = (os.getenv("AI_AGENT_THINKING_MODE") or "auto").strip().lower()
    ai_agent_simple_model: str = os.getenv("AI_AGENT_SIMPLE_MODEL", "").strip()
    # 流式接收模型输出：进行中的思考与回答实时写入运行记录，前端轮询即可逐段显示
    ai_agent_stream: bool = _env_bool("AI_AGENT_STREAM", True)
    # 发给模型的上下文超过该字符数时，把较早轮次的工具结果压缩为汇总
    ai_agent_context_chars: int = int(os.getenv("AI_AGENT_CONTEXT_CHARS", "60000"))
    # 领星官方 MCP：助手里勾选「领星MCP」时才使用；密钥在领星【AI助手】-【MCP】-【复制密钥】获取，只放 .env
    lingxing_mcp_url: str = (os.getenv("LINGXING_MCP_URL")
                             or "https://openmcp.lingxing.com/mcp-servers/lingxing-mcp").strip()
    lingxing_mcp_key: str = os.getenv("LINGXING_MCP_KEY", "")
    ai_agent_max_rounds: int = int(os.getenv("AI_AGENT_MAX_ROUNDS", "8"))
    ai_agent_max_tool_calls: int = int(os.getenv("AI_AGENT_MAX_TOOL_CALLS", "16"))
    ai_agent_timeout_sec: int = int(os.getenv("AI_AGENT_TIMEOUT_SEC", "300"))
    ai_agent_tool_timeout_sec: int = int(os.getenv("AI_AGENT_TOOL_TIMEOUT_SEC", "90"))
    ai_agent_parallel_tools: int = int(os.getenv("AI_AGENT_PARALLEL_TOOLS", "4"))
    deepseek_system_prompt: str = os.getenv(
        "DEEPSEEK_SYSTEM_PROMPT",
        (
            "你是JMH数据平台的内部AI助手。请使用简洁、准确的中文回答。"
            "不得编造ERP业务数据；当前未提供业务查询工具时，应明确说明无法直接读取系统数据。"
            "不得声称已经执行查询、导出、修改或删除操作。"
            "涉及数据修改、权限、密钥或其他高风险操作时，必须提醒用户由人工确认。"
        ),
    )


settings = Settings()
