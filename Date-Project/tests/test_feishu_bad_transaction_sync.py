"""飞书不良交易刊登同步：字段映射、增量判定、批次清理。不发真实请求、不连库。"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.repositories import feishu_bad_transaction_repository as repo
from backend.services import feishu_bad_transaction_sync_service as service


def record(**fields):
    """按飞书真实返回的形状造一条：文本字段是富文本分段数组，日期是毫秒时间戳。"""
    base = {
        "登记日期": 1790092800000,          # 北京时间 2026-09-23 00:00
        "店铺": [{"type": "text", "text": "帝蓝泰江-ebay-Moses-motorsports"}],
        "评估日期": [{"type": "text", "text": "2026-09-20"}],
        "物品编号": [{"type": "text", "text": "156493318406"}],
        "刊登标题": [{"type": "text", "text": "Rear Air Suspension Spring for BMW X5"}],
        "刊登状态：Y=在线，N=已下线": "Y",
        "SKU": [{"type": "text", "text": "BMW-30031-2-0231"}],
        "总交易额": [{"type": "text", "text": "120.75392"}],
        "总交易量": [{"type": "text", "text": "2"}],
        "不良交易量": [{"type": "text", "text": "1"}],
        "物品未收到纠纷数量": [{"type": "text", "text": "1"}],
        "物品与描述不符退货数量": [{"type": "text", "text": "0"}],
        "中差评数量": [{"type": "text", "text": "0"}],
        "物品描述评分低分数量": [{"type": "text", "text": "0"}],
        "因缺货而取消的交易数量": [{"type": "text", "text": "0"}],
        "不良交易率": [{"type": "text", "text": "0.5"}],
    }
    base.update(fields)
    return {"record_id": "recvw08lloVJon", "fields": base,
            "created_time": 1790125542000, "last_modified_time": 1790125542000}


# ------------------------------------------------------------------ 字段映射

def test_rich_text_arrays_flattened_and_dates_converted():
    warnings = set()
    row = service.to_row(record(), warnings)
    assert row["record_id"] == "recvw08lloVJon"
    # 毫秒时间戳按北京时区换算：1790092800000 是北京时间 2026-09-23 零点，
    # 按 UTC 算会退到 09-22，整批批次日期都会差一天。
    assert row["reg_date"] == dt.date(2026, 9, 23)
    assert row["shop"] == "帝蓝泰江-ebay-Moses-motorsports"
    assert row["sku"] == "BMW-30031-2-0231"
    assert row["listing_status"] == "Y"
    # 飞书侧是文本字段，就原样存文本，不擅自转成数值。
    assert row["total_amount"] == "120.75392" and row["defect_rate"] == "0.5"
    assert row["evaluate_date"] == "2026-09-20"
    assert row["feishu_updated_at"] == dt.datetime(2026, 9, 23, 9, 5, 42)
    assert not warnings


def test_empty_values_become_null_not_empty_string():
    row = service.to_row(record(SKU=[], 登记日期=None, 父记录={}), set())
    assert row["sku"] is None and row["reg_date"] is None and row["parent_json"] is None


def test_unknown_feishu_field_is_reported_not_silently_dropped():
    warnings = set()
    service.to_row(record(**{"字段 9": [{"type": "text", "text": "x"}]}), warnings)
    assert any("字段 9" in w for w in warnings)


def test_overlong_text_truncated_to_column_width_with_warning():
    warnings = set()
    row = service.to_row(record(刊登标题=[{"type": "text", "text": "标" * 300}]), warnings)
    assert len(row["title"]) == 255
    assert any("刊登标题" in w and "截断" in w for w in warnings)


def test_record_without_id_is_refused():
    broken = record()
    broken["record_id"] = ""
    with pytest.raises(service.FeishuBadTransactionSyncError, match="record_id"):
        service.to_row(broken, set())


@pytest.mark.parametrize("value,expected", [
    (1790092800000, dt.date(2026, 9, 23)),
    (None, None), ("", None), ([], None), ("bad", None),
])
def test_date_conversion_tolerates_missing_and_garbage(value, expected):
    assert service.to_date(value) == expected


# ------------------------------------------------------------------ 内容指纹

def test_hash_ignores_sync_timestamps_only_business_columns_count():
    """指纹只看业务列：飞书的最后更新时间会因无关操作变化，拿它判'变没变'会误报。"""
    row = service.to_row(record(), set())
    other = dict(row, feishu_updated_at=dt.datetime(2030, 1, 1), last_synced_at="x")
    assert repo.content_hash(row) == repo.content_hash(other)


def test_hash_changes_when_any_business_value_changes():
    row = service.to_row(record(), set())
    changed = service.to_row(record(不良交易率=[{"type": "text", "text": "0.6"}]), set())
    assert repo.content_hash(row) != repo.content_hash(changed)


# -------------------------------------------------------------- 增量写库

def db(monkeypatch, existing=None):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(repo, "db_connection", lambda: context)
    rows = [{"record_id": k, "content_hash": v} for k, v in (existing or {}).items()]
    # 第一次 fetchall 是查已有指纹，之后是批次清理时查该批次的全部id。
    cursor.fetchall.side_effect = [rows, []]
    cursor.rowcount = 0
    # 写后行数校验查的是 COUNT(*)，参数就是这一段 record_id；默认按参数个数返回，
    # 也就是"一条不少"。专门的用例再覆盖对不上的情况。
    cursor.fetchone.side_effect = lambda: {"n": len(cursor.execute.call_args.args[1])}
    return connection, cursor


def rows_for(*specs):
    out = []
    for rid, rate in specs:
        row = service.to_row(record(不良交易率=[{"type": "text", "text": rate}]), set())
        row["record_id"] = rid
        row["content_hash"] = repo.content_hash(row)
        out.append(row)
    return out


def test_new_records_counted_as_inserted(monkeypatch):
    connection, cursor = db(monkeypatch)
    rows = rows_for(("r1", "0.5"), ("r2", "0.6"))
    result = repo.upsert(rows, batches=[dt.date(2026, 9, 23)], synced_at=dt.datetime(2026, 9, 23))
    assert result["inserted_rows"] == 2 and result["updated_rows"] == 0
    assert result["unchanged_rows"] == 0
    connection.commit.assert_called_once()


def test_unchanged_records_are_not_rewritten(monkeypatch):
    rows = rows_for(("r1", "0.5"))
    connection, cursor = db(monkeypatch, existing={"r1": rows[0]["content_hash"]})
    result = repo.upsert(rows, batches=[], synced_at=dt.datetime(2026, 9, 23))
    assert result == {"inserted_rows": 0, "updated_rows": 0, "unchanged_rows": 1, "deleted_rows": 0}
    # 没变的行不走 INSERT ... ON DUPLICATE，只 UPDATE 一下最后同步时间。
    cursor.executemany.assert_not_called()
    touched = [c for c in cursor.execute.call_args_list if c.args[0].startswith("UPDATE")]
    assert len(touched) == 1


def test_changed_record_counted_as_updated_not_inserted(monkeypatch):
    rows = rows_for(("r1", "0.6"))
    connection, _ = db(monkeypatch, existing={"r1": "过时的指纹"})
    result = repo.upsert(rows, batches=[], synced_at=dt.datetime(2026, 9, 23))
    assert result["inserted_rows"] == 0 and result["updated_rows"] == 1


def test_records_deleted_in_feishu_are_removed_from_that_batch_only(monkeypatch):
    connection, cursor = db(monkeypatch)
    cursor.fetchall.side_effect = [[], [{"record_id": "r1"}, {"record_id": "gone"}]]
    cursor.rowcount = 1
    rows = rows_for(("r1", "0.5"))
    result = repo.upsert(rows, batches=[dt.date(2026, 9, 23)], synced_at=dt.datetime(2026, 9, 23))
    assert result["deleted_rows"] == 1
    deletes = [c for c in cursor.execute.call_args_list if c.args[0].startswith("DELETE")]
    assert len(deletes) == 1 and deletes[0].args[1] == ["gone"]
    # 清理范围严格限定在本次拉到的批次里，靠 reg_date 限定。
    scans = [c for c in cursor.execute.call_args_list if "WHERE reg_date=%s" in c.args[0]]
    assert scans and scans[0].args[1] == (dt.date(2026, 9, 23),)


def test_no_batches_means_no_reconcile(monkeypatch):
    """登记日期为空的记录归不到批次，只upsert、不参与清理，免得误删。"""
    connection, cursor = db(monkeypatch)
    repo.upsert(rows_for(("r1", "0.5")), batches=[], synced_at=dt.datetime(2026, 9, 23))
    assert not [c for c in cursor.execute.call_args_list if c.args[0].startswith("DELETE")]


def test_write_failure_rolls_back_everything(monkeypatch):
    connection, cursor = db(monkeypatch)
    cursor.executemany.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        repo.upsert(rows_for(("r1", "0.5")), batches=[], synced_at=dt.datetime(2026, 9, 23))
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_empty_pull_writes_nothing(monkeypatch):
    assert repo.upsert([], batches=[dt.date(2026, 9, 23)]) == {
        "inserted_rows": 0, "updated_rows": 0, "unchanged_rows": 0, "deleted_rows": 0}


# -------------------------------------------------------------- 同步编排

def configure(monkeypatch, *, view="vew1"):
    """Settings 是 frozen dataclass，改不了字段，整个替换掉。"""
    monkeypatch.setattr(service, "settings", SimpleNamespace(
        feishu_bad_transaction_app_token="App1", feishu_bad_transaction_table_id="tbl1",
        feishu_bad_transaction_view_id=view))


def test_duplicate_record_ids_abort_before_writing(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(service, "FeishuClient",
                        lambda *a, **k: MagicMock(__enter__=lambda s: MagicMock(
                            fetch_records=lambda *a, **k: [record(), record()]),
                            __exit__=lambda *a: None))
    written = []
    monkeypatch.setattr(repo, "upsert", lambda *a, **k: written.append(a) or {})
    with pytest.raises(service.FeishuBadTransactionSyncError, match="重复的record_id"):
        service.sync_feishu_bad_transactions()
    assert not written


def test_view_required_for_incremental_mode(monkeypatch):
    configure(monkeypatch, view="")
    with pytest.raises(service.FeishuBadTransactionSyncError, match="视图"):
        service.sync_feishu_bad_transactions()


def test_task_registered_in_scheduler():
    from backend.services import scheduler_service
    assert service.TASK_CODE in scheduler_service.TASK_CODES
    assert scheduler_service.TASK_SPECS[service.TASK_CODE].name == service.TASK_NAME


def test_row_count_mismatch_after_write_rolls_back(monkeypatch):
    """静默少行必须当场炸出来：record_id 大小写敏感，主键排序规则不对会撞行。

    实测飞书里就有 rec277zuUdLAHp 与 rec277zuUdLahP 这种只差大小写的两条；
    主键若是 utf8mb4_unicode_ci，后写的会变成 UPDATE 前一条，行数少了却不报错。
    """
    connection, cursor = db(monkeypatch)
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = {"n": 1}   # 写了2条，只查到1条
    with pytest.raises(ValueError, match="utf8mb4_bin"):
        repo.upsert(rows_for(("r1", "0.5"), ("r2", "0.6")), batches=[],
                    synced_at=dt.datetime(2026, 9, 23))
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_row_count_match_commits(monkeypatch):
    connection, cursor = db(monkeypatch)
    cursor.fetchone.side_effect = None
    cursor.fetchone.return_value = {"n": 2}
    repo.upsert(rows_for(("r1", "0.5"), ("r2", "0.6")), batches=[],
                synced_at=dt.datetime(2026, 9, 23))
    connection.commit.assert_called_once()
