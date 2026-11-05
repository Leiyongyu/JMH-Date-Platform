"""负责人映射表飞书同步：按表名还原成 Excel 同构的表、与上传同一解析口径、内容未变跳过、只重算有变化的月份。"""
from __future__ import annotations

import pytest

from backend.services import owner_rule_feishu_sync_service as svc

KEY_COLUMNS = {"EU-店铺": "店铺", "EU-品牌": "品牌", "EU-OTH": "中间码-OTH", "US1": "店铺名", "US2": "店铺名", "EBAY": "列1"}


def default_rows():
    return {
        "EU-店铺": [{"店铺": "伶斯勋", "202610": "陈渝", "202611": "陈渝"}],
        "EU-品牌": [{"品牌": "abc", "202610": [{"type": "text", "text": "吴清栩"}], "202611": "吴清栩"}],
        "EU-OTH": [{"中间码-OTH": "10071", "202610": "陶俊霏", "202611": "陶俊霏"}],
        "US1": [{"店铺名": "水金余", "202610": "注销", "202611": "待定"}],
        "US2": [{"店铺名": "斯鑫雅", "202610": "王皓"}],
        "EBAY": [{"列1": "FLL", "202610": "方黎力", "202611": "方黎力"}],
    }


class FakeClient:
    def __init__(self, rows=None, tables=None):
        self.rows = rows or default_rows()
        self.tables = tables or list(KEY_COLUMNS)
        self.closed = False

    def list_tables(self, app_token):
        return [{"table_id": f"tbl{i}", "name": name} for i, name in enumerate(self.tables)]

    def _name(self, table_id):
        return self.tables[int(table_id[3:])]

    def list_fields(self, app_token, table_id):
        name = self._name(table_id)
        return [{"field_name": column} for column in (KEY_COLUMNS[name], "202610", "202611", "备注")]

    def iter_records(self, app_token, table_id):
        for index, row in enumerate(self.rows[self._name(table_id)]):
            yield {"record_id": f"rec{index}", "fields": row}

    def close(self):
        self.closed = True


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def apply(parsed, batch_id, source, **kwargs):
        calls.update(parsed=parsed, kwargs=kwargs, source=source)
        return {"imported_rows": len(parsed["rules"]), "months": parsed["months"],
                "refreshed_months": sorted(kwargs.get("only_months") or []), "refresh": None}

    monkeypatch.setattr(svc.repo, "latest_import_hash", lambda import_type: None)
    monkeypatch.setattr(svc.repo, "owner_rule_snapshot", lambda months: {})
    return calls, apply


def test_tables_become_excel_shaped_frames_and_use_the_same_parser(captured):
    calls, apply = captured
    client = FakeClient()
    result = svc.sync_owner_rules_from_feishu(client_factory=lambda: client, apply=apply)
    assert client.closed and result["status"] == "completed"
    assert result["table_rows"] == {name: 1 for name in KEY_COLUMNS}
    rules = {(r["group_code"], r["match_key"], r["stat_month"]): r["principal_name"] for r in calls["parsed"]["rules"]}
    assert rules[("EU", "ABC", "2026-10")] == "吴清栩"  # 品牌转大写、富文本取文字，与上传一致
    assert rules[("US1", "水金余", "2026-11")] == ""      # 待定 = 未分配
    assert rules[("", "FLL", "2026-11")] == "方黎力"      # EBAY 第一列为品牌
    assert ("US2", "斯鑫雅", "2026-11") in rules and rules[("US2", "斯鑫雅", "2026-11")] == ""
    assert calls["kwargs"]["import_type"] == "owner_rule_feishu" and calls["source"].startswith("飞书多维表格:")
    assert result["changed_months"] == ["2026-10", "2026-11"] and calls["kwargs"]["rebuild"] is True
    assert result["extract_rows"] == 6 and result["refresh"] == {}


def test_unchanged_content_is_skipped(monkeypatch, captured):
    calls, apply = captured
    first = svc.sync_owner_rules_from_feishu(client_factory=FakeClient, apply=apply)
    monkeypatch.setattr(svc.repo, "latest_import_hash", lambda import_type: first["content_hash"])
    calls.clear()
    second = svc.sync_owner_rules_from_feishu(client_factory=FakeClient, apply=apply)
    assert second["status"] == "unchanged" and calls == {} and second["ods_rows"] == 0
    forced = svc.sync_owner_rules_from_feishu(client_factory=FakeClient, apply=apply, force=True)
    assert forced["status"] == "completed"


def test_only_months_with_changed_owners_are_recalculated(monkeypatch, captured):
    calls, apply = captured
    parsed = svc.parse_unified_owner_rule_frames(svc.fetch_frames(FakeClient(), "app")[0], "x", b"x", "b")
    existing = {(r["platform"], r["stat_month"], r["group_code"], r["rule_type"], r["match_key"]): r["principal_name"]
                for r in parsed["rules"]}
    existing[("amazon", "2026-11", "EU", "STORE", "伶斯勋")] = "别人"
    monkeypatch.setattr(svc.repo, "owner_rule_snapshot", lambda months: existing)
    result = svc.sync_owner_rules_from_feishu(client_factory=FakeClient, apply=apply)
    assert result["changed_months"] == ["2026-11"] and calls["kwargs"]["only_months"] == {"2026-11"}

    monkeypatch.setattr(svc.repo, "owner_rule_snapshot", lambda months: {**existing, ("amazon", "2026-11", "EU", "STORE", "伶斯勋"): "陈渝"})
    result = svc.sync_owner_rules_from_feishu(client_factory=FakeClient, apply=apply)
    assert result["changed_months"] == [] and calls["kwargs"]["rebuild"] is False


def test_missing_table_or_conflicting_rows_are_rejected(captured):
    calls, apply = captured
    with pytest.raises(ValueError, match="缺少数据表：EBAY"):
        svc.sync_owner_rules_from_feishu(client_factory=lambda: FakeClient(tables=list(KEY_COLUMNS)[:-1]), apply=apply)
    rows = default_rows()
    rows["US1"].append({"店铺名": "水金余", "202610": "张三"})
    with pytest.raises(ValueError, match="重复"):
        svc.sync_owner_rules_from_feishu(client_factory=lambda: FakeClient(rows=rows), apply=apply)


def test_registered_as_scheduler_task():
    from backend.services import scheduler_service
    spec = scheduler_service.TASK_SPECS[svc.TASK_CODE]
    assert spec.name == svc.TASK_NAME and spec.lock_name(None) == "performance:owner-rule:feishu"
