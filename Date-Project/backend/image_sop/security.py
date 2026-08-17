"""Shared helpers: health response sanitization and CORS origin parsing.

Compatible with Python 3.6+ (replenishment runs on 3.6.8).
"""

from typing import Any, Dict, List, Optional
try:
    from urllib.parse import urlsplit
except ImportError:  # pragma: no cover - Python 2 compatibility fallback
    from urlparse import urlsplit

INTERNAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def client_is_internal(client_host, forwarded_for=""):
    # type: (Optional[str], str) -> bool
    if client_host in INTERNAL_HOSTS:
        return True
    first = (forwarded_for or "").split(",")[0].strip()
    return first in INTERNAL_HOSTS


def browser_request_is_same_origin(host, referer, sec_fetch_site=""):
    # type: (str, str, str) -> bool
    """Allow the directly served Image SOP page to call its own Python APIs."""
    if (sec_fetch_site or "").strip().lower() not in {"", "same-origin"}:
        return False
    try:
        parsed = urlsplit((referer or "").strip())
    except (TypeError, ValueError):
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.netloc.lower() != (host or "").strip().lower():
        return False
    path = parsed.path.rstrip("/")
    return path == "/image-sop" or path.startswith("/image-sop/")


def sanitize_health(payload):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """Public/minimal health payload for browser clients."""
    out = {
        "ok": bool(payload.get("ok")),
        "service": payload.get("service"),
    }  # type: Dict[str, Any]
    lingxing = payload.get("lingxing")
    if isinstance(lingxing, dict):
        lx = {}  # type: Dict[str, Any]
        if "configured" in lingxing:
            lx["configured"] = lingxing.get("configured")
        if "token_ok" in lingxing:
            lx["token_ok"] = lingxing.get("token_ok")
        if lingxing.get("token_ok") is False:
            lx["error"] = "领星连接异常"
        out["lingxing"] = lx
    queue = payload.get("queue")
    if isinstance(queue, dict) and queue.get("redis_ok") is False:
        out["queue"] = {"redis_ok": False}
    return out


def cors_origins_from_env(raw, default_host="8.137.177.25"):
    # type: (str, str) -> List[str]
    text = (raw or "").strip()
    if text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [
        "http://{}".format(default_host),
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
