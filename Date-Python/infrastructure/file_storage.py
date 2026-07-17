"""文件上传/存储/校验"""
import hashlib
import os
from datetime import datetime
from pathlib import Path

from core.config import get_settings
from core.errors import FileError, PayloadTooLargeError


def _upload_dir() -> Path:
    path = Path(get_settings().upload_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def save_upload_stream(filename: str, file_obj, sub_dir: str = "") -> tuple[str, str, int]:
    """保存上传文件流。
    返回 (stored_path, original_name, file_size)
    """
    settings = get_settings()
    base = _upload_dir()
    if sub_dir:
        base = base / sub_dir
    base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = filename.replace("\\", "_").replace("/", "_")
    stored_name = f"{timestamp}_{safe_name}"
    stored_path = str(base / stored_name)

    file_size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    with open(stored_path, "wb") as out:
        while True:
            chunk = file_obj.read(8192)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > max_bytes:
                try:
                    os.remove(stored_path)
                except OSError:
                    pass
                raise PayloadTooLargeError(
                    f"上传文件不能超过 {settings.max_upload_mb} MB"
                )
            out.write(chunk)

    return stored_path, filename, file_size


def compute_sha256(file_path: str) -> str:
    """计算文件的 SHA-256 摘要"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def idempotency_key(file_sha256: str, task_type: str) -> str:
    """生成任务幂等键"""
    raw = f"{file_sha256}|{task_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
