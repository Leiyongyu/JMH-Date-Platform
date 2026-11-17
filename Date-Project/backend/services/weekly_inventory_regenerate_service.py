"""Generate a new archive from an existing successful snapshot, without extraction."""
from __future__ import annotations

import logging
from uuid import uuid4

from backend.repositories import weekly_inventory_repository as repo
from backend.services.weekly_inventory_export_service import export_root, write_export

LOG = logging.getLogger(__name__)
NO_SNAPSHOT = "暂无可用的成功库存快照，请先等待定时任务完成拉取；页面生成不会调用领星"


def regenerate_weekly_inventory():
    """Caller holds inventory:weekly-export for the entire operation."""
    source = repo.latest_completed_snapshot()
    if not source:
        raise ValueError(NO_SNAPSHOT)
    batch, day = source['sync_batch_id'], source['snapshot_date']
    # Keep the original snapshot identity; a distinct filename identifies this export.
    filename = f"仓位库存明细_{day}_重新生成_{uuid4()}.xlsx"
    path = export_root() / filename
    repo.begin_export(batch, day, filename, path, 'manual_snapshot')
    try:
        groups = repo.snapshot(batch)
        if not groups['inventory']:
            raise ValueError("所选库存快照已缺失，请先完成定时拉取")
        for rows in groups.values():
            if any(row.get('sync_batch_id') != batch or row.get('snapshot_date') != day for row in rows):
                raise ValueError("快照批次或日期不一致，拒绝混合导出")
        product_ids = {row['product_id'] for row in groups['products']}
        if not {row['product_id'] for row in groups['inventory']}.issubset(product_ids):
            raise ValueError("所选快照产品详情不完整，拒绝生成；请重新完成定时拉取")
        metrics = write_export(groups, repo.warehouse_names(), path)
        repo.finish_export(batch, file_name=filename, **metrics)
        return {'sync_batch_id': batch, 'snapshot_date': str(day), 'file_name': filename,
                'extract_rows': 0, 'ods_rows': 0, 'source_mode': 'existing_snapshot', **metrics}
    except Exception:
        LOG.exception("Snapshot export failed, batch=%s file=%s", batch, filename)
        try:
            repo.finish_export(batch, file_name=filename,
                               error=f"已有快照生成失败，批次{batch}；请查看任务日志；原文件和快照保留")
        except Exception:
            LOG.exception("Snapshot export failure registration failed, file=%s", filename)
        raise
