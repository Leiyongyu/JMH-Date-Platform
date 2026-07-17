"""应用日志配置。

当前使用标准库 logging（兼容 Python 3.14 预发布版）。
后续 Python 版本稳定后可升级为 structlog。
"""
import logging
import sys

from core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = (
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d - %(message)s"
        if settings.log_format == "console"
        else '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","file":"%(filename)s:%(lineno)d","message":"%(message)s"}'
    )

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # 降低第三方库日志噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "logging_initialized level=%s format=%s", settings.log_level, settings.log_format
    )
