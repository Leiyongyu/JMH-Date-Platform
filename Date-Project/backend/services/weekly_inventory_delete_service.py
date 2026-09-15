"""Explicit permanent deletion of one generated Excel, never its source snapshot."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.repositories import weekly_inventory_repository as repo
from backend.repositories.performance_repository import named_lock
from backend.services.weekly_inventory_export_service import export_root

LOG = logging.getLogger(__name__)


class WeeklyFileDeleteConflict(ValueError):
    pass


def _file_path(record):
    """Resolve the exact registered .xlsx; disallow directories/links/path escape."""
    root = export_root().resolve()
    filename = record.get('file_name')
    stored_path = record.get('file_path')
    if not isinstance(filename, str) or not isinstance(stored_path, str):
        raise ValueError('周报文件路径不合法，拒绝删除')
    path = Path(stored_path)
    if (not path.is_absolute() or path.name != filename
            or path.suffix.lower() != '.xlsx' or path.parent.resolve() != root
            or path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
            or path.resolve() != root / filename
            or (path.exists() and not path.is_file())):
        raise ValueError('周报文件路径不合法，拒绝删除')
    return path


def delete_weekly_inventory_file(file_id: int):
    if not isinstance(file_id, int) or isinstance(file_id, bool) or file_id <= 0:
        raise ValueError('文件编号不合法')
    # Serialize with both scheduled extraction/generation and manual generation.
    with named_lock('inventory:weekly-export') as acquired:
        if not acquired:
            raise WeeklyFileDeleteConflict('周报正在生成或处理其他文件，请稍后再删除')
        record = repo.file_record(file_id)
        if not record:
            raise FileNotFoundError('周报文件记录不存在')
        status = record.get('status')
        if status == 'DELETED':
            return {'file_id': file_id, 'message': '文件已删除，库存快照保留', 'already_deleted': True}
        if status not in {'SUCCESS', 'DELETE_PENDING'}:
            raise WeeklyFileDeleteConflict('只能删除已生成的文件；生成中或失败的记录不可删除')
        path = _file_path(record)
        if status == 'SUCCESS':
            repo.mark_file_delete_pending(file_id)
        # No recursive deletion, no glob, no user-supplied path. If the process
        # stops before the final update, retry DELETE_PENDING idempotently.
        missing = False
        try:
            path.unlink()
        except FileNotFoundError:
            missing = True
        except OSError:
            LOG.warning('Weekly file deletion pending, file_id=%s', file_id)
            raise WeeklyFileDeleteConflict('文件暂时无法删除，可能被占用；请关闭相关文件后重试') from None
        repo.mark_file_deleted(file_id)
        LOG.info('Weekly Excel permanently deleted, file_id=%s already_missing=%s', file_id, missing)
        return {'file_id': file_id, 'message': 'Excel文件已永久删除，当前保留的最新快照不受影响；旧文件无法直接恢复',
                'already_missing': missing}
