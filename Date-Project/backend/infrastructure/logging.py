from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from backend.config import PROJECT_ROOT
from backend.infrastructure.request_context import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s - %(message)s"
    )
    request_filter = RequestIdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.addFilter(request_filter)
    console_handler.setFormatter(formatter)

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "date-project-api.log",
        maxBytes=20 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.addFilter(request_filter)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(level)
