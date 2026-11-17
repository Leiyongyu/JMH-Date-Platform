from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from backend.config import PROJECT_ROOT
from backend.infrastructure.request_context import get_request_id

# 设为 "0" 时不写 logs/date-project-api.log，只输出到控制台。
# tests/conftest.py 会设置它，避免 pytest 的测试日志混进正式服务日志。
FILE_LOGGING_ENV = "DATE_PROJECT_FILE_LOGGING"
LOG_FILE_NAME = "date-project-api.log"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def file_logging_enabled() -> bool:
    return os.getenv(FILE_LOGGING_ENV, "1").strip() != "0"


def configure_logging(level: int = logging.INFO) -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s - %(message)s"
    )
    request_filter = RequestIdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.addFilter(request_filter)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    if file_logging_enabled():
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / LOG_FILE_NAME,
            maxBytes=20 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.addFilter(request_filter)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(level)
