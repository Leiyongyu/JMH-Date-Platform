"""Composite middle-code/site mapping (database table) and mixed-site search tests."""
from __future__ import annotations

import base64
from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Font

from backend.ebay_tool import app as tool


def run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("Unexpected asynchronous I/O in offline test")


def options():
    return dict(site="auto", free_shipping="false", search_strategy="category_lock",
                ebay_sort="price", delivery_country="", delivery_postal_code="",
                pickup_country="", pickup_postal_code="", pickup_radius="", pickup_unit="",
                price_min="", price_max="", us_postal_code="08505")


@pytest.fixture
def mapping(monkeypatch):
    monkeypatch.setattr(tool, "_mapping_loaded", True)
    monkeypatch.setattr(tool, "_mapping_schema", "site_key")
    monkeypatch.setattr(tool, "_site_key_oe_map", {
        "10144US": ("10144", "us", "OE-US"),
        "10144UK": ("10144", "uk", "OE-UK"),
        "50244US": ("50244", "us", ""),
        "30532US": ("30532", "us", "SAME-OE"),
        "30528US": ("30528", "us", "SAME-OE"),
    })


def test_exact_site_key_lookup_and_blank_oe(mapping):
    targets, matches, missing = tool._resolve_site_key_targets(
        ["10144us", "10144UK", "10144DE", "50244US", "bad"]
    )
    assert [(t["inputKey"], t["site"], t["oe"]) for t in targets] == [
        ("10144US", "us", "OE-US"), ("10144UK", "uk", "OE-UK")
    ]
    assert matches == {"10144US": "OE-US", "10144UK": "OE-UK"}
    assert any("10144DE" in error and "站点没有映射" in error for error in missing)
    assert any("50244US" in error and "为空" in error for error in missing)
    assert any("bad" in error and "格式" in error for error in missing)
    assert any("中间码不存在" in error for error in tool._resolve_site_key_targets(["99999US"])[2])


def test_mixed_sites_and_same_oe_keep_independent_groups(mapping, monkeypatch):
    calls = []

    def scrape(oe, site, **kwargs):
        calls.append((oe, site))
        return ([{"oe": oe, "itemId": "1", "pf": 1}], None, 0,
                "category_locked", None, [1])

    monkeypatch.setattr(tool, "scrape_one_oe", scrape)
    targets, _, _ = tool._resolve_site_key_targets(
        ["10144US", "10144UK", "30532US", "30528US"]
    )
    task_id = "offline-mixed-sites"
    try:
        tool.search_batch([], "auto", task_id, targets=targets)
        results = tool.tasks[task_id]["results"]
        assert [(r["inputKey"], r["site"], r["oe"]) for r in results] == [
            ("10144US", "US", "OE-US"), ("10144UK", "UK", "OE-UK"),
            ("30532US", "US", "SAME-OE"), ("30528US", "US", "SAME-OE")
        ]
        assert set(calls) == {("OE-US", "us"), ("OE-UK", "uk"), ("SAME-OE", "us")}
        assert results[2]["groupKey"] != results[3]["groupKey"]
        assert results[2]["items"][0]["inputKey"] == "30532US"
        assert results[3]["items"][0]["inputKey"] == "30528US"
    finally:
        tool.tasks.pop(task_id, None)


def test_text_endpoint_sends_targets_without_manual_site(mapping, monkeypatch):
    received = []
    monkeypatch.setattr(tool, "_start_search_task", lambda *a, **kw: (received.append((a, kw)) or {"ok": True}))
    result = run_immediate(tool.api_scrape(
        nkw="10144US, 10144UK, 50244US", input_type="site_key", **options()
    ))
    assert result == {"ok": True}
    assert [t["site"] for t in received[0][1]["targets"]] == ["us", "uk"]
    assert any("50244US" in error for error in received[0][0][5])


def test_unmatched_input_does_not_fall_back_to_raw_oe(mapping):
    with pytest.raises(HTTPException, match="没有可查询的映射"):
        run_immediate(tool.api_scrape(
            nkw="50244US, 10144DE", input_type="site_key", **options()
        ))


# 测试用固定映射表，不依赖业务人员会持续编辑的真实 SKU主OE对照表.xlsx 或数据库。
SAMPLE_ROWS = [
    ("10144US", "7L6616403B"),
    ("10144UK", "7L6616403B-UK"),
    ("10141US", "8K0616039"),
    ("10141UK", "8K0616039-UK"),
    ("50244US", None),
    ("30532US", "SAME-OE"),
]


class FakeRepo:
    """In-memory stand-in for ebay_sku_oe_repository with the same semantics."""

    def __init__(self, rows=()):
        self.rows = {key: {"site_key": key, "middle_code": key[:-2], "site": key[-2:], "oe_no": oe,
                           "update_by": "seed"} for key, oe in rows}

    def list_mappings(self):
        return [dict(row) for _, row in sorted(self.rows.items())]

    def upsert_mappings(self, rows, operator):
        created = updated = 0
        for row in rows:
            old = self.rows.get(row["site_key"])
            if old is None:
                created += 1
            elif old["oe_no"] != row["oe_no"]:
                updated += 1
            else:
                continue
            self.rows[row["site_key"]] = {**row, "update_by": operator}
        return {"created": created, "updated": updated, "unchanged": len(rows) - created - updated}

    def insert_mapping(self, row, operator):
        if row["site_key"] in self.rows:
            return False
        self.rows[row["site_key"]] = {**row, "update_by": operator}
        return True

    def update_mapping(self, original, row, operator):
        if original not in self.rows:
            return "missing"
        if row["site_key"] != original and row["site_key"] in self.rows:
            return "duplicate"
        del self.rows[original]
        self.rows[row["site_key"]] = {**row, "update_by": operator}
        return "ok"

    def delete_mapping(self, key):
        return self.rows.pop(key, None) is not None


def _isolate_mapping_state(monkeypatch):
    for name in ("_site_key_oe_map", "_sku_oe_map", "_middle_code_oe_map", "_mapping_schema", "_mapping_loaded"):
        monkeypatch.setattr(tool, name, getattr(tool, name))


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo([(key, oe or "") for key, oe in SAMPLE_ROWS])
    monkeypatch.setattr(tool, "sku_oe_repo", fake)
    _isolate_mapping_state(monkeypatch)
    monkeypatch.setattr(tool, "_mapping_loaded", False)
    return fake


def _workbook_bytes(rows, header=("中间码+站点", "中间码", "站点", "OE号")) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(header))
    for index, (key, oe) in enumerate(rows, start=2):
        sheet.append([key, f"=LEFT(A{index},LEN(A{index})-2)", f"=RIGHT(A{index},2)", oe])
        sheet.cell(index, 1).font = Font(name="Arial", bold=True)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class Request:
    def __init__(self, body=None, username=None):
        self.body = body
        self.headers = {}
        if username:
            encoded = base64.urlsafe_b64encode(username.encode("utf-8")).decode().rstrip("=")
            self.headers["X-ERP-Username-B64"] = encoded

    async def json(self):
        return self.body


class Upload:
    def __init__(self, content, filename="SKU主OE对照表.xlsx"):
        self.content = content
        self.filename = filename

    async def read(self):
        return self.content


def test_queries_read_the_database_table_lazily(repo):
    assert tool._mapping_loaded is False
    _targets, mapping, missing = tool._resolve_site_key_targets(["10144us", "50244US"])
    assert tool._mapping_loaded is True
    assert mapping == {"10144US": "7L6616403B"}
    assert tool._site_key_oe_map["10144UK"] == ("10144", "uk", "7L6616403B-UK")
    assert any("50244US" in error and "为空" in error for error in missing)
    listing = run_immediate(tool.api_sku_list())
    assert listing["siteKeyMode"] is True and listing["total"] == len(SAMPLE_ROWS)


def test_unreadable_table_reports_migration_hint(monkeypatch):
    _isolate_mapping_state(monkeypatch)
    monkeypatch.setattr(tool, "_mapping_loaded", False)

    class Broken:
        def list_mappings(self):
            raise RuntimeError("Table 'dim_ebay_sku_oe_site' doesn't exist")

    monkeypatch.setattr(tool, "sku_oe_repo", Broken())
    with pytest.raises(HTTPException) as error:
        tool._resolve_site_key_targets(["10144US"])
    assert error.value.status_code == 503
    assert "20261106_ebay_sku_oe_site.sql" in error.value.detail


def test_upload_overwrites_by_site_key_and_keeps_the_rest(repo):
    content = _workbook_bytes([
        ("10144US", "NEW-OE"),        # overwrite
        ("10141US", "8K0616039"),     # same value -> unchanged
        ("99999DE", "BRAND-NEW"),     # create
        ("10144UK", None),            # blank OE -> skipped, existing kept
        ("bad-key", "X"),             # bad format
        ("99999DE", "SECOND"),        # duplicate in file -> first wins
        ("88888UK", 12345.0),         # numeric OE cell
    ])
    result = run_immediate(tool.api_sku_import(Request(username="张三"), file=Upload(content)))
    assert (result["created"], result["updated"], result["unchanged"]) == (2, 1, 1)
    assert result["totalRows"] == 7 and result["skippedRows"] == 3
    assert any("10144UK" in item and "为空" in item for item in result["skipped"])
    assert any("bad-key" in item and "格式" in item for item in result["skipped"])
    assert any("99999DE" in item and "重复" in item for item in result["skipped"])
    assert repo.rows["10144US"]["oe_no"] == "NEW-OE"
    assert repo.rows["10144US"]["update_by"] == "张三"
    assert repo.rows["10144UK"]["oe_no"] == "7L6616403B-UK"      # untouched
    assert repo.rows["30532US"]["oe_no"] == "SAME-OE"            # absent from file, kept
    assert repo.rows["99999DE"] == {"site_key": "99999DE", "middle_code": "99999", "site": "DE",
                                    "oe_no": "BRAND-NEW", "update_by": "张三"}
    assert repo.rows["88888UK"]["oe_no"] == "12345"
    assert tool._resolve_site_key_targets(["99999DE"])[1] == {"99999DE": "BRAND-NEW"}   # cache reloaded


def test_upload_rejects_wrong_header_empty_data_and_other_types(repo):
    wrong_header = _workbook_bytes([("10144US", "X")], header=("SKU", "", "", "OE"))
    with pytest.raises(HTTPException, match="表头应为"):
        run_immediate(tool.api_sku_import(Request(), file=Upload(wrong_header)))
    with pytest.raises(HTTPException, match="没有可导入"):
        run_immediate(tool.api_sku_import(Request(), file=Upload(_workbook_bytes([("10144US", None)]))))
    with pytest.raises(HTTPException, match="仅支持"):
        run_immediate(tool.api_sku_import(Request(), file=Upload(b"x", "a.csv")))
    assert repo.rows["10144US"]["oe_no"] == "7L6616403B"


def test_add_update_delete_write_the_table(repo):
    result = run_immediate(tool.api_sku_add(Request({"sku": "00998us", "oe": "API-OE"}, "李四")))
    assert result["sku"] == "00998US" and repo.rows["00998US"]["update_by"] == "李四"
    with pytest.raises(HTTPException, match="已存在"):
        run_immediate(tool.api_sku_add(Request({"sku": "00998US", "oe": "DUP"})))
    run_immediate(tool.api_sku_update(Request({"originalSku": "00998US", "sku": "00998UK", "oe": "EDIT-OE"})))
    assert "00998US" not in repo.rows
    assert tool._resolve_site_key_targets(["00998UK"])[1] == {"00998UK": "EDIT-OE"}
    with pytest.raises(HTTPException, match="已存在"):
        run_immediate(tool.api_sku_update(Request({"originalSku": "00998UK", "sku": "10144US", "oe": "X"})))
    with pytest.raises(HTTPException, match="不存在"):
        run_immediate(tool.api_sku_update(Request({"originalSku": "77777US", "sku": "77777US", "oe": "X"})))
    with pytest.raises(HTTPException, match="不能为空"):
        run_immediate(tool.api_sku_add(Request({"sku": "00997US", "oe": " "})))
    run_immediate(tool.api_sku_delete(Request({"sku": "00998uk"})))
    assert "00998UK" not in repo.rows
    assert "00998UK" not in tool._site_key_oe_map
    with pytest.raises(HTTPException, match="不存在"):
        run_immediate(tool.api_sku_delete(Request({"sku": "00998UK"})))


def test_specific_query_errors(repo):
    with pytest.raises(HTTPException, match="中间码不存在"):
        run_immediate(tool.api_scrape(nkw="99999US", input_type="site_key", **options()))
    with pytest.raises(HTTPException, match="对应站点没有映射"):
        run_immediate(tool.api_scrape(nkw="10144DE", input_type="site_key", **options()))
    with pytest.raises(HTTPException, match="OE 号为空"):
        run_immediate(tool.api_scrape(nkw="50244US", input_type="site_key", **options()))


def test_excel_query_reads_first_column_as_site_keys():
    keys, kind, total, _, _ = tool._parse_excel_keywords_from_bytes(
        _workbook_bytes(SAMPLE_ROWS), "SKU主OE对照表.xlsx", site_key_mode=True
    )
    assert kind == "site_key"
    assert total == len(SAMPLE_ROWS)
    assert "10141US" in keys and "10141UK" in keys


def test_excel_endpoint_uses_site_mapping_without_manual_site(repo, monkeypatch):
    received = []
    monkeypatch.setattr(tool, "_start_search_task", lambda *a, **kw: (received.append((a, kw)) or {"ok": True}))
    assert run_immediate(tool.api_scrape_file(
        file=Upload(_workbook_bytes(SAMPLE_ROWS), "query.xlsx"), input_type="site_key", **options()
    )) == {"ok": True}
    targets = received[0][1]["targets"]
    assert any(t["inputKey"] == "10144US" and t["site"] == "us" for t in targets)
    assert any(t["inputKey"] == "10141UK" and t["site"] == "uk" for t in targets)
    assert any("50244US" in error for error in received[0][0][5])
