"""谷仓区域仓库存同步：get_product_inventory（V1）全量拉取，校验后单事务整表替换。

价格分析看板的海外仓库存（DE / UK / USEA / USWE）以这张表为准，成都中转仓仍用领星。

- 分页、认证、请求间隔、重试复用 GoodcangClient；每页 200 条。
- V1 响应校验：ask 必须是 Success；翻页过程中 count 不许变；data 为 null 或空数组即结束；
  分页提前结束、越界、同一 (仓, SKU) 重复出现都判失败，不提交半份快照。
- 空快照保护：count 为 0 或最终 0 行直接判失败，不替换表 —— 接口偶发返回空会把看板库存整片清零。
- 单事务整表替换：本任务不和价格分析刷表共锁，靠「先删后插在同一个事务里」保证读方
  在一致性读下只看到旧表或新表。
- 所有区域仓原样落库（含 CZ、IT 等），缺值留 NULL 不补零；站点映射与过滤在 DWS 里做。
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import islice
from typing import Any, Callable, Iterator
from uuid import uuid4

from backend.database import db_connection
from backend.integrations.goodcang.client import (
    INVENTORY_PAGE_SIZE, INVENTORY_PATH, GoodcangClient, source_json,
)

TASK_CODE = "goodcang_product_inventory_sync"
TASK_NAME = "谷仓区域仓库存同步"
TABLE = "ods_goodcang_product_inventory_latest"
CHINA_TIME = timezone(timedelta(hours=8))
LOG = logging.getLogger(__name__)
MAX_PAGES = 1000
_INSERT_BATCH = 500

TEXT_LIMITS = {"warehouse_code": 32, "warehouse_desc": 255, "product_sku": 255, "product_title": 1000}
INTEGER_FIELDS = (
    "sellable", "reserved", "onway", "transfer_onway", "total_onway", "pending", "unsellable",
    "pi_freeze", "stocking", "pi_warning_qty", "pi_no_stock", "product_type",
)
COLUMNS = (*TEXT_LIMITS, *INTEGER_FIELDS, "raw_json", "sync_batch_id", "pulled_at")


class GoodcangProductInventorySyncError(ValueError):
    """带 stage / metrics，调度器据此还原失败运行记录。"""

    def __init__(self, stage: str, message: str, metrics: dict[str, Any]):
        super().__init__(message)
        self.stage = stage
        self.metrics = dict(metrics)


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("谷仓库存接口 count 必须为非负整数")
    text = str(value)
    if not text.isascii() or not text.isdigit():
        raise ValueError("谷仓库存接口 count 必须为非负整数")
    result = int(text)
    if result > MAX_PAGES * INVENTORY_PAGE_SIZE:
        raise ValueError("谷仓库存接口 count 超过分页安全上限")
    return result


def _integer(value: Any, field: str) -> int | None:
    """缺值留 NULL，不补零；小数、布尔、非数字一律拒绝，不静默取整。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{field} 必须为整数")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"{field} 必须为整数") from None
    if (not number.is_finite() or number != number.to_integral_value()
            or not Decimal("-9223372036854775808") <= number <= Decimal("9223372036854775807")):
        raise ValueError(f"{field} 不是有效 BIGINT 整数")
    return int(number)


def _row(source: dict[str, Any], *, batch_id: str, pulled_at: datetime) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field, limit in TEXT_LIMITS.items():
        value = source.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            raise ValueError(f"{field} 类型或长度异常")
        row[field] = value.strip() if isinstance(value, str) and field in ("warehouse_code", "product_sku") else value
    if not row["warehouse_code"] or not row["product_sku"]:
        raise ValueError("库存行缺少 warehouse_code 或 product_sku")
    row.update({field: _integer(source.get(field), field) for field in INTEGER_FIELDS})
    row.update(raw_json=source_json(source), sync_batch_id=batch_id, pulled_at=pulled_at)
    return row


def _pages(fetch: Callable[[int], Any], metrics: dict[str, Any]) -> Iterator[dict[str, Any]]:
    expected = None
    received = 0
    for page in range(1, MAX_PAGES + 1):
        metrics["current_page"] = page
        response = fetch(page)
        metrics["page_count"] += 1
        context = f"接口={INVENTORY_PATH} page={page}"
        if not isinstance(response, dict) or response.get("ask") != "Success":
            ask = response.get("ask") if isinstance(response, dict) else None
            raise ValueError(f"谷仓库存V1接口未返回ask=Success（ask={ask}）；{context}")
        count = _count(response.get("count"))
        if expected is not None and expected != count:
            raise ValueError(f"谷仓库存拉取期间count发生变化（{expected}→{count}）；{context}")
        expected = count
        metrics["api_count"] = count
        data = response.get("data")
        if data is None:
            data = []
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError(f"谷仓库存data必须为对象数组；{context}")
        if not data:
            # 文档约定 null / [] 表示无数据或超出页码；这里必须正好收齐 count 条。
            if received != count:
                raise ValueError(f"谷仓库存分页提前结束：已收{received}条，count={count}；{context}")
            return
        if len(data) > INVENTORY_PAGE_SIZE or received + len(data) > count:
            raise ValueError(f"谷仓库存分页数量越界；{context}")
        if received + len(data) < count and len(data) < INVENTORY_PAGE_SIZE:
            raise ValueError(f"谷仓库存分页提前结束；{context}")
        yield from data
        received += len(data)
        if received == count:
            return
    raise ValueError(f"谷仓库存超过分页安全上限；接口={INVENTORY_PATH}")


def replace_snapshot(rows: list[dict[str, Any]]) -> dict[str, int]:
    """单事务整表替换：先删后插、写完按行数复核，任何一步失败整体回滚，读方只见旧表或新表。"""
    names = ",".join(f"`{column}`" for column in COLUMNS)
    placeholders = ",".join(f"%({column})s" for column in COLUMNS)
    insert = f"INSERT INTO `{TABLE}` ({names}) VALUES ({placeholders})"
    with db_connection() as connection:
        # 显式 begin：避免连接池在单条 DELETE 之后自动重连重放。
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{TABLE}`")
                deleted = cursor.rowcount
                iterator = iter(rows)
                while batch := list(islice(iterator, _INSERT_BATCH)):
                    cursor.executemany(insert, batch)
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{TABLE}`")
                stored = int((cursor.fetchone() or {}).get("n") or 0)
                if stored != len(rows):
                    raise ValueError(f"谷仓库存写入行数校验失败：本次{len(rows)}行，库里{stored}行，已回滚")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"ods_rows": stored, "inserted_rows": stored, "deleted_rows": deleted}


def sync_goodcang_product_inventory(
    *,
    client_factory: Callable[[], GoodcangClient] = GoodcangClient,
    replace: Callable[[list[dict[str, Any]]], dict[str, int]] | None = None,
) -> dict[str, Any]:
    replace = replace or replace_snapshot
    batch_id = str(uuid4())
    pulled_at = datetime.now(CHINA_TIME).replace(tzinfo=None, microsecond=0)
    metrics: dict[str, Any] = {
        "sync_batch_id": batch_id, "pulled_at": pulled_at.strftime("%Y-%m-%d %H:%M:%S"),
        "extract_rows": 0, "ods_rows": 0, "inserted_rows": 0, "deleted_rows": 0,
        "api_count": None, "page_count": 0, "current_page": 0, "page_size": INVENTORY_PAGE_SIZE,
        "warehouse_counts": {}, "warehouse_sellable": {},
    }
    stage = "EXTRACT"
    try:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        with client_factory() as client:
            for source in _pages(client.fetch_product_inventory_page, metrics):
                row = _row(source, batch_id=batch_id, pulled_at=pulled_at)
                key = (row["warehouse_code"], row["product_sku"])
                if key in seen:
                    raise ValueError(f"谷仓库存同一(仓,SKU)重复出现：{key[0]} {key[1]}")
                seen.add(key)
                rows.append(row)
        metrics["extract_rows"] = len(rows)
        if not metrics["api_count"] or not rows:
            raise ValueError("谷仓库存接口返回空快照（count=0 或 0 行），按失败处理，未替换表")
        counts = Counter(row["warehouse_code"] for row in rows)
        sellable: Counter = Counter()
        for row in rows:
            sellable[row["warehouse_code"]] += row["sellable"] or 0
        metrics["warehouse_counts"] = dict(sorted(counts.items()))
        metrics["warehouse_sellable"] = dict(sorted(sellable.items()))
        stage = "LOAD"
        metrics.update(replace(rows))
        LOG.info("谷仓区域仓库存同步完成 batch=%s rows=%s pages=%s warehouses=%s",
                 batch_id, metrics["ods_rows"], metrics["page_count"], metrics["warehouse_counts"])
        return metrics
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else f"exception_type={type(exc).__name__}"
        message = (f"谷仓区域仓库存同步失败：{reason}；stage={stage} batch={batch_id} "
                   f"page={metrics['current_page']}")
        LOG.error("%s", message)
        raise GoodcangProductInventorySyncError(stage, message, metrics) from None
