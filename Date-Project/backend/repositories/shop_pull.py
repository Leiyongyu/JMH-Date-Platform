"""向领星拉取数据时的店铺筛选（与 Java ShopListMapper.selectSidsByPlatform 口径一致）。

shop_list 上的拉取控制字段由 ERP「运营中心 > 同步管理 > 店铺管理」维护，领星店铺同步不会覆盖：
- lingxing_present=0：最近一次完整的店铺同步里领星已不再返回该店铺 → 一律不拉取；
- pull_enabled=0：人工停止拉取（封店、停店、主体注销等），pull_stop_date 为生效日期：
  - 不按月份拉取（当前快照类）的任务：立即不再拉取；
  - 按月份整月替换的任务：开始于停止日期之前的月份仍然拉取，重跑历史月份不会把该店铺当月数据删掉。

只用在「去领星拉数据」的地方；按 sid 查店铺名、读历史报表的地方不要用，否则停用店铺的历史数据会从报表里消失。
数据库还没有这些字段时（迁移未执行）返回空条件并记一次警告，保持原有行为。
"""
from __future__ import annotations

import logging
import threading
from datetime import date

LOG = logging.getLogger(__name__)
PULL_COLUMNS = ("pull_enabled", "pull_stop_date", "lingxing_present")
_lock = threading.Lock()
_columns_ready: dict[str, bool] = {}
_warned: dict[str, bool] = {}


def _has_columns(cursor, database: str | None) -> bool:
    key = database or ""
    with _lock:
        if key in _columns_ready:
            return _columns_ready[key]
    if database:
        cursor.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='shop_list'",
            (database,),
        )
    else:
        cursor.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list'"
        )
    names = {str(row["COLUMN_NAME"]).lower() for row in cursor.fetchall()}
    ready = all(column in names for column in PULL_COLUMNS)
    with _lock:
        warned = _warned.get(key, False)
        if ready:
            _columns_ready[key] = True  # 只缓存「已有字段」，迁移执行后不用重启即可生效
        else:
            _warned[key] = True
    if not ready and not warned:
        LOG.warning("shop_list 尚无拉取控制字段（%s），按原口径拉取全部店铺；请执行 ERP 迁移 20261105_shop_pull_control.sql",
                    database or "当前库")
    return ready


def month_start(month: str | None) -> date | None:
    if not month:
        return None
    year, number = (int(part) for part in month.split("-")[:2])
    return date(year, number, 1)


def pull_condition(cursor, database: str | None, *, month: str | None = None,
                   alias: str = "") -> tuple[str, tuple]:
    """返回追加到 WHERE 的 SQL 片段与参数；month 为 YYYY-MM 时按「整月拉取」口径。"""
    if not _has_columns(cursor, database):
        return "", ()
    prefix = f"{alias}." if alias else ""
    start = month_start(month)
    if start is None:
        return f" AND {prefix}lingxing_present = 1 AND {prefix}pull_enabled = 1", ()
    return (f" AND {prefix}lingxing_present = 1 AND ({prefix}pull_enabled = 1"
            f" OR ({prefix}pull_stop_date IS NOT NULL AND {prefix}pull_stop_date > %s))", (start,))


def reset_cache() -> None:
    with _lock:
        _columns_ready.clear()
        _warned.clear()
