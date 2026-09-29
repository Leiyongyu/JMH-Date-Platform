"""Incremental product-price imports, isolated from Lingxing procurement snapshots."""
from __future__ import annotations

from typing import Any

from pymysql.err import ProgrammingError

from backend.database import db_connection
from backend.repositories.performance_repository import named_lock


PRICE_TABLE = "ebay_inventory_detail_price"
_IMPORT_LOCK = "ebay_inventory_detail_price_import"
_BATCH_SIZE = 500
MAX_ROWS = 50_000
_TABLE_MISSING = "产品单价表尚未创建，请先执行 Ebay库存明细产品单价建表 SQL"


def _table_missing(exc: Exception) -> bool:
    return (
        isinstance(exc, ProgrammingError)
        and bool(exc.args)
        and exc.args[0] == 1146
        and PRICE_TABLE in str(exc)
    )


def replace_prices(rows: list[dict[str, Any]], operator: str, filename: str) -> int:
    """按上传核心码替换全部候选价，清掉同核心码未再上传的低价后缀SKU。

    同时清理本次完整SKU的旧映射，避免改核心码后留下旧价/唯一键冲突。
    所有删除与插入共用事务及导入锁；未涉及的核心码保持不变。
    """
    if not rows:
        return 0
    if len(rows) > MAX_ROWS:
        raise ValueError(f"产品单价导入超过{MAX_ROWS}行")

    source_file = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1][:255]
    distinct_skus = list(dict.fromkeys(row["sku"] for row in rows))
    core_codes = list(dict.fromkeys(row["middle_code"] for row in rows if row.get("middle_code")))
    params = [
        {
            "sku": row["sku"],
            "middle_code": row.get("middle_code"),
            "unit_price": row["unit_price"],
            "source_file": source_file,
            "updated_by": operator,
        }
        for row in rows
    ]
    insert_sql = f"""
        INSERT INTO {PRICE_TABLE}
            (sku,middle_code,unit_price,source_file,updated_by,created_at,updated_at)
        VALUES (%(sku)s,%(middle_code)s,%(unit_price)s,%(source_file)s,%(updated_by)s,
                NOW(),NOW())
    """

    with named_lock(_IMPORT_LOCK) as acquired:
        if not acquired:
            raise ValueError("正在导入产品单价，请稍后重试")
        with db_connection() as connection:
            try:
                connection.begin()
                with connection.cursor() as cursor:
                    for offset in range(0, len(core_codes), _BATCH_SIZE):
                        keys = core_codes[offset:offset + _BATCH_SIZE]
                        placeholders = ",".join(["%s"] * len(keys))
                        cursor.execute(
                            f"DELETE FROM {PRICE_TABLE} WHERE middle_code IN ({placeholders})",
                            tuple(keys),
                        )
                    for offset in range(0, len(distinct_skus), _BATCH_SIZE):
                        keys = distinct_skus[offset:offset + _BATCH_SIZE]
                        placeholders = ",".join(["%s"] * len(keys))
                        cursor.execute(
                            f"DELETE FROM {PRICE_TABLE} WHERE sku IN ({placeholders})",
                            tuple(keys),
                        )
                    for offset in range(0, len(params), _BATCH_SIZE):
                        cursor.executemany(insert_sql, params[offset:offset + _BATCH_SIZE])
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if _table_missing(exc):
                    raise ValueError(_TABLE_MISSING) from exc
                raise
    return len(rows)
