"""In-memory helpers for the Amazon image-upload runtime configuration."""
from __future__ import annotations

from typing import Any

def get_marketplaces(cfg: dict[str, Any]) -> list[dict[str, str]]:
    """返回站点列表 [{code,name,domain}, ...]。"""
    return cfg.get("marketplaces", []) or []


def get_path(cfg: dict[str, Any], key: str) -> str:
    """读取 paths 下的某项，返回字符串。"""
    return str((cfg.get("paths", {}) or {}).get(key, ""))


def set_path(cfg: dict[str, Any], key: str, value: str) -> None:
    """设置 paths 下的某项。"""
    cfg.setdefault("paths", {})[key] = value


def get_ziniao_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """读取紫鸟浏览器配置段。"""
    return cfg.get("ziniao", {}) or {}


def is_ziniao_configured(cfg: dict[str, Any]) -> bool:
    """检查紫鸟必要配置是否已填写。"""
    z = get_ziniao_cfg(cfg)
    return bool(z.get("company") and z.get("username") and z.get("password"))
