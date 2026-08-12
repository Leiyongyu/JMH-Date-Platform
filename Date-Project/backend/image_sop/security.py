"""Shared helpers: health response sanitization and CORS origin parsing.

Compatible with Python 3.6+ (replenishment runs on 3.6.8).
"""

from typing import Any, Dict, List, Optional

INTERNAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def client_is_internal(client_host, forwarded_for=""):
    # type: (Optional[str], str) -> bool
    if client_host in INTERNAL_HOSTS:
        return True
    first = (forwarded_for or "").split(",")[0].strip()
    return first in INTERNAL_HOSTS


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
