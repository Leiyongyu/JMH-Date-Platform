"""Amazon主图批量上传子应用，挂载到 Date-Project 的 8010 服务。"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import os
import queue
import re
import secrets
import threading
import time
import winreg
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.infrastructure.request_context import get_request_id

from . import config_loader as cl
from . import repository
from .excel_reader import read_skus
from .image_loader import get_sku_images
from .upload_app import UploadApp
from .ziniao_client import ZiniaoClient


MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent.parent
RUNTIME_DIR = Path(
    os.getenv(
        "AMAZON_IMAGE_UPLOAD_OUTPUT_DIR",
        str(PROJECT_ROOT / "outputs" / "amazon_image_upload"),
    )
).expanduser().resolve()
RUNTIME_CONFIG_FILE = RUNTIME_DIR / "config.json"
STATIC_DIR = MODULE_DIR / "static"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_EXCEL_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_IMAGE_BATCH_BYTES = 45 * 1024 * 1024
MAX_IMAGE_BATCH_FILES = 50
MAX_AUTOMATION_SLOTS = 5
SHOP_AUTH_TTL_SECONDS = 30 * 60
USER_CONFIG_HEADER = "X-Ziniao-User-Config"


def _new_automation_event_loop() -> asyncio.AbstractEventLoop:
    """Create an event loop that can launch Playwright's driver on Windows.

    Uvicorn reload mode installs WindowsSelectorEventLoopPolicy globally.  A
    selector loop cannot create subprocesses, so Playwright fails with an empty
    NotImplementedError before it ever connects to Ziniao's CDP port.
    """
    if os.name == "nt":
        return asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
    return asyncio.new_event_loop()


def _exception_text(exc: BaseException) -> str:
    detail = str(exc).strip()
    return detail or f"{type(exc).__name__}: {exc!r}"

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
app = FastAPI(title="亚马逊主图批量上传", version="1.0.0")


@app.middleware("http")
async def require_internal_proxy(request: Request, call_next):
    """Only Java's internal proxy (or local development) may access this app."""
    configured_token = settings.python_internal_api_token
    provided_token = request.headers.get("X-Internal-Token", "")
    if configured_token:
        if not provided_token or not secrets.compare_digest(provided_token, configured_token):
            return JSONResponse({"error": "内部接口令牌无效"}, status_code=401)
    else:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            return JSONResponse(
                {"error": "未配置内部接口令牌时，仅允许本机访问"},
                status_code=403,
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


def detect_ziniao_path() -> str | None:
    """自动检测紫鸟浏览器安装路径（全盘搜索，只认 ziniao.exe 主程序）。"""
    import string
    import subprocess

    # 紫鸟主程序名（只认 ziniao.exe，SuperBrowser.exe 是内核程序不能用）
    possible_names = ["ziniao.exe"]
    # 目录关键词（用于快速定位，紫鸟安装目录可能叫 ziniao 或 SuperBrowser）
    dir_keywords = ["ziniao", "紫鸟", "superbrowser", "super browser"]

    def _is_ziniao_exe(path: str) -> bool:
        """验证一个 exe 是否是紫鸟主程序。"""
        if not os.path.isfile(path):
            return False
        fname = os.path.basename(path).lower()
        return any(n.lower() == fname for n in possible_names)

    # ================================================================
    # 第1层：最快——正在运行的紫鸟进程（直接拿路径，100%准确）
    # ================================================================
    for name in possible_names:
        try:
            result = subprocess.run(
                ["wmic", "process", "where", f"name='{name}'", "get", "ExecutablePath", "/value"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "ExecutablePath=" in line:
                    path = line.split("=", 1)[1].strip()
                    if path and os.path.isfile(path):
                        return path
        except Exception:
            continue

    # ================================================================
    # 第2层：快——注册表卸载信息
    # ================================================================
    reg_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, subkey in reg_paths:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                        i += 1
                        with winreg.OpenKey(key, name) as item:
                            try:
                                display_name = winreg.QueryValueEx(item, "DisplayName")[0]
                            except OSError:
                                continue
                            name_lower = display_name.lower()
                            if any(kw in name_lower for kw in dir_keywords):
                                # 尝试 InstallLocation
                                try:
                                    install_loc = winreg.QueryValueEx(item, "InstallLocation")[0]
                                    for n in possible_names:
                                        candidate = os.path.join(install_loc, n)
                                        if os.path.isfile(candidate):
                                            return candidate
                                except OSError:
                                    pass
                                # 尝试 DisplayIcon
                                try:
                                    icon = winreg.QueryValueEx(item, "DisplayIcon")[0]
                                    icon = icon.split(",")[0].strip('"')
                                    if _is_ziniao_exe(icon):
                                        return icon
                                except OSError:
                                    pass
                    except OSError:
                        break
        except OSError:
            continue

    # ================================================================
    # 第3层：较快——桌面 + 开始菜单快捷方式
    # ================================================================
    shortcut_dirs = [
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    ]
    for sdir in shortcut_dirs:
        if not os.path.isdir(sdir):
            continue
        for root, dirs, files in os.walk(sdir):
            for fname in files:
                if fname.lower().endswith(".lnk"):
                    if any(kw in fname.lower() for kw in dir_keywords):
                        try:
                            import win32com.client
                            shell = win32com.client.Dispatch("WScript.Shell")
                            shortcut = shell.CreateShortCut(os.path.join(root, fname))
                            target = shortcut.Targetpath
                            if _is_ziniao_exe(target):
                                return target
                        except Exception:
                            pass

    # ================================================================
    # 第4层：中速——所有盘符的常见安装目录
    # ================================================================
    drives = [c + ":\\" for c in string.ascii_uppercase if os.path.exists(c + ":\\")]
    common_dirs = [
        r"Program Files\ziniao",
        r"Program Files (x86)\ziniao",
        r"Program Files\SuperBrowser",
        r"Program Files (x86)\SuperBrowser",
        "ziniao",
        "SuperBrowser",
    ]
    for drive in drives:
        for d in common_dirs:
            base = os.path.join(drive, d)
            if not os.path.isdir(base):
                continue
            # 直接找主程序
            for n in possible_names:
                candidate = os.path.join(base, n)
                if os.path.isfile(candidate):
                    return candidate
            # 找版本号子目录（如 5.270.13.16）
            try:
                for sub in os.listdir(base):
                    sub_path = os.path.join(base, sub)
                    if os.path.isdir(sub_path):
                        for n in possible_names:
                            candidate = os.path.join(sub_path, n)
                            if os.path.isfile(candidate):
                                return candidate
            except Exception:
                pass

    # ================================================================
    # 第5层：慢速但全面——全盘递归搜索（深度6层，跳过系统和已搜目录）
    # ================================================================
    skip_dirs = {
        "windows", "system volume information", "$recycle.bin", "programdata",
        "users", "appdata", "node_modules", ".git", "__pycache__",
        "program files", "program files (x86)",  # 第4层已搜过，避免重复
    }

    def _recursive_search(start_dir: str, max_depth: int, current_depth: int = 0) -> str | None:
        """递归搜索紫鸟主程序。"""
        if current_depth > max_depth:
            return None
        try:
            entries = os.listdir(start_dir)
        except Exception:
            return None

        # 先检查当前目录有没有主程序
        for n in possible_names:
            candidate = os.path.join(start_dir, n)
            if os.path.isfile(candidate):
                return candidate

        # 递归子目录
        for entry in entries:
            entry_path = os.path.join(start_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            if entry.lower() in skip_dirs:
                continue
            result = _recursive_search(entry_path, max_depth, current_depth + 1)
            if result:
                return result
        return None

    for drive in drives:
        # 从盘符根目录开始，深度6层
        result = _recursive_search(drive, max_depth=6)
        if result:
            return result

    # 没找到
    return None


def _shop_root() -> Path:
    """Return the fixed Windows-side shop repository configured by the host."""
    raw = (os.getenv("AMAZON_IMAGE_UPLOAD_SHOP_ROOT") or "").strip()
    if not raw:
        raise ValueError(
            "执行主机未配置 AMAZON_IMAGE_UPLOAD_SHOP_ROOT，请先设置固定店铺扫描根目录"
        )
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError("AMAZON_IMAGE_UPLOAD_SHOP_ROOT 必须是绝对路径")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_windows_component(value: str, fallback: str) -> str:
    """Build a readable Windows folder component without reserved names/chars."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if not cleaned or cleaned.upper() in reserved:
        cleaned = fallback
    return cleaned[:96].rstrip(" .") or fallback


def _find_shop_excel(shop_dir: Path) -> Path | None:
    candidates = sorted(
        (
            item for item in shop_dir.iterdir()
            if item.is_file() and item.suffix.lower() in {".xlsx", ".xlsm"}
        ),
        key=lambda item: ("sku" not in item.name.lower(), item.name.lower()),
    )
    return candidates[0] if candidates else None


def _image_root_has_images(image_root: Path) -> bool:
    try:
        return any(
            image.is_file() and image.suffix.lower() in ALLOWED_IMAGE_SUFFIXES
            for sku_dir in image_root.iterdir()
            if sku_dir.is_dir() and not sku_dir.name.startswith(".")
            for image in sku_dir.iterdir()
        )
    except OSError:
        return False


def _initialize_authorized_shop(
    root: Path, shop_id: str, shop_name: str
) -> dict[str, Any]:
    """Create/reuse one deterministic folder for an authorized Ziniao shop."""
    stable_id = (shop_id or shop_name).strip()
    digest = hashlib.sha256(stable_id.encode("utf-8")).hexdigest()[:12]
    suffix = f"__{digest}"
    existing = next(
        (
            item for item in root.iterdir()
            if item.is_dir() and item.name.lower().endswith(suffix)
        ),
        None,
    )
    created = existing is None
    if existing is None:
        base = _safe_windows_component(shop_name, "未命名店铺")
        existing = root / f"{base[: max(1, 110 - len(suffix))]}{suffix}"
        existing.mkdir(parents=True, exist_ok=True)

    image_root = existing / "图片"
    image_root.mkdir(parents=True, exist_ok=True)
    excel = _find_shop_excel(existing)
    return {
        "ziniao_shop_id": shop_id,
        "ziniao_shop_name": shop_name,
        "shop_name": existing.name,
        "shop_key": shop_id,
        "path": str(existing),
        "excel": str(excel) if excel else "",
        "image_root": str(image_root),
        "has_excel": excel is not None,
        "has_images": _image_root_has_images(image_root),
        "matched": True,
        "folder_created": created,
    }


def _default_config() -> dict[str, Any]:
    return {
        "marketplaces": [
            {"code": "DE", "name": "德国", "domain": "sellercentral.amazon.de"},
        ],
        "paths": {
            "sku_excel": "",
            "image_root": "",
            "log_dir": str(RUNTIME_DIR / "logs"),
            "progress_file": str(RUNTIME_DIR / "progress.json"),
        },
        "ziniao": {
            "client_path": os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_CLIENT_PATH", ""),
            "socket_port": int(os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_PORT", "16851")),
            "company": os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_COMPANY", ""),
            "username": os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_USERNAME", ""),
            # 密码不允许从.env/文件读取，ERP访问时只由Redis 8小时快照注入。
            "password": "",
            "default_shop": os.getenv("AMAZON_IMAGE_UPLOAD_DEFAULT_SHOP", ""),
        },
        "browser": {
            "slow_mo": 300,
            "timeout": 30000,
            "retry_times": 3,
        },
        "excel": {
            "sku_column": "SKU",
        },
        "upload": {
            "wait_after_save": 2,
            "clear_existing_images": True,
        },
    }


def _load_runtime_config() -> dict[str, Any]:
    loaded = _default_config()
    if RUNTIME_CONFIG_FILE.exists():
        try:
            overrides = json.loads(RUNTIME_CONFIG_FILE.read_text(encoding="utf-8"))
            for section in ("browser", "excel", "upload"):
                values = overrides.get(section)
                if isinstance(values, dict):
                    loaded.setdefault(section, {}).update(values)
        except Exception:
            pass
    # 全局回退值只来自服务器环境。ERP访问时会按当前用户覆盖。
    loaded["ziniao"]["client_path"] = os.getenv(
        "AMAZON_IMAGE_UPLOAD_ZINIAO_CLIENT_PATH", ""
    )
    loaded["ziniao"]["socket_port"] = int(
        os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_PORT", "16851")
    )
    loaded["ziniao"]["company"] = os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_COMPANY", "")
    loaded["ziniao"]["username"] = os.getenv("AMAZON_IMAGE_UPLOAD_ZINIAO_USERNAME", "")
    loaded["ziniao"]["password"] = ""
    return loaded


def _save_runtime_config(data: dict[str, Any]) -> None:
    allowed: dict[str, dict[str, Any]] = {}
    for section in ("browser", "excel", "upload"):
        if isinstance(data.get(section), dict):
            allowed[section] = dict(data[section])
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG_FILE.write_text(
        json.dumps(allowed, ensure_ascii=False, indent=2), encoding="utf-8"
    )


cfg: dict[str, Any] = _load_runtime_config()


def _config_for_request(request: Request) -> dict[str, Any]:
    """Build a request-scoped config; ERP user credentials never enter global cfg."""
    runtime = copy.deepcopy(cfg)
    encoded = (request.headers.get(USER_CONFIG_HEADER) or "").strip()
    if not encoded:
        return runtime
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        )
    except Exception as exc:
        raise ValueError("当前用户的紫鸟配置传输格式无效") from exc
    if not isinstance(payload, dict) or payload.get("source") != "erp_user":
        raise ValueError("当前用户的紫鸟配置来源无效")

    header_user_id = (request.headers.get("X-Erp-User-ID") or "").strip()
    payload_user_id = str(payload.get("user_id") or "").strip()
    if header_user_id and payload_user_id and header_user_id != payload_user_id:
        raise ValueError("当前ERP用户与紫鸟配置不匹配")

    ziniao = runtime.setdefault("ziniao", {})
    ziniao["company"] = str(payload.get("company") or "")[:128]
    ziniao["username"] = str(payload.get("username") or "")[:128]
    ziniao["password"] = str(payload.get("password") or "")[:512]
    ziniao["client_path"] = str(payload.get("client_path") or "")[:500]
    try:
        expires_in = max(0, int(payload.get("password_expires_in_seconds") or 0))
    except (TypeError, ValueError):
        expires_in = 0
    ziniao["password_expires_at"] = time.time() + expires_in if expires_in else 0
    runtime["erp_user_config"] = True
    return runtime


def _ziniao_config_error(runtime: dict[str, Any]) -> str | None:
    ziniao = runtime.get("ziniao", {}) or {}
    if not ziniao.get("company") or not ziniao.get("username"):
        return "请返回ERP脚本菜单配置紫鸟公司名和账号"
    if not ziniao.get("password"):
        return "紫鸟密码未输入或已超过8小时，请返回ERP重新输入"
    if not ziniao.get("client_path"):
        return "请返回ERP脚本菜单配置紫鸟 ziniao.exe 路径"
    return None

# 上传任务管理：最多五个独立紫鸟端口，超出的任务保留在内存队列中。
_task_lock = threading.RLock()
_pending_uploads: deque[dict[str, Any]] = deque()
_active_uploads: dict[int, dict[str, Any]] = {}

# 本地文件上传可在不同店铺并行；同一店铺串行提交并使用原子替换。
_shop_file_locks: dict[str, asyncio.Lock] = {}
_shop_file_locks_guard = threading.Lock()

# 用户可见店铺和上传文件缓存必须按ERP用户隔离。这里不存放密码。
_user_states: dict[str, dict[str, Any]] = {}
_user_states_lock = threading.RLock()

# WebSocket 连接池
_ws_clients: set[WebSocket] = set()
_ws_lock = threading.Lock()

# 跨线程消息队列（后台线程 put，主事件循环协程 get 并广播）
_msg_queue: queue.Queue = queue.Queue()

# 日志缓冲区（最近 500 条）
_log_buffer: list[dict] = []
LOG_MAX = 500


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _log(level: str, msg: str, task_id: int | None = None) -> None:
    """Record an in-memory live log and a durable task log."""
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "msg": msg,
    }
    _log_buffer.append(entry)
    if len(_log_buffer) > LOG_MAX:
        _log_buffer.pop(0)
    if task_id is not None:
        try:
            repository.append_log(task_id, level, msg)
        except Exception:
            pass
    _ws_broadcast({"type": "log", "data": entry})


def _ws_broadcast(message: dict) -> None:
    """把消息放入队列，由主事件循环的 broadcast_worker 统一推送。"""
    _msg_queue.put(message)


async def _broadcast_worker() -> None:
    """主事件循环中的后台协程：从队列取消息并广播给所有 WebSocket。"""
    while True:
        try:
            # 不要把永久阻塞的 Queue.get 放进默认线程池。Uvicorn 热重载时会
            # 等待线程池退出，之前这里会让整个 Python 服务卡在关闭阶段。
            try:
                message = _msg_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            data = json.dumps(message, ensure_ascii=False)
            with _ws_lock:
                dead = []
                for ws in _ws_clients:
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    _ws_clients.discard(ws)
        except Exception:
            await asyncio.sleep(0.1)


def _get_marketplace(runtime_config: dict[str, Any] | None = None) -> dict[str, str]:
    """获取德国站配置（固定单站点）。"""
    mps = cl.get_marketplaces(runtime_config or cfg)
    if mps:
        return mps[0]
    # 兜底
    return {"code": "DE", "name": "德国", "domain": "sellercentral.amazon.de"}


def _progress_path() -> str:
    return str((cfg.get("paths", {}) or {}).get("progress_file", "data/progress.json"))


def _load_completed(user_id: int | None = None) -> set[str]:
    try:
        return repository.completed_keys(user_id)
    except Exception:
        return set()


def _erp_actor(request: Request) -> tuple[int | None, str, str]:
    raw_user_id = (request.headers.get("X-Erp-User-ID") or "").strip()
    try:
        user_id = int(raw_user_id) if raw_user_id else None
    except ValueError:
        user_id = None
    username = (request.headers.get("X-Erp-User") or "").strip() or "local"
    request_id = (request.headers.get("X-Request-ID") or "").strip() or get_request_id()
    return user_id, username[:100], request_id[:64]


def _user_state(request: Request) -> dict[str, Any]:
    raw_user_id = (request.headers.get("X-Erp-User-ID") or "").strip()
    key = f"erp:{raw_user_id}" if raw_user_id else "local"
    with _user_states_lock:
        return _user_states.setdefault(
            key,
            {
                "cached_skus": [],
                "cached_excel_path": cl.get_path(cfg, "sku_excel"),
                "cached_image_root": cl.get_path(cfg, "image_root"),
                "scanned_shops": [],
                "ziniao_shops": [],
                "initialized_at": None,
            },
        )


def _any_upload_running() -> bool:
    with _task_lock:
        return bool(_active_uploads)


def _shop_file_lock(shop_id: str) -> asyncio.Lock:
    with _shop_file_locks_guard:
        return _shop_file_locks.setdefault(shop_id, asyncio.Lock())


def _authorized_shop(request: Request, shop_id: str) -> dict[str, Any] | None:
    target = (shop_id or "").strip()
    if not target:
        return None
    state = _user_state(request)
    initialized_at = float(state.get("initialized_at") or 0)
    if initialized_at <= 0 or time.time() - initialized_at > SHOP_AUTH_TTL_SECONDS:
        return None
    for shop in state["scanned_shops"]:
        if str(shop.get("ziniao_shop_id") or "") == target:
            return shop
    return None


def _authorized_shop_by_index(request: Request, shop_index: int) -> dict[str, Any] | None:
    state = _user_state(request)
    initialized_at = float(state.get("initialized_at") or 0)
    shops = state["scanned_shops"]
    if (
        initialized_at <= 0
        or time.time() - initialized_at > SHOP_AUTH_TTL_SECONDS
        or shop_index < 0
        or shop_index >= len(shops)
    ):
        return None
    return shops[shop_index]


def _safe_task_payload(shop_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "shops": [
            {
                "shop_id": str(task.get("shop_id") or "")[:128],
                "shop_name": str(task.get("shop_name") or "")[:255],
                "selected_sku_count": len(task.get("selected_skus") or []),
                "selected_image_count": sum(
                    len(images)
                    for images in (task.get("selected_images") or {}).values()
                    if isinstance(images, list)
                ),
            }
            for task in shop_tasks
        ]
    }


def _dispatch_pending_tasks() -> None:
    """Fill free Ziniao port slots from the FIFO in-memory queue."""
    with _task_lock:
        while _pending_uploads:
            job = _pending_uploads[0]
            runtime_config = copy.deepcopy(job["runtime_config"])
            base_port = int(
                (runtime_config.get("ziniao", {}) or {}).get("socket_port", 16851)
            )
            slot = repository.claim_executor(
                int(job["task_id"]), base_port, MAX_AUTOMATION_SLOTS
            )
            if slot is None:
                break

            _pending_uploads.popleft()
            expiry_timer = job.pop("expiry_timer", None)
            if expiry_timer is not None:
                expiry_timer.cancel()
            runtime_config.setdefault("ziniao", {})["socket_port"] = base_port + slot - 1
            task_id = int(job["task_id"])
            if job["kind"] == "multi":
                target = _run_upload_multi_thread
                args = (
                    task_id,
                    job["shop_tasks"],
                    job["marketplace"],
                    runtime_config,
                    job["user_id"],
                )
            else:
                target = _run_upload_thread
                args = (
                    task_id,
                    job["excel_path"],
                    job["image_root"],
                    job["marketplace"],
                    job["shop_id"],
                    runtime_config,
                    job["user_id"],
                )
            thread = threading.Thread(
                target=target,
                args=args,
                daemon=True,
                name=f"amazon-image-upload-{task_id}-slot-{slot}",
            )
            _active_uploads[task_id] = {
                "thread": thread,
                "app": None,
                "slot": slot,
                "port": base_port + slot - 1,
                "user_id": job["user_id"],
                "stop_requested": False,
            }
            try:
                thread.start()
                job.setdefault("runtime_config", {}).setdefault("ziniao", {})[
                    "password"
                ] = ""
            except Exception as exc:
                job.setdefault("runtime_config", {}).setdefault("ziniao", {})[
                    "password"
                ] = ""
                _active_uploads.pop(task_id, None)
                repository.release_executor(task_id)
                repository.finish_task(task_id, "failed", str(exc))


def _expire_pending_upload(task_id: int) -> None:
    """Remove an in-memory password snapshot when its Redis TTL is reached."""
    expired_job: dict[str, Any] | None = None
    with _task_lock:
        for job in list(_pending_uploads):
            if int(job["task_id"]) != task_id:
                continue
            expires_at = float(
                ((job.get("runtime_config") or {}).get("ziniao", {}) or {}).get(
                    "password_expires_at", 0
                )
                or 0
            )
            if expires_at > 0 and time.time() >= expires_at:
                _pending_uploads.remove(job)
                runtime = job.setdefault("runtime_config", {})
                runtime.setdefault("ziniao", {})["password"] = ""
                expired_job = job
            break
    if expired_job is not None:
        repository.finish_task(
            task_id,
            "failed",
            "排队期间紫鸟密码的8小时Redis缓存已过期，请重新输入后再提交",
        )
        repository.append_log(
            task_id,
            "WARNING",
            "排队期间紫鸟密码已过期，任务已从队列移除",
        )


def _enqueue_upload(job: dict[str, Any]) -> tuple[bool, int]:
    """Queue a task and immediately dispatch it if one of five ports is free."""
    task_id = int(job["task_id"])
    with _task_lock:
        _pending_uploads.append(job)
        _dispatch_pending_tasks()
        if task_id in _active_uploads:
            return True, 0
        for position, queued in enumerate(_pending_uploads, 1):
            if int(queued["task_id"]) == task_id:
                expires_at = float(
                    ((queued.get("runtime_config") or {}).get("ziniao", {}) or {}).get(
                        "password_expires_at", 0
                    )
                    or 0
                )
                if expires_at > 0:
                    timer = threading.Timer(
                        max(0.01, expires_at - time.time()),
                        _expire_pending_upload,
                        args=(task_id,),
                    )
                    timer.daemon = True
                    queued["expiry_timer"] = timer
                    timer.start()
                return False, position
    return False, repository.queue_position(task_id)


# ---------------------------------------------------------------------------
# 上传任务后台线程
# ---------------------------------------------------------------------------
def _run_upload_thread(
    task_id: int,
    excel_path: str,
    image_root: str,
    marketplace: dict[str, str],
    shop_id: str,
    runtime_config: dict[str, Any],
    user_id: int | None,
) -> None:
    """在独立线程中运行 asyncio 事件循环，执行上传任务。"""
    loop = _new_automation_event_loop()
    asyncio.set_event_loop(loop)

    upload_app = UploadApp(
        runtime_config,
        completed_loader=lambda: repository.completed_keys(user_id),
        completed_marker=lambda key: repository.mark_completed(key, task_id, user_id),
    )
    upload_app.set_shop_id(shop_id)
    with _task_lock:
        if task_id in _active_uploads:
            _active_uploads[task_id]["app"] = upload_app

    def log_cb(msg: str) -> None:
        level = "INFO"
        if "失败" in msg or "错误" in msg or "异常" in msg:
            level = "ERROR"
        elif "跳过" in msg:
            level = "WARNING"
        elif "完成" in msg or "成功" in msg:
            level = "SUCCESS"
        _log(level, msg, task_id)

    def prog_cb(done: int, total: int, msg: str) -> None:
        try:
            repository.update_progress(task_id, done, total, msg)
        except Exception:
            pass
        _ws_broadcast({
            "type": "progress",
            "data": {"done": done, "total": total, "msg": msg},
        })

    upload_app.set_callbacks(log_cb=log_cb, prog_cb=prog_cb)

    try:
        upload_app.ziniao.force_exit_client()
        repository.mark_started(task_id)
        _ws_broadcast({"type": "status", "data": {"running": True}})
        loop.run_until_complete(upload_app.run(excel_path, image_root, marketplace))
        with _task_lock:
            stopped = bool(_active_uploads.get(task_id, {}).get("stop_requested"))
        repository.finish_task(task_id, "stopped" if stopped else "completed")
    except Exception as e:
        detail = _exception_text(e)
        _log("ERROR", f"运行异常: {detail}", task_id)
        repository.finish_task(task_id, "failed", detail)
    finally:
        try:
            upload_app.ziniao.exit_client()
        except Exception as exc:
            _log("WARNING", f"释放紫鸟端口失败: {exc}", task_id)
        _ws_broadcast({"type": "status", "data": {"running": False}})
        try:
            loop.close()
        except Exception:
            pass
        repository.release_executor(task_id)
        with _task_lock:
            _active_uploads.pop(task_id, None)
        _dispatch_pending_tasks()


def _run_upload_multi_thread(
    task_id: int,
    shop_tasks: list[dict[str, Any]],
    marketplace: dict[str, str],
    runtime_config: dict[str, Any],
    user_id: int | None,
) -> None:
    """在独立线程中运行多店铺上传任务。"""
    loop = _new_automation_event_loop()
    asyncio.set_event_loop(loop)

    upload_app = UploadApp(
        runtime_config,
        completed_loader=lambda: repository.completed_keys(user_id),
        completed_marker=lambda key: repository.mark_completed(key, task_id, user_id),
    )
    with _task_lock:
        if task_id in _active_uploads:
            _active_uploads[task_id]["app"] = upload_app

    def log_cb(msg: str) -> None:
        level = "INFO"
        if "失败" in msg or "错误" in msg or "异常" in msg:
            level = "ERROR"
        elif "跳过" in msg:
            level = "WARNING"
        elif "完成" in msg or "成功" in msg:
            level = "SUCCESS"
        _log(level, msg, task_id)

    def prog_cb(done: int, total: int, msg: str) -> None:
        try:
            repository.update_progress(task_id, done, total, msg)
        except Exception:
            pass
        _ws_broadcast({
            "type": "progress",
            "data": {"done": done, "total": total, "msg": msg},
        })

    upload_app.set_callbacks(log_cb=log_cb, prog_cb=prog_cb)

    try:
        upload_app.ziniao.force_exit_client()
        repository.mark_started(task_id)
        _ws_broadcast({"type": "status", "data": {"running": True}})
        loop.run_until_complete(upload_app.run_multi(shop_tasks, marketplace))
        with _task_lock:
            stopped = bool(_active_uploads.get(task_id, {}).get("stop_requested"))
        repository.finish_task(task_id, "stopped" if stopped else "completed")
    except Exception as e:
        detail = _exception_text(e)
        _log("ERROR", f"运行异常: {detail}", task_id)
        repository.finish_task(task_id, "failed", detail)
    finally:
        try:
            upload_app.ziniao.exit_client()
        except Exception as exc:
            _log("WARNING", f"释放紫鸟端口失败: {exc}", task_id)
        _ws_broadcast({"type": "status", "data": {"running": False}})
        try:
            loop.close()
        except Exception:
            pass
        repository.release_executor(task_id)
        with _task_lock:
            _active_uploads.pop(task_id, None)
        _dispatch_pending_tasks()


# ---------------------------------------------------------------------------
# 静态文件（前端）
# ---------------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(STATIC_DIR)), name="web")


@app.get("/")
async def index():
    """返回前端首页。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(index_file))
    return JSONResponse({"error": "前端文件未找到，请确认 static/index.html 存在"}, status_code=404)


# ---------------------------------------------------------------------------
# 配置 API
# ---------------------------------------------------------------------------
@app.get("/api/config")
async def get_config(request: Request):
    """Return non-secret runtime settings; never expose the password."""
    try:
        runtime_config = _config_for_request(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    z = dict(runtime_config.get("ziniao", {}) or {})
    z["configured"] = bool(
        z.get("company")
        and z.get("username")
        and z.get("password")
        and z.get("client_path")
    )
    z["password"] = ""
    return {
        "ziniao": z,
        "shop_storage": {
            "root": (os.getenv("AMAZON_IMAGE_UPLOAD_SHOP_ROOT") or "").strip(),
            "configured": bool((os.getenv("AMAZON_IMAGE_UPLOAD_SHOP_ROOT") or "").strip()),
        },
        "automation": {
            "base_port": int(z.get("socket_port") or 16851),
            "max_concurrent": MAX_AUTOMATION_SLOTS,
        },
        "marketplaces": cl.get_marketplaces(runtime_config),
        "browser": runtime_config.get("browser", {}),
        "excel": runtime_config.get("excel", {}),
        "paths": {
            "sku_excel": cl.get_path(runtime_config, "sku_excel"),
            "image_root": cl.get_path(runtime_config, "image_root"),
        },
        "upload": runtime_config.get("upload", {}),
    }


@app.post("/api/config")
async def save_config(data: dict):
    """Persist only non-secret runtime settings under outputs/."""
    global cfg
    try:
        _save_runtime_config(data)
        cfg = _load_runtime_config()
        _log("INFO", "浏览器运行参数已保存；紫鸟用户配置继续由ERP管理")
        return {"ok": True}
    except Exception as e:
        _log("ERROR", f"保存配置失败: {e}")
        return JSONResponse({"error": f"保存配置失败: {e}"}, status_code=500)


# ---------------------------------------------------------------------------
# 紫鸟店铺 API
# ---------------------------------------------------------------------------
@app.post("/api/shops/refresh")
async def refresh_shops(request: Request):
    """获取当前用户有权访问的紫鸟店铺，并初始化固定根目录。"""
    state = _user_state(request)

    try:
        runtime_config = _config_for_request(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    config_error = _ziniao_config_error(runtime_config)
    if config_error:
        return JSONResponse(
            {"error": config_error},
            status_code=400,
        )
    try:
        shop_root = _shop_root()
    except (ValueError, OSError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    ziniao_cfg = copy.deepcopy(runtime_config.get("ziniao", {}) or {})
    base_port = int(ziniao_cfg.get("socket_port") or 16851)
    temporary_owner = -int(time.time_ns() % 9_000_000_000) - 1
    try:
        slot = await asyncio.to_thread(
            repository.claim_executor,
            temporary_owner,
            base_port,
            MAX_AUTOMATION_SLOTS,
        )
    except Exception as exc:
        return JSONResponse({"error": f"分配紫鸟端口失败: {exc}"}, status_code=500)
    if slot is None:
        return JSONResponse(
            {
                "error": "当前5个紫鸟自动化端口均在使用中，店铺初始化正在排队，请稍后重试",
                "queued": True,
            },
            status_code=429,
        )
    ziniao_cfg["socket_port"] = base_port + slot - 1

    _log("INFO", f"正在通过端口 {ziniao_cfg['socket_port']} 获取紫鸟店铺列表...")

    def _fetch_ziniao() -> list[dict]:
        ziniao = ZiniaoClient(ziniao_cfg)
        try:
            # 槽位可能残留上一次账号的进程，必须先清理再用当前账号启动。
            ziniao.force_exit_client()
            client_path = ziniao_cfg.get("client_path", "")
            if client_path and not os.path.exists(client_path):
                raise RuntimeError(
                    f"紫鸟客户端路径不存在: {client_path}；请配置 ziniao.exe"
                )
            if not ziniao.start_client():
                raise RuntimeError(
                    "紫鸟客户端启动失败，请检查路径、账号密码、webdriver权限或多实例授权"
                )
            if not ziniao.update_core():
                raise RuntimeError("紫鸟浏览器内核更新失败")
            return ziniao.get_browser_list()
        finally:
            ziniao.exit_client()

    try:
        shops = await asyncio.to_thread(_fetch_ziniao)
    except Exception as exc:
        _log("ERROR", str(exc))
        return JSONResponse({"error": str(exc)}, status_code=502)
    finally:
        await asyncio.to_thread(repository.release_executor, temporary_owner)
        _dispatch_pending_tasks()

    if not shops:
        state["ziniao_shops"] = []
        state["scanned_shops"] = []
        state["initialized_at"] = time.time()
        return {
            "shops": [],
            "count": 0,
            "created_count": 0,
            "root": str(shop_root),
        }

    _log("SUCCESS", f"获取到 {len(shops)} 个紫鸟店铺")
    ziniao_shops: list[dict[str, Any]] = []
    for s in shops:
        shop_id = str(s.get("browserOauth") or s.get("browserId") or "").strip()
        if not shop_id:
            _log("WARNING", f"忽略缺少店铺标识的紫鸟记录: {s.get('browserName', '未命名')}")
            continue
        ziniao_shops.append({
            "id": shop_id,
            "name": str(s.get("browserName") or "未命名"),
            "oauth": str(s.get("browserOauth") or ""),
        })

    scanned_shops = await asyncio.to_thread(
        lambda: [
            _initialize_authorized_shop(shop_root, shop["id"], shop["name"])
            for shop in ziniao_shops
        ]
    )
    created_count = sum(1 for shop in scanned_shops if shop["folder_created"])

    state["ziniao_shops"] = ziniao_shops
    state["scanned_shops"] = scanned_shops
    state["initialized_at"] = time.time()
    _log(
        "SUCCESS",
        f"已初始化 {len(scanned_shops)} 个授权店铺目录，新建 {created_count} 个",
    )

    return {
        "shops": scanned_shops,
        "count": len(scanned_shops),
        "ziniao_count": len(ziniao_shops),
        "matched_count": len(scanned_shops),
        "created_count": created_count,
        "root": str(shop_root),
    }


@app.get("/api/shops/scan")
async def scan_shops(request: Request):
    """只重新扫描当前用户已通过紫鸟鉴权的店铺目录。"""
    state = _user_state(request)
    initialized_at = float(state.get("initialized_at") or 0)
    if (
        not state["ziniao_shops"]
        or initialized_at <= 0
        or time.time() - initialized_at > SHOP_AUTH_TTL_SECONDS
    ):
        return JSONResponse(
            {"error": "请先刷新紫鸟店铺以初始化当前用户权限"}, status_code=400
        )
    try:
        root = _shop_root()
        shops = await asyncio.to_thread(
            lambda: [
                _initialize_authorized_shop(root, shop["id"], shop["name"])
                for shop in state["ziniao_shops"]
            ]
        )
    except Exception as exc:
        return JSONResponse({"error": f"扫描店铺目录失败: {exc}"}, status_code=500)
    state["scanned_shops"] = shops
    return {"shops": shops, "count": len(shops), "root": str(root)}


# ---------------------------------------------------------------------------
# 店铺 SKU 和图片 API
# ---------------------------------------------------------------------------
@app.get("/api/shop/skus")
async def get_shop_skus(request: Request, shop_index: int):
    """获取某个店铺的SKU列表（解析Excel）。"""
    shop = _authorized_shop_by_index(request, shop_index)
    if shop is None:
        return JSONResponse({"error": "店铺权限已过期，请刷新店铺"}, status_code=403)
    excel_path = shop.get("excel", "")

    if not excel_path or not os.path.exists(excel_path):
        return JSONResponse({"error": "该店铺没有找到Excel文件"}, status_code=400)

    def _parse() -> list[str]:
        return read_skus(excel_path)

    loop = asyncio.get_event_loop()
    try:
        skus = await loop.run_in_executor(None, _parse)
    except Exception as e:
        return JSONResponse({"error": f"解析Excel失败: {e}"}, status_code=500)

    # 检查每个SKU是否有图片
    image_root = shop.get("image_root", "")
    sku_list = []
    for sku in skus:
        has_images = False
        if image_root and os.path.isdir(image_root):
            sku_dir = os.path.join(image_root, sku)
            if os.path.isdir(sku_dir):
                has_images = True
        sku_list.append({
            "sku": sku,
            "has_images": has_images,
        })

    return {"skus": sku_list, "count": len(sku_list), "shop_name": shop["shop_name"]}


@app.get("/api/shop/sku/images")
async def get_shop_sku_images(request: Request, shop_index: int, sku: str):
    """获取某个店铺某个SKU的图片列表。"""
    shop = _authorized_shop_by_index(request, shop_index)
    if shop is None:
        return JSONResponse({"error": "店铺权限已过期，请刷新店铺"}, status_code=403)
    image_root = Path(str(shop.get("image_root") or "")).resolve()
    if not image_root.is_dir():
        return JSONResponse({"error": "该店铺没有找到图片目录"}, status_code=400)
    try:
        checked_sku = _checked_upload_component(sku, "SKU")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    sku_dir = (image_root / checked_sku).resolve()
    try:
        inside_root = os.path.commonpath([str(image_root), str(sku_dir)]) == str(image_root)
    except ValueError:
        inside_root = False
    if not inside_root:
        return JSONResponse({"error": "非法SKU路径"}, status_code=400)
    if not sku_dir.is_dir():
        return {"images": [], "count": 0, "sku": sku}

    from urllib.parse import quote
    images = [
        {
            "name": os.path.basename(path),
            "url": (
                f"/api/shop/sku/image/file?shop_index={shop_index}"
                f"&sku={quote(checked_sku, safe='')}&name={quote(os.path.basename(path), safe='')}"
            ),
        }
        for path in get_sku_images(checked_sku, str(image_root))
    ]

    return {"images": images, "count": len(images), "sku": sku}


@app.get("/api/shop/images/catalog")
async def get_shop_image_catalog(request: Request, shop_index: int):
    """列出当前授权店铺图片目录中的全部SKU及缩略图。"""
    shop = _authorized_shop_by_index(request, shop_index)
    if shop is None:
        return JSONResponse({"error": "店铺权限已过期，请刷新店铺"}, status_code=403)
    image_root = Path(str(shop.get("image_root") or "")).resolve()
    if not image_root.is_dir():
        return {"items": [], "sku_count": 0, "image_count": 0}

    from urllib.parse import quote
    items: list[dict[str, Any]] = []
    image_count = 0
    for sku_dir in sorted(
        (item for item in image_root.iterdir() if item.is_dir() and not item.name.startswith(".")),
        key=lambda item: item.name.casefold(),
    ):
        resolved_sku_dir = sku_dir.resolve()
        try:
            inside_root = os.path.commonpath(
                [str(image_root), str(resolved_sku_dir)]
            ) == str(image_root)
        except ValueError:
            inside_root = False
        if not inside_root:
            continue
        image_paths = get_sku_images(sku_dir.name, str(image_root))
        if not image_paths:
            continue
        images = [
            {
                "name": os.path.basename(path),
                "url": (
                    f"/api/shop/sku/image/file?shop_index={shop_index}"
                    f"&sku={quote(sku_dir.name, safe='')}"
                    f"&name={quote(os.path.basename(path), safe='')}"
                ),
            }
            for path in image_paths
        ]
        image_count += len(images)
        items.append({"sku": sku_dir.name, "images": images, "count": len(images)})
    return {
        "items": items,
        "sku_count": len(items),
        "image_count": image_count,
    }


@app.get("/api/shop/sku/image/file")
async def get_shop_sku_image_file(request: Request, shop_index: int, sku: str, name: str):
    """返回某个店铺某个SKU的图片文件（带路径穿越安全检查）。"""
    _log("INFO", f"图片请求: shop_index={shop_index}, sku={sku}, name={name}")

    shop = _authorized_shop_by_index(request, shop_index)
    if shop is None:
        return JSONResponse({"error": "店铺权限已过期，请刷新店铺"}, status_code=403)
    image_root = Path(str(shop.get("image_root") or "")).resolve()
    if not image_root.is_dir():
        _log("ERROR", "图片目录无效")
        return JSONResponse({"error": "图片目录无效"}, status_code=400)

    # 安全检查：防止路径穿越
    try:
        checked_sku = _checked_upload_component(sku, "SKU")
        checked_name = _checked_upload_component(name, "图片文件名")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    sku_dir = (image_root / checked_sku).resolve()
    file_path = (sku_dir / checked_name).resolve()
    try:
        inside_root = os.path.commonpath([str(image_root), str(sku_dir)]) == str(image_root)
        inside_sku_dir = os.path.commonpath([str(sku_dir), str(file_path)]) == str(sku_dir)
    except ValueError:
        inside_root = False
        inside_sku_dir = False
    if not inside_root or not inside_sku_dir:
        _log("ERROR", f"非法路径: {file_path}")
        return JSONResponse({"error": "非法路径"}, status_code=400)

    if not file_path.is_file() or file_path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        _log("ERROR", f"文件不存在: {file_path}")
        return JSONResponse({"error": "文件不存在"}, status_code=404)

    _log("INFO", f"返回图片: {file_path}, 大小={os.path.getsize(file_path)} bytes")

    # 根据扩展名设置media_type
    ext = file_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    # 使用StreamingResponse手动读取文件，避免FileResponse在打包环境中的问题
    from fastapi.responses import StreamingResponse

    def iterfile():
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ---------------------------------------------------------------------------
# Excel API
# ---------------------------------------------------------------------------
@app.post("/api/excel/parse")
async def parse_excel(request: Request, file: UploadFile = File(None), path: str = Form(None)):
    """解析 Excel，返回 SKU 列表。支持上传文件或指定本地路径。"""
    state = _user_state(request)

    excel_path = path
    if excel_path:
        requested = Path(excel_path).resolve()
        allowed = any(
            shop.get("excel")
            and Path(str(shop["excel"])).resolve() == requested
            for shop in state["scanned_shops"]
        )
        initialized_at = float(state.get("initialized_at") or 0)
        if (
            not allowed
            or initialized_at <= 0
            or time.time() - initialized_at > SHOP_AUTH_TTL_SECONDS
        ):
            return JSONResponse(
                {"error": "只能读取当前用户已初始化店铺中的Excel文件"}, status_code=403
            )
    if file:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            return JSONResponse({"error": "仅支持 .xlsx 或 .xlsm 文件"}, status_code=400)
        # 保存上传的文件
        save_dir = RUNTIME_DIR / "data"
        save_dir.mkdir(parents=True, exist_ok=True)
        excel_path = str(save_dir / f"uploaded_skus_{int(time.time())}{suffix}")
        content = await file.read()
        if len(content) > MAX_EXCEL_BYTES:
            return JSONResponse({"error": "Excel 文件不能超过 20MB"}, status_code=413)
        with open(excel_path, "wb") as f:
            f.write(content)
        _log("INFO", f"Excel 已上传: {file.filename}")

    if not excel_path or not os.path.exists(excel_path):
        return JSONResponse({"error": "请上传 Excel 文件或指定有效路径"}, status_code=400)

    sku_col = str((cfg.get("excel", {}) or {}).get("sku_column", "SKU"))
    try:
        skus = read_skus(excel_path, sku_col)
    except Exception as e:
        return JSONResponse({"error": f"解析 Excel 失败: {e}"}, status_code=400)

    state["cached_skus"] = skus
    state["cached_excel_path"] = excel_path

    _log("INFO", f"解析到 {len(skus)} 个 SKU")
    return {"skus": skus, "count": len(skus), "path": excel_path}


# ---------------------------------------------------------------------------
# 图片 API
# ---------------------------------------------------------------------------
@app.post("/api/images/scan")
async def scan_images(request: Request, path: str = Form(...)):
    """扫描本地图片根目录，返回每个 SKU 的图片数量。"""
    state = _user_state(request)

    if not path or not os.path.isdir(path):
        return JSONResponse({"error": "图片目录不存在"}, status_code=400)
    requested = Path(path).resolve()
    authorized = any(
        shop.get("image_root")
        and Path(str(shop["image_root"])).resolve() == requested
        for shop in state["scanned_shops"]
    )
    initialized_at = float(state.get("initialized_at") or 0)
    if (
        not authorized
        or initialized_at <= 0
        or time.time() - initialized_at > SHOP_AUTH_TTL_SECONDS
    ):
        return JSONResponse(
            {"error": "只能扫描当前用户紫鸟权限内的店铺图片目录"}, status_code=403
        )

    state["cached_image_root"] = path

    # 如果已有缓存的 SKU 列表，匹配图片
    sku_images = {}
    skus_to_check = state["cached_skus"] if state["cached_skus"] else []

    if skus_to_check:
        for sku in skus_to_check:
            imgs = get_sku_images(sku, path)
            sku_images[sku] = len(imgs)
    else:
        # 没有 Excel，扫描目录下所有子文件夹
        try:
            for entry in os.scandir(path):
                if entry.is_dir():
                    imgs = get_sku_images(entry.name, path)
                    if imgs:
                        sku_images[entry.name] = len(imgs)
        except Exception as e:
            return JSONResponse({"error": f"扫描目录失败: {e}"}, status_code=400)

    total_images = sum(sku_images.values())
    _log("INFO", f"图片目录已扫描: {len(sku_images)} 个 SKU 文件夹，共 {total_images} 张图片")
    return {
        "path": path,
        "sku_images": sku_images,
        "sku_count": len(sku_images),
        "total_images": total_images,
    }


@app.post("/api/images/upload")
async def upload_images(request: Request, files: list[UploadFile] = File(...)):
    """通过浏览器文件夹选择上传图片（保留相对路径结构）。"""
    state = _user_state(request)

    save_dir = RUNTIME_DIR / "data" / f"uploaded_images_{int(time.time())}"
    save_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for f in files:
        # webkitRelativePath 格式：文件夹名/SKU名/图片.jpg
        rel_path = f.filename or ""
        if not rel_path:
            continue
        # 去掉第一层（用户选择的根文件夹名）
        parts = Path(rel_path.replace("\\", "/")).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            continue
        if len(parts) > 1:
            parts = parts[1:]
        suffix = Path(parts[-1]).suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            continue
        target = (save_dir / Path(*parts)).resolve()
        try:
            inside_save_dir = os.path.commonpath([str(save_dir.resolve()), str(target)]) == str(save_dir.resolve())
        except ValueError:
            inside_save_dir = False
        if not inside_save_dir:
            continue
        content = await f.read()
        if len(content) > MAX_IMAGE_BYTES:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as out:
            out.write(content)
        saved += 1

    state["cached_image_root"] = str(save_dir)

    _log("INFO", f"图片文件夹已上传: {saved} 个文件，保存到 {save_dir}")
    return {"path": str(save_dir), "files_saved": saved}


@app.get("/api/images/list")
async def list_images(request: Request, sku: str):
    """获取指定 SKU 的图片列表（用于前端预览）。"""
    image_root = _user_state(request)["cached_image_root"]
    if not image_root:
        return JSONResponse({"error": "请先选择/上传图片文件夹"}, status_code=400)

    imgs = get_sku_images(sku, image_root)
    if not imgs:
        return {"sku": sku, "images": [], "count": 0}

    image_list = []
    for p in imgs:
        fname = os.path.basename(p)
        image_list.append({
            "name": fname,
            "url": f"/api/images/file?sku={sku}&name={fname}",
        })
    return {"sku": sku, "images": image_list, "count": len(image_list)}


@app.get("/api/images/file")
async def get_image_file(request: Request, sku: str, name: str):
    """返回指定 SKU 的图片文件（用于前端 <img> 标签加载）。"""
    image_root = _user_state(request)["cached_image_root"]
    if not image_root:
        return JSONResponse({"error": "图片目录未设置"}, status_code=400)

    # 安全检查：防止路径穿越
    safe_name = os.path.basename(name)
    sku_dir = os.path.join(image_root, sku)
    file_path = os.path.join(sku_dir, safe_name)

    # 确保文件在图片根目录内
    real_root = os.path.realpath(image_root)
    real_path = os.path.realpath(file_path)
    try:
        inside_root = os.path.commonpath([real_root, real_path]) == real_root
    except ValueError:
        inside_root = False
    if not inside_root:
        return JSONResponse({"error": "非法路径"}, status_code=400)

    if not os.path.isfile(file_path):
        return JSONResponse({"error": "文件不存在"}, status_code=404)

    from fastapi.responses import FileResponse
    return FileResponse(file_path)


@app.get("/api/ziniao/detect")
async def detect_ziniao():
    """自动检测紫鸟浏览器安装路径。"""
    path = await asyncio.to_thread(detect_ziniao_path)
    if path:
        return {"found": True, "path": path}
    return {"found": False, "path": "", "message": "未检测到紫鸟浏览器，请手动填写安装路径"}


# ---------------------------------------------------------------------------
# 上传任务 API
# ---------------------------------------------------------------------------
def _checked_upload_component(value: str, label: str) -> str:
    candidate = (value or "").strip().strip(" .")
    if (
        not candidate
        or candidate in {".", ".."}
        or len(candidate) > 255
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', candidate)
    ):
        raise ValueError(f"{label}不合法: {value}")
    return candidate


def _batch_target(
    upload: UploadFile, relative_path: str, explicit_sku: str
) -> tuple[str, str]:
    raw_path = (relative_path or upload.filename or "").replace("\\", "/")
    parts = [part for part in raw_path.split("/") if part]
    if not parts:
        raise ValueError("图片文件名为空")
    filename = _checked_upload_component(parts[-1], "图片文件名")
    if Path(filename).suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        raise ValueError(f"不支持的图片格式: {filename}")
    if explicit_sku:
        sku = _checked_upload_component(explicit_sku, "SKU")
    else:
        if len(parts) < 2:
            raise ValueError(
                f"{filename} 缺少SKU目录；请选择包含 SKU/图片 的文件夹，或填写SKU"
            )
        sku = _checked_upload_component(parts[-2], "SKU")
    return sku, filename


def _cleanup_batch_temp(temp_dir: Path) -> None:
    if not temp_dir.exists():
        return
    for item in temp_dir.iterdir():
        if item.is_file():
            item.unlink(missing_ok=True)
    temp_dir.rmdir()
    parent = temp_dir.parent
    if parent.name == ".upload_tmp" and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


@app.post("/api/shop-images/batch-upload")
async def batch_upload_shop_images(
    request: Request,
    shop_id: str = Form(...),
    sku: str = Form(""),
    overwrite: bool = Form(False),
    files: list[UploadFile] = File(...),
    relative_paths: list[str] | None = Form(None),
):
    """Upload images only into a shop that the current user can access."""
    shop = _authorized_shop(request, shop_id)
    if shop is None:
        return JSONResponse(
            {"error": "店铺未初始化或不在当前用户的紫鸟权限范围内"},
            status_code=403,
        )
    if not files:
        return JSONResponse({"error": "请选择图片文件"}, status_code=400)
    if len(files) > MAX_IMAGE_BATCH_FILES:
        return JSONResponse(
            {"error": f"单批最多 {MAX_IMAGE_BATCH_FILES} 个文件，请拆分上传"},
            status_code=413,
        )

    image_root = Path(str(shop["image_root"])).resolve()
    try:
        configured_root = _shop_root()
        if os.path.commonpath([str(configured_root), str(image_root)]) != str(configured_root):
            raise ValueError("店铺图片目录不在固定扫描根目录内")
    except (ValueError, OSError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    batch_id = secrets.token_hex(16)
    temp_dir = image_root / ".upload_tmp" / batch_id
    temp_dir.mkdir(parents=True, exist_ok=False)
    user_id, username, request_id = _erp_actor(request)
    try:
        repository.create_file_batch(
            batch_id=batch_id,
            request_id=request_id,
            user_id=user_id,
            username=username,
            shop_id=str(shop["ziniao_shop_id"]),
            shop_name=str(shop["ziniao_shop_name"]),
            shop_folder=str(shop["path"]),
            requested_files=len(files),
        )
    except Exception as exc:
        _cleanup_batch_temp(temp_dir)
        return JSONResponse(
            {"error": f"创建图片上传审计记录失败: {exc}"}, status_code=500
        )

    staged: list[tuple[Path, str, str, int]] = []
    seen_targets: set[tuple[str, str]] = set()
    total_bytes = 0
    saved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        for index, upload in enumerate(files):
            relative = (
                relative_paths[index]
                if relative_paths and index < len(relative_paths)
                else ""
            )
            target_sku, filename = _batch_target(upload, relative, sku)
            target_key = (target_sku.casefold(), filename.casefold())
            if target_key in seen_targets:
                raise ValueError(f"批次内存在重复图片: {target_sku}/{filename}")
            seen_targets.add(target_key)

            staged_path = temp_dir / f"{index:04d}{Path(filename).suffix.lower()}"
            file_bytes = 0
            with staged_path.open("wb") as output:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if file_bytes > MAX_IMAGE_BYTES:
                        raise ValueError(f"单张图片不能超过30MB: {filename}")
                    if total_bytes > MAX_IMAGE_BATCH_BYTES:
                        raise ValueError("单批图片总大小不能超过45MB，请拆分上传")
                    output.write(chunk)
            if file_bytes == 0:
                raise ValueError(f"图片为空文件: {filename}")
            staged.append((staged_path, target_sku, filename, file_bytes))

        async with _shop_file_lock(str(shop["ziniao_shop_id"])):
            for staged_path, target_sku, filename, file_bytes in staged:
                sku_dir = (image_root / target_sku).resolve()
                if os.path.commonpath([str(image_root), str(sku_dir)]) != str(image_root):
                    raise ValueError("非法SKU目录")
                sku_dir.mkdir(parents=True, exist_ok=True)
                target = (sku_dir / filename).resolve()
                if os.path.commonpath([str(sku_dir), str(target)]) != str(sku_dir):
                    raise ValueError("非法图片路径")
                if target.exists() and not overwrite:
                    skipped.append({"sku": target_sku, "name": filename, "reason": "已存在"})
                    continue
                os.replace(staged_path, target)
                saved.append({"sku": target_sku, "name": filename, "bytes": file_bytes})

        _cleanup_batch_temp(temp_dir)
        shop["has_images"] = _image_root_has_images(image_root)
        repository.finish_file_batch(
            batch_id,
            status="completed",
            saved_files=len(saved),
            skipped_files=len(skipped),
            total_bytes=total_bytes,
        )
        return {
            "ok": True,
            "batch_id": batch_id,
            "shop_id": shop["ziniao_shop_id"],
            "saved_count": len(saved),
            "skipped_count": len(skipped),
            "total_bytes": total_bytes,
            "saved": saved,
            "skipped": skipped,
        }
    except ValueError as exc:
        _cleanup_batch_temp(temp_dir)
        repository.finish_file_batch(
            batch_id,
            status="partial" if saved else "failed",
            saved_files=len(saved),
            skipped_files=len(skipped),
            total_bytes=total_bytes,
            error_message=str(exc),
        )
        return JSONResponse(
            {
                "error": str(exc),
                "batch_id": batch_id,
                "saved_count": len(saved),
                "skipped_count": len(skipped),
            },
            status_code=400,
        )
    except Exception as exc:
        try:
            _cleanup_batch_temp(temp_dir)
        except Exception:
            pass
        repository.finish_file_batch(
            batch_id,
            status="partial" if saved else "failed",
            saved_files=len(saved),
            skipped_files=len(skipped),
            total_bytes=total_bytes,
            error_message=str(exc),
        )
        return JSONResponse(
            {
                "error": f"批量保存图片失败: {exc}",
                "batch_id": batch_id,
                "saved_count": len(saved),
                "skipped_count": len(skipped),
            },
            status_code=500,
        )
def _validated_image_selection(
    image_root: str,
    selected_skus: list[str],
    raw_selection: Any,
) -> dict[str, list[str]]:
    if not isinstance(raw_selection, dict):
        raise ValueError("请展开SKU图片并勾选本次要上传的图片")
    normalized: dict[str, list[str]] = {}
    for sku in selected_skus:
        _checked_upload_component(sku, "SKU")
        requested = raw_selection.get(sku)
        if not isinstance(requested, list) or not requested:
            raise ValueError(f"SKU {sku} 尚未选择任何图片")
        requested_names = {
            _checked_upload_component(str(name), "图片文件名").casefold()
            for name in requested
        }
        available_paths = get_sku_images(sku, image_root)
        selected_paths = [
            path
            for path in available_paths
            if os.path.basename(path).casefold() in requested_names
        ]
        if len(selected_paths) != len(requested_names):
            raise ValueError(f"SKU {sku} 的图片选择已失效，请重新预览并勾选")
        normalized[sku] = [os.path.basename(path) for path in selected_paths]
    return normalized


@app.post("/api/upload/start")
async def start_upload(data: dict, request: Request):
    """Create a single-shop job and use a free port or enter the FIFO queue."""
    try:
        runtime_config = _config_for_request(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    config_error = _ziniao_config_error(runtime_config)
    if config_error:
        return JSONResponse({"error": config_error}, status_code=400)

    shop_id = str(data.get("shop_id") or "").strip()
    authorized = _authorized_shop(request, shop_id)
    if authorized is None:
        return JSONResponse(
            {"error": "店铺不在当前用户已初始化的紫鸟权限范围内"}, status_code=403
        )
    excel_path = str(authorized.get("excel") or "")
    image_root = str(authorized.get("image_root") or "")
    if not excel_path or not os.path.isfile(excel_path):
        return JSONResponse({"error": "该店铺目录中没有SKU Excel文件"}, status_code=400)
    if not image_root or not os.path.isdir(image_root):
        return JSONResponse({"error": "该店铺图片目录不存在"}, status_code=400)

    marketplace = _get_marketplace(runtime_config)
    sku_col = str((runtime_config.get("excel", {}) or {}).get("sku_column", "SKU"))
    try:
        total_sku = len(read_skus(excel_path, sku_col))
    except Exception as exc:
        return JSONResponse({"error": f"读取SKU失败: {exc}"}, status_code=400)
    user_id, username, request_id = _erp_actor(request)
    task_id = repository.create_task(
        request_id=request_id,
        user_id=user_id,
        username=username,
        marketplace_code=marketplace["code"],
        shop_count=1,
        total_sku=total_sku,
        payload=_safe_task_payload([{"shop_id": shop_id, "selected_skus": []}]),
    )
    _log("INFO", f"提交上传任务 #{task_id}，店铺: {authorized['ziniao_shop_name']}", task_id)
    started, position = _enqueue_upload({
        "kind": "single",
        "task_id": task_id,
        "excel_path": excel_path,
        "image_root": image_root,
        "marketplace": marketplace,
        "shop_id": shop_id,
        "runtime_config": runtime_config,
        "user_id": user_id,
    })
    message = "任务已启动" if started else f"5个端口均忙，当前排队第 {position} 位"
    return {
        "ok": True,
        "task_id": task_id,
        "started": started,
        "queued": not started,
        "queue_position": position,
        "msg": message,
    }


@app.post("/api/upload/start_multi")
async def start_multi_upload(data: dict, request: Request):
    """Create a multi-shop job using server-derived authorized paths."""
    try:
        runtime_config = _config_for_request(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    config_error = _ziniao_config_error(runtime_config)
    if config_error:
        return JSONResponse({"error": config_error}, status_code=400)

    requested = data.get("shop_tasks") or []
    if not requested:
        return JSONResponse({"error": "请先选择要上传的店铺"}, status_code=400)
    sku_col = str((runtime_config.get("excel", {}) or {}).get("sku_column", "SKU"))
    valid_tasks: list[dict[str, Any]] = []
    seen_shop_ids: set[str] = set()
    for requested_task in requested:
        shop_id = str(requested_task.get("shop_id") or "").strip()
        if not shop_id or shop_id in seen_shop_ids:
            continue
        authorized = _authorized_shop(request, shop_id)
        if authorized is None:
            return JSONResponse(
                {"error": f"店铺 {shop_id} 不在当前用户权限范围内"}, status_code=403
            )
        seen_shop_ids.add(shop_id)
        excel_path = str(authorized.get("excel") or "")
        image_root = str(authorized.get("image_root") or "")
        if not excel_path or not os.path.isfile(excel_path):
            return JSONResponse(
                {"error": f"店铺 {authorized['ziniao_shop_name']} 缺少SKU Excel文件"},
                status_code=400,
            )
        selected_skus = list(dict.fromkeys(
            str(item).strip() for item in (requested_task.get("selected_skus") or [])
            if str(item).strip()
        ))
        if not selected_skus:
            return JSONResponse(
                {"error": f"店铺 {authorized['ziniao_shop_name']} 尚未选择SKU图片"},
                status_code=400,
            )
        try:
            excel_skus = set(read_skus(excel_path, sku_col))
        except Exception as exc:
            return JSONResponse({"error": f"读取SKU失败: {exc}"}, status_code=400)
        unknown_skus = [sku for sku in selected_skus if sku not in excel_skus]
        if unknown_skus:
            return JSONResponse(
                {"error": f"以下SKU不在店铺Excel中: {', '.join(unknown_skus[:10])}"},
                status_code=400,
            )
        try:
            selected_images = _validated_image_selection(
                image_root,
                selected_skus,
                requested_task.get("selected_images"),
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        valid_tasks.append({
            "shop_id": shop_id,
            "shop_name": str(authorized.get("ziniao_shop_name") or shop_id),
            "excel_path": excel_path,
            "image_root": image_root,
            "selected_skus": selected_skus,
            "selected_images": selected_images,
        })
    if not valid_tasks:
        return JSONResponse({"error": "没有有效的店铺任务"}, status_code=400)

    marketplace = _get_marketplace(runtime_config)
    total_sku = sum(len(task["selected_skus"]) for task in valid_tasks)

    user_id, username, request_id = _erp_actor(request)
    task_id = repository.create_task(
        request_id=request_id,
        user_id=user_id,
        username=username,
        marketplace_code=marketplace["code"],
        shop_count=len(valid_tasks),
        total_sku=total_sku,
        payload=_safe_task_payload(valid_tasks),
    )
    _log("INFO", f"提交多店铺任务 #{task_id}，共 {len(valid_tasks)} 个店铺", task_id)
    started, position = _enqueue_upload({
        "kind": "multi",
        "task_id": task_id,
        "shop_tasks": valid_tasks,
        "marketplace": marketplace,
        "runtime_config": runtime_config,
        "user_id": user_id,
    })
    message = (
        f"多店铺任务已启动，共 {len(valid_tasks)} 个店铺"
        if started
        else f"5个端口均忙，当前排队第 {position} 位"
    )
    return {
        "ok": True,
        "task_id": task_id,
        "started": started,
        "queued": not started,
        "queue_position": position,
        "msg": message,
        "count": len(valid_tasks),
    }


@app.post("/api/upload/stop")
async def stop_upload(request: Request):
    """停止上传任务（优雅停止）。"""
    user_id, _, _ = _erp_actor(request)
    latest = repository.latest_task(user_id)
    if not latest:
        return {"ok": False, "msg": "没有运行中或排队中的任务"}
    task_id = int(latest["task_id"])
    with _task_lock:
        if str(latest.get("status")) == "queued":
            for pending in list(_pending_uploads):
                if int(pending["task_id"]) == task_id:
                    _pending_uploads.remove(pending)
                    timer = pending.pop("expiry_timer", None)
                    if timer is not None:
                        timer.cancel()
                    pending.setdefault("runtime_config", {}).setdefault("ziniao", {})[
                        "password"
                    ] = ""
                    stopped = repository.stop_queued_task(task_id, user_id)
                    return {
                        "ok": stopped,
                        "task_id": task_id,
                        "msg": "排队任务已取消" if stopped else "任务状态已变化",
                    }
        active = _active_uploads.get(task_id)
        if active:
            active["stop_requested"] = True
            upload_app = active.get("app")
            if upload_app is not None:
                upload_app.stop()
            _log("WARNING", "已发送停止请求，将在当前步骤完成后退出", task_id)
            return {"ok": True, "task_id": task_id, "msg": "停止请求已发送"}
    return {"ok": False, "msg": "没有运行中的任务"}


@app.get("/api/upload/status")
async def upload_status(request: Request):
    """获取当前上传状态。"""
    state = _user_state(request)
    user_id, _, _ = _erp_actor(request)
    completed = _load_completed(user_id)
    latest = repository.latest_task(user_id)
    latest_status = str(latest.get("status")) if latest else ""
    queue_position = (
        repository.queue_position(int(latest["task_id"]))
        if latest and latest_status == "queued"
        else 0
    )
    with _task_lock:
        active_count = len(_active_uploads)
        queued_count = len(_pending_uploads)
    return {
        "running": latest_status == "running",
        "queued": latest_status == "queued",
        "queue_position": queue_position,
        "active_count": active_count,
        "queued_count": queued_count,
        "max_concurrent": MAX_AUTOMATION_SLOTS,
        "task": latest,
        "completed_count": len(completed),
        "cached_skus": len(state["cached_skus"]),
        "excel_path": state["cached_excel_path"],
        "image_root": state["cached_image_root"],
    }


@app.post("/api/progress/clear")
async def clear_progress(request: Request):
    """清除断点续传进度。"""
    user_id, _, _ = _erp_actor(request)
    latest = repository.latest_task(user_id)
    if latest and str(latest.get("status")) in {"queued", "running"}:
        return JSONResponse({"error": "任务运行中不能清除断点记录"}, status_code=409)
    deleted = repository.clear_progress(user_id)
    _log("WARNING", f"已清除 {deleted} 条历史断点记录")
    return {"ok": True, "deleted": deleted}


@app.get("/api/progress")
async def get_progress(request: Request):
    """获取已完成的任务列表。"""
    user_id, _, _ = _erp_actor(request)
    completed = _load_completed(user_id)
    return {"completed": sorted(completed), "count": len(completed)}


# ---------------------------------------------------------------------------
# 日志 API
# ---------------------------------------------------------------------------
@app.get("/api/logs")
async def get_logs(request: Request, limit: int = 200):
    """获取历史日志。"""
    user_id, _, _ = _erp_actor(request)
    latest = repository.latest_task(user_id)
    if not latest:
        return {"logs": []}
    rows = repository.task_logs(int(latest["task_id"]), limit, user_id)
    return {
        "task_id": latest["task_id"],
        "logs": [
            {
                "time": row["created_at"].strftime("%H:%M:%S"),
                "level": row["level"],
                "msg": row["message"],
            }
            for row in rows
        ],
    }


@app.get("/api/tasks")
async def get_tasks(request: Request, limit: int = 30):
    user_id, _, _ = _erp_actor(request)
    return {"items": repository.list_tasks(limit, user_id)}


@app.get("/api/tasks/{task_id}/logs")
async def get_task_logs(request: Request, task_id: int, limit: int = 500):
    user_id, _, _ = _erp_actor(request)
    return {"task_id": task_id, "logs": repository.task_logs(task_id, limit, user_id)}


# ---------------------------------------------------------------------------
# WebSocket —— 实时日志 + 进度
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    configured_token = settings.python_internal_api_token
    provided_token = ws.headers.get("X-Internal-Token", "")
    client_host = ws.client.host if ws.client else ""
    if configured_token:
        if not provided_token or not secrets.compare_digest(provided_token, configured_token):
            await ws.close(code=4401)
            return
    elif client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        await ws.close(code=4403)
        return
    await ws.accept()
    with _ws_lock:
        _ws_clients.add(ws)

    # 发送当前状态
    await ws.send_text(json.dumps({
        "type": "status",
        "data": {"running": _any_upload_running()},
    }, ensure_ascii=False))

    # 发送最近日志
    await ws.send_text(json.dumps({
        "type": "log_batch",
        "data": _log_buffer[-100:],
    }, ensure_ascii=False))

    try:
        while True:
            # 保持连接，接收心跳
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        with _ws_lock:
            _ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# 启动时初始化
# ---------------------------------------------------------------------------
_runtime_started = False


async def initialize_runtime() -> None:
    global _runtime_started
    if _runtime_started:
        return
    _runtime_started = True
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "data").mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "logs").mkdir(parents=True, exist_ok=True)
    repository.recover_interrupted_tasks()

    # 启动 WebSocket 广播协程
    asyncio.create_task(_broadcast_worker())

    # 把 src 模块（ziniao_client/amazon_bot/app）的 loguru 日志转发到前端
    from loguru import logger as loguru_logger
    def _loguru_sink(message):
        record = message.record
        module = record.get("module", "")
        # 只转发核心模块的日志，避免 uvicorn/fastapi 等噪音
        if module in ("ziniao_client", "amazon_bot", "config_loader", "excel_reader", "image_loader"):
            level = record["level"].name
            msg = record["message"]
            _log(level, msg)
    loguru_logger.add(_loguru_sink, level="DEBUG", enqueue=True)

    _log("INFO", "Amazon主图批量上传子应用已启动")
    _log("INFO", f"运行数据目录: {RUNTIME_DIR}")


@app.on_event("startup")
async def startup():
    await initialize_runtime()
