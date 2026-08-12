"""文件清理模块 — 保留最近 N 次生成的草稿及文件，删除其余。

用法：
  # 作为模块调用
  python -m app.cleanup

  # 代码中调用
  from backend.image_sop.cleanup import cleanup_keep_recent
  cleanup_keep_recent(keep_count=20)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保项目根目录在 sys.path 中（cron 调用时可能不包含）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.image_sop.config import get_settings
from backend.image_sop.repository import init_db, get_db

KEEP_COUNT = 20
EXPORT_KEEP_COUNT = 30
EXPORT_MAX_AGE_DAYS = 7


def _draft_payload(draft: dict) -> dict:
    """list_all_drafts 返回 {id, sku, created_at, data}，文件引用在 data 内。"""
    data = draft.get("data")
    if isinstance(data, dict):
        return data
    return draft


def _normalize_path(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


def _collect_referenced_files(draft: dict) -> set[str]:
    """收集单个草稿引用的所有本地文件路径"""
    payload = _draft_payload(draft)
    paths: set[str] = set()

    upload_path = payload.get("upload_path", "")
    if upload_path:
        paths.add(_normalize_path(str(upload_path)))

    for file_path in (payload.get("upload_files") or {}).values():
        if file_path:
            paths.add(_normalize_path(str(file_path)))

    for file_path in (payload.get("web_ref_files") or {}).values():
        if file_path:
            paths.add(_normalize_path(str(file_path)))

    return paths


def _delete_file_safe(file_path: str) -> int:
    """安全删除文件，返回释放的字节数（失败返回 0）"""
    try:
        p = Path(file_path)
        if not p.exists():
            return 0
        fsize = p.stat().st_size
        p.unlink()
        return fsize
    except OSError as exc:
        logger.warning("删除文件失败 %s: %s", file_path, exc)
        return 0


def _cleanup_orphan_files(settings, kept_files: set[str]) -> dict:
    """扫描上传/缓存目录，删除不被保留草稿引用的孤儿文件"""
    stats = {"deleted_files": 0, "freed_bytes": 0}

    scan_dirs = [
        settings.upload_path,
        settings.web_ref_path,
        settings.nas_cache_path,
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for entry in scan_dir.rglob("*"):
            if not entry.is_file():
                continue
            file_str = _normalize_path(str(entry))
            if file_str in kept_files:
                continue
            freed = _delete_file_safe(file_str)
            if freed:
                stats["deleted_files"] += 1
                stats["freed_bytes"] += freed

    return stats


def _cleanup_old_exports(
    settings,
    keep_count: int = EXPORT_KEEP_COUNT,
    max_age_days: int = EXPORT_MAX_AGE_DAYS,
) -> dict:
    """清理过期的 Excel 导出文件（按数量 + 天数双重限制）"""
    stats = {"deleted_files": 0, "freed_bytes": 0}
    export_dir = settings.export_path
    if not export_dir.exists():
        return stats

    import time

    cutoff = time.time() - max_age_days * 86400
    candidates = [
        p for p in export_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".xlsx"
    ]
    if not candidates:
        return stats

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for idx, path in enumerate(candidates):
        too_old = path.stat().st_mtime < cutoff
        over_limit = idx >= keep_count
        if not too_old and not over_limit:
            continue
        freed = _delete_file_safe(str(path))
        if freed:
            stats["deleted_files"] += 1
            stats["freed_bytes"] += freed

    composites = export_dir / "_composites"
    if composites.exists():
        for entry in composites.rglob("*"):
            if not entry.is_file():
                continue
            if entry.stat().st_mtime >= cutoff:
                continue
            freed = _delete_file_safe(str(entry))
            if freed:
                stats["deleted_files"] += 1
                stats["freed_bytes"] += freed

    return stats


def cleanup_keep_recent(keep_count: int = KEEP_COUNT) -> dict:
    """
    保留最近 keep_count 次生成的草稿及其关联文件，删除其余。

    返回统计: {"deleted_drafts": N, "deleted_files": N, "freed_bytes": N}
    """
    stats = {"deleted_drafts": 0, "deleted_files": 0, "freed_bytes": 0, "expired_drafts": 0}

    # 加载配置（若失败则退出，避免误删）
    try:
        settings = get_settings()
    except Exception as exc:
        logger.error("加载配置失败，终止清理: %s", exc)
        return stats

    # 确保数据库已初始化
    try:
        db = get_db()
    except RuntimeError:
        try:
            db = init_db(settings.db_file_path)
        except Exception as exc:
            logger.error("初始化数据库失败，终止清理: %s", exc)
            return stats

    try:
        stats["expired_drafts"] = db.clean_expired()
    except Exception as exc:
        logger.warning("清理过期草稿失败: %s", exc)
    try:
        db.clean_ai_profiles(max(1, settings.ai_profile_cache_ttl_hours) * 3600)
    except Exception as exc:
        logger.warning("清理 AI 产品分析缓存失败: %s", exc)

    try:
        export_stats = _cleanup_old_exports(settings)
        stats["deleted_files"] += export_stats["deleted_files"]
        stats["freed_bytes"] += export_stats["freed_bytes"]
    except Exception as exc:
        logger.warning("导出文件清理失败: %s", exc)

    try:
        drafts = db.list_all_drafts()
    except Exception as exc:
        logger.error("读取草稿列表失败，终止清理: %s", exc)
        return stats

    total_count = len(drafts)
    kept_drafts = drafts[:keep_count]
    deleted_drafts = drafts[keep_count:] if total_count > keep_count else []

    if not deleted_drafts:
        logger.info("当前草稿数 %d <= %d，跳过草稿删减", total_count, keep_count)

    if deleted_drafts:
        logger.info(
            "草稿总数 %d，保留 %d，待删除 %d",
            total_count, keep_count, len(deleted_drafts),
        )

    # 收集保留草稿引用的文件（这些不能删）
    kept_files: set[str] = set()
    for draft in kept_drafts:
        try:
            kept_files.update(_collect_referenced_files(draft))
        except Exception as exc:
            logger.warning(
                "收集保留草稿文件引用失败 (id=%s): %s",
                draft.get("id", "?"),
                exc,
            )

    # 草稿数未超限时仍清理未被任何草稿引用的孤儿文件
    if not deleted_drafts:
        try:
            orphan_stats = _cleanup_orphan_files(settings, kept_files)
            stats["deleted_files"] += orphan_stats["deleted_files"]
            stats["freed_bytes"] += orphan_stats["freed_bytes"]
        except Exception as exc:
            logger.warning("孤儿文件清理失败: %s", exc)
        freed_mb = stats["freed_bytes"] / 1024 / 1024 if stats["freed_bytes"] else 0
        logger.info(
            "清理完成: 过期草稿 %d, 删除文件 %d, 释放 %.1f MB",
            stats["expired_drafts"],
            stats["deleted_files"],
            freed_mb,
        )
        return stats

    # 删除不再被保留草稿引用的文件
    for draft in deleted_drafts:
        try:
            for file_path_str in _collect_referenced_files(draft):
                if file_path_str in kept_files:
                    continue  # 被其他保留草稿引用，跳过
                freed = _delete_file_safe(file_path_str)
                if freed:
                    stats["deleted_files"] += 1
                    stats["freed_bytes"] += freed
        except Exception as exc:
            logger.warning("删除过期草稿文件失败 (id=%s): %s",
                           draft.get("id", "?"), exc)

    # 删除数据库中过期的草稿记录
    try:
        deleted_ids = [d["id"] for d in deleted_drafts]
        stats["deleted_drafts"] = db.delete_drafts_batch(deleted_ids)
    except Exception as exc:
        logger.error("删除过期草稿记录失败: %s", exc)

    # 清理孤儿文件（物理存在但未被任何保留草稿引用的文件）
    try:
        orphan_stats = _cleanup_orphan_files(settings, kept_files)
        stats["deleted_files"] += orphan_stats["deleted_files"]
        stats["freed_bytes"] += orphan_stats["freed_bytes"]
    except Exception as exc:
        logger.warning("孤儿文件清理失败: %s", exc)

    freed_mb = stats["freed_bytes"] / 1024 / 1024 if stats["freed_bytes"] else 0
    logger.info(
        "清理完成: 删除 %d 条草稿, %d 个文件, 释放 %.1f MB",
        stats["deleted_drafts"],
        stats["deleted_files"],
        freed_mb,
    )
    return stats


# ── CLI 入口 ──

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    result = cleanup_keep_recent()
    print(
        f"清理完毕: 删除 {result['deleted_drafts']} 条草稿, "
        f"{result['deleted_files']} 个文件, "
        f"释放 {result['freed_bytes'] / 1024 / 1024:.1f} MB"
    )
