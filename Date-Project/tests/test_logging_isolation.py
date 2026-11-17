"""pytest 运行时不能把测试日志写进正式服务日志 logs/date-project-api.log。"""
import logging
import uuid
from logging.handlers import RotatingFileHandler

from backend.config import PROJECT_ROOT
from backend.infrastructure import logging as app_logging


def _file_handlers():
    return [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.FileHandler)
    ]


def test_conftest_disables_file_logging():
    assert app_logging.file_logging_enabled() is False


def test_configure_logging_skips_file_handler_and_keeps_service_log_untouched():
    log_file = PROJECT_ROOT / "logs" / app_logging.LOG_FILE_NAME
    offset = log_file.stat().st_size if log_file.exists() else 0
    marker = f"isolation-check-{uuid.uuid4().hex}"

    app_logging.configure_logging()
    logging.getLogger("tests.logging-isolation").error(marker)
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert _file_handlers() == []
    # 本机 8010 服务可能同时在写这个文件，所以只检查新增部分里没有本测试的日志。
    appended = b""
    if log_file.exists():
        with log_file.open("rb") as fh:
            fh.seek(min(offset, log_file.stat().st_size))
            appended = fh.read()
    assert marker.encode() not in appended


def test_importing_main_does_not_attach_service_log_handler():
    import backend.main  # noqa: F401  导入即调用 create_app() -> configure_logging()

    app_logging.configure_logging()
    assert _file_handlers() == []


def test_file_logging_still_enabled_by_default(monkeypatch, tmp_path):
    """正式服务没设环境变量时，仍然写轮转日志文件（行为不变）。"""
    monkeypatch.delenv(app_logging.FILE_LOGGING_ENV, raising=False)
    monkeypatch.setattr(app_logging, "PROJECT_ROOT", tmp_path)
    root_logger = logging.getLogger()
    saved_handlers = list(root_logger.handlers)
    saved_level = root_logger.level
    try:
        app_logging.configure_logging()
        handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]
        assert len(handlers) == 1
        assert handlers[0].baseFilename == str(tmp_path / "logs" / app_logging.LOG_FILE_NAME)
        assert handlers[0].maxBytes == 20 * 1024 * 1024
        assert handlers[0].backupCount == 10
    finally:
        for handler in root_logger.handlers:
            if handler not in saved_handlers:
                handler.close()
        root_logger.handlers[:] = saved_handlers
        root_logger.setLevel(saved_level)
