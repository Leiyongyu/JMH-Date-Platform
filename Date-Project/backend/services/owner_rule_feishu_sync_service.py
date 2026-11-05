"""负责人映射表从飞书多维表格自动同步（每周一 08:00，取代原来每月手工上传「负责人划分.xlsx」，上传入口已移除）。

飞书多维表格里的 6 张数据表与 Excel 模板的 6 个 Sheet 同名同结构（EU-店铺、EU-品牌、EU-OTH、US1、US2、EBAY；
第一列为匹配键，YYYYMM 列为当月负责人）。这里把每张表按字段顺序还原成与 Excel 一样的二维表，
交给同一个解析器和入库流程：重复/冲突校验、「待定」视为未分配、按月增量 upsert，口径与原来的上传一致。

飞书内容与上一次同步完全相同时直接跳过（不入库、不重算）；有变化时只重算负责人真正变化的月份。
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable
from uuid import uuid4

import pandas as pd

from backend.config import settings
from backend.integrations.feishu.client import FeishuClient, field_text
from backend.parsers.performance_owner_rule_parser import UNIFIED_OWNER_SHEETS, parse_unified_owner_rule_frames
from backend.repositories import performance_repository as repo

LOG = logging.getLogger(__name__)
TASK_CODE = "owner_rule_feishu_sync"
TASK_NAME = "负责人映射表飞书同步"
IMPORT_TYPE = "owner_rule_feishu"


def _cell(value: Any) -> str | None:
    text = field_text(value).strip()
    return text or None


def fetch_frames(client: FeishuClient, app_token: str) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """按表名取 6 张数据表，字段按飞书字段顺序排列（第一列是匹配键，与 Excel 一致）。"""
    tables = {t.get("name"): t.get("table_id") for t in client.list_tables(app_token)}
    missing = [name for name in UNIFIED_OWNER_SHEETS if name not in tables]
    if missing:
        raise ValueError(f"飞书负责人表缺少数据表：{'、'.join(missing)}（表名需与 Excel 模板的 Sheet 名一致）")
    frames, counts = {}, {}
    for name in UNIFIED_OWNER_SHEETS:
        table_id = tables[name]
        columns = [f.get("field_name") for f in client.list_fields(app_token, table_id) if f.get("field_name")]
        rows = []
        for record in client.iter_records(app_token, table_id):
            values = record.get("fields") or {}
            rows.append({column: _cell(values.get(column)) for column in columns})
        frames[name] = pd.DataFrame(rows, columns=columns, dtype=object)
        counts[name] = len(rows)
    return frames, counts


def fingerprint(frames: dict[str, pd.DataFrame]) -> bytes:
    """规范化后的表内容：表名、字段顺序、各行取值；用来判断与上次同步是否相同。"""
    payload = {
        name: {"columns": list(frame.columns),
               "rows": sorted(json.dumps(row, ensure_ascii=False, sort_keys=True)
                              for row in frame.where(pd.notna(frame), None).to_dict("records"))}
        for name, frame in sorted(frames.items())
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def changed_months(rules: list[dict[str, Any]], existing: dict[tuple, str]) -> set[str]:
    """与库里现有规则相比，负责人有变化（新增或改了负责人）的月份；只有这些月份需要重算绩效。"""
    months = set()
    for rule in rules:
        key = (rule["platform"], rule["stat_month"], rule["group_code"], rule["rule_type"], rule["match_key"])
        if key not in existing or (existing[key] or "") != (rule["principal_name"] or ""):
            months.add(rule["stat_month"])
    return months


def sync_owner_rules_from_feishu(
    *,
    client_factory: Callable[[], FeishuClient] = FeishuClient,
    apply: Callable[..., dict] | None = None,
    force: bool = False,
    request_id: str = "",
) -> dict[str, Any]:
    from backend.services.performance_service import apply_unified_owner_rules

    apply = apply or apply_unified_owner_rules
    app_token = settings.feishu_owner_rule_app_token.strip()
    if not app_token:
        raise ValueError("未配置 FEISHU_OWNER_RULE_APP_TOKEN（负责人映射表的多维表格 app_token）")
    client = client_factory()
    try:
        frames, counts = fetch_frames(client, app_token)
    finally:
        client.close()
    content = fingerprint(frames)
    content_hash = hashlib.sha256(content).hexdigest()
    fetched = sum(counts.values())
    if not force and repo.latest_import_hash(IMPORT_TYPE) == content_hash:
        LOG.info("负责人映射表飞书同步：内容与上次相同，跳过 rows=%s", fetched)
        return {"status": "unchanged", "fetched_rows": fetched, "table_rows": counts, "imported_rows": 0,
                "months": [], "refreshed_months": [], "content_hash": content_hash,
                # 调度框架记运行记录用的通用字段
                "extract_rows": fetched, "ods_rows": 0, "sync_batch_id": f"unchanged:{content_hash[:12]}"}
    batch_id = str(uuid4())
    source = f"飞书多维表格:{app_token}"
    parsed = parse_unified_owner_rule_frames(frames, source, content, batch_id)
    changed = changed_months(parsed["rules"], repo.owner_rule_snapshot(parsed["months"]))
    result = apply(parsed, batch_id, source, import_type=IMPORT_TYPE, rebuild=bool(changed),
                   operator="feishu-sync", request_id=request_id, only_months=changed)
    LOG.info("负责人映射表飞书同步完成 rows=%s rules=%s months=%s refreshed=%s", fetched,
             result.get("imported_rows"), len(result.get("months") or []), result.get("refreshed_months"))
    return {**result, "status": "completed", "fetched_rows": fetched, "table_rows": counts,
            "changed_months": sorted(changed),
            "content_hash": content_hash, "extract_rows": fetched, "ods_rows": int(result.get("imported_rows") or 0),
            "sync_batch_id": batch_id, "refresh": result.get("refresh") or {}}
