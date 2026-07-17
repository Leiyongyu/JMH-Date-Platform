"""应用配置 — 纯标准库，无外部依赖。

环境变量前缀: JMH_
.env 文件手动解析以兼容 Python 3.14 预发布版。
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """手动解析 .env 文件并注入 os.environ（仅在变量不存在时设置）。"""
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# 加载项目根目录下的 .env
_env_file = Path(__file__).resolve().parent.parent / ".env"
_load_dotenv(_env_file)


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"缺少必要的环境变量: {key}，请在 .env 文件或系统环境变量中设置"
        )
    return value


class Settings:
    """应用配置单例。通过 JMH_ 前缀的环境变量注入。"""

    # ── 数据库 ──
    db_host: str = os.environ.get("JMH_DB_HOST", "localhost")
    db_port: int = int(os.environ.get("JMH_DB_PORT", "3306"))
    db_user: str = os.environ.get("JMH_DB_USER", "root")
    db_password: str = _require("JMH_DB_PASSWORD")
    db_name: str = os.environ.get("JMH_DB_NAME", "export_tax_refund")
    db_pool_size: int = int(os.environ.get("JMH_DB_POOL_SIZE", "5"))
    db_pool_overflow: int = int(os.environ.get("JMH_DB_POOL_OVERFLOW", "10"))

    jmh_db_host: str = os.environ.get("JMH_JMH_DB_HOST", "localhost")
    jmh_db_port: int = int(os.environ.get("JMH_JMH_DB_PORT", "3306"))
    jmh_db_user: str = os.environ.get("JMH_JMH_DB_USER", "root")
    jmh_db_password: str = _require("JMH_JMH_DB_PASSWORD")
    jmh_db_name: str = os.environ.get("JMH_JMH_DB_NAME", "jmh_data_platform")

    # ── 文件上传 ──
    upload_dir: str = os.environ.get("JMH_UPLOAD_DIR", "uploads")
    max_upload_mb: int = int(os.environ.get("JMH_MAX_UPLOAD_MB", "50"))

    # ── 任务 ──
    task_max_workers: int = int(os.environ.get("JMH_TASK_MAX_WORKERS", "4"))

    # ── 日志 ──
    log_level: str = os.environ.get("JMH_LOG_LEVEL", "INFO")
    log_format: str = os.environ.get("JMH_LOG_FORMAT", "console")

    # ── 金额 ──
    amount_tolerance: float = float(os.environ.get("JMH_AMOUNT_TOLERANCE", "0.02"))
    default_refund_rate: float = float(os.environ.get("JMH_DEFAULT_REFUND_RATE", "0.13"))


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
