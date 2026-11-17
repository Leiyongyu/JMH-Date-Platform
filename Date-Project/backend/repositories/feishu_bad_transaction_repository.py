"""飞书「不良交易刊登」本地表的写入；整批一个事务，失败全回滚。"""
from __future__ import annotations

import hashlib
import json

from backend.database import db_connection

TABLE = "ods_feishu_bad_transaction_listing"
# 业务列，顺序即写入顺序。record_id 是主键，单独放在最前。
BUSINESS_COLUMNS = (
    "reg_date", "shop", "evaluate_date", "item_id", "title", "listing_status", "sku",
    "total_amount", "total_qty", "defect_qty", "inr_qty", "snad_qty",
    "neutral_negative_qty", "low_dsr_qty", "oos_cancel_qty", "defect_rate", "parent_json",
    "spare_date_1", "spare_date_2", "spare_date_3",
    "spare_text_4", "spare_text_5", "spare_text_6", "spare_text_7", "spare_text_8",
)
COLUMNS = ("record_id",) + BUSINESS_COLUMNS + ("feishu_created_at", "feishu_updated_at", "content_hash")
_BATCH_SIZE = 500


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=str)


def content_hash(row):
    """业务列的指纹；不含同步时间，否则每次都"变了"。

    只看 BUSINESS_COLUMNS：飞书的 last_modified_time 会因为无关操作（比如
    有人点开又保存）变化，拿它判"内容变没变"会把大量没改的行算成更新。
    """
    payload = dumps([str(row.get(column)) if row.get(column) is not None else None
                     for column in BUSINESS_COLUMNS])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def existing_hashes(cursor, record_ids):
    """取这些记录当前的内容指纹，用来分辨新增/更新/未变。"""
    known = {}
    ids = list(record_ids)
    for offset in range(0, len(ids), _BATCH_SIZE):
        chunk = ids[offset:offset + _BATCH_SIZE]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(f"SELECT record_id,content_hash FROM {TABLE} WHERE record_id IN ({placeholders})", chunk)
        known.update({r["record_id"]: r["content_hash"] for r in cursor.fetchall()})
    return known


def upsert(rows, *, batches=(), synced_at=None, full=False, month=""):
    """按 record_id 增量写入，并清理本次批次里飞书已删除的记录。

    内容没变的行只更新 last_synced_at，不动业务列、不动 last_changed_at——
    这样"上次真正变化是什么时候"才有意义。

    full=True 表示本次拉的是整张表，那么飞书没有的行一律删掉，包括登记日期为空的。
    按批次清理管不到没有登记日期的行，它们会永远残留：实测业务方把422行的空登记
    日期补成了1999-01-01（等于删旧行建新行），本地那422行旧记录一条也没被清掉。
    """
    if not rows:
        return {"inserted_rows": 0, "updated_rows": 0, "unchanged_rows": 0, "deleted_rows": 0}
    insert_sql = (
        f"INSERT INTO {TABLE} (" + ",".join(f"`{c}`" for c in COLUMNS)
        + ",first_synced_at,last_synced_at,last_changed_at) VALUES ("
        + ",".join(["%s"] * len(COLUMNS)) + ",%s,%s,%s) "
        + "ON DUPLICATE KEY UPDATE "
        + ",".join(f"`{c}`=VALUES(`{c}`)" for c in BUSINESS_COLUMNS)
        + ",feishu_created_at=VALUES(feishu_created_at)"
        ",feishu_updated_at=VALUES(feishu_updated_at)"
        ",content_hash=VALUES(content_hash)"
        ",last_synced_at=VALUES(last_synced_at)"
        ",last_changed_at=VALUES(last_changed_at)"
    )
    touch_sql = f"UPDATE {TABLE} SET last_synced_at=%s WHERE record_id IN ({{placeholders}})"
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                known = existing_hashes(cursor, (row["record_id"] for row in rows))
                changed, unchanged = [], []
                for row in rows:
                    before = known.get(row["record_id"])
                    (unchanged if before == row["content_hash"] else changed).append(row)
                inserted = sum(1 for row in changed if row["record_id"] not in known)

                for offset in range(0, len(changed), _BATCH_SIZE):
                    chunk = changed[offset:offset + _BATCH_SIZE]
                    cursor.executemany(insert_sql, [
                        tuple(row.get(c) for c in COLUMNS) + (synced_at, synced_at, synced_at)
                        for row in chunk])
                # 没变的行也要留个"这次确实见到了"的痕迹，好区分"没变"和"已从飞书消失"。
                for offset in range(0, len(unchanged), _BATCH_SIZE):
                    chunk = unchanged[offset:offset + _BATCH_SIZE]
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(touch_sql.format(placeholders=placeholders),
                                   [synced_at] + [row["record_id"] for row in chunk])

                seen = {row["record_id"] for row in rows}
                if full:
                    deleted = _reconcile_all(cursor, seen)
                elif month:
                    # 按月拉取时用月份对齐：整批在飞书被删光时，按批次清理会
                    # 因为那个批次不在本次结果里而漏掉它，月份范围能覆盖到。
                    deleted = _reconcile_month(cursor, month, seen)
                else:
                    deleted = _reconcile(cursor, batches, seen)
                _verify_written(cursor, [row["record_id"] for row in rows])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"inserted_rows": inserted, "updated_rows": len(changed) - inserted,
            "unchanged_rows": len(unchanged), "deleted_rows": deleted}


def _reconcile(cursor, batches, seen):
    """本次拉到的批次里，库里有、飞书没有的记录删掉。其他批次一行不碰。

    只按 reg_date 限定范围，所以历史批次和登记日期为空的记录都不会被误删。
    """
    deleted = 0
    for batch in batches:
        # 先取该批次库里的全部id，在Python里做差集：比拼一条超长的 NOT IN 更稳，
        # 参数个数只跟"要删的"有关，不跟"拉到的"有关。
        cursor.execute(f"SELECT record_id FROM {TABLE} WHERE reg_date=%s", (batch,))
        stale = [r["record_id"] for r in cursor.fetchall() if r["record_id"] not in seen]
        for offset in range(0, len(stale), _BATCH_SIZE):
            chunk = stale[offset:offset + _BATCH_SIZE]
            placeholders = ",".join(["%s"] * len(chunk))
            cursor.execute(f"DELETE FROM {TABLE} WHERE record_id IN ({placeholders})", chunk)
            deleted += cursor.rowcount
    return deleted


def _verify_written(cursor, record_ids):
    """写完确认这批 record_id 在库里一条不少，少了就整批回滚。

    防的是"静默少行"：record_id 大小写敏感，主键列若用了大小写不敏感的排序
    规则，rec...AHp 和 rec...ahP 会撞成同一行，后写的变成 UPDATE 前一条，
    行数对不上却不报错。这里当场拦住，而不是等人去对数才发现。
    """
    found = 0
    for offset in range(0, len(record_ids), _BATCH_SIZE):
        chunk = record_ids[offset:offset + _BATCH_SIZE]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(f"SELECT COUNT(*) AS n FROM {TABLE} WHERE record_id IN ({placeholders})", chunk)
        found += cursor.fetchone()["n"]
    if found != len(record_ids):
        raise ValueError(
            f"写入行数校验失败：本次{len(record_ids)}条，库里只查到{found}条。"
            f"最常见的原因是 record_id 列不是大小写敏感排序规则（应为utf8mb4_bin），"
            f"导致只差大小写的记录撞主键。已整批回滚。")


def _reconcile_all(cursor, seen):
    """整表对齐：飞书没有的行全删，包括登记日期为空、归不到批次的那些。

    只在全量拉取后调用——那时本次拉到的就是飞书的全部内容，删得有依据。
    增量（只拉视图当周那批）绝不能走这里，否则会把没拉的历史批次全删光。
    """
    cursor.execute(f"SELECT record_id FROM {TABLE}")
    stale = [r["record_id"] for r in cursor.fetchall() if r["record_id"] not in seen]
    deleted = 0
    for offset in range(0, len(stale), _BATCH_SIZE):
        chunk = stale[offset:offset + _BATCH_SIZE]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(f"DELETE FROM {TABLE} WHERE record_id IN ({placeholders})", chunk)
        deleted += cursor.rowcount
    return deleted


def _reconcile_month(cursor, month, seen):
    """该统计月份里，库里有、本次没拉到的记录删掉。别的月份一行不碰。"""
    cursor.execute(f"SELECT record_id FROM {TABLE} "
                   f"WHERE reg_date IS NOT NULL AND DATE_FORMAT(reg_date,'%%Y-%%m')=%s", (month,))
    stale = [r["record_id"] for r in cursor.fetchall() if r["record_id"] not in seen]
    deleted = 0
    for offset in range(0, len(stale), _BATCH_SIZE):
        chunk = stale[offset:offset + _BATCH_SIZE]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(f"DELETE FROM {TABLE} WHERE record_id IN ({placeholders})", chunk)
        deleted += cursor.rowcount
    return deleted
