from io import BytesIO
from unittest.mock import MagicMock

import pytest
from openpyxl import Workbook

from backend.services import inventory_report_history_import_service as history
from backend.repositories import inventory_report_etl_repository as repo
from backend.services.inventory_report_export_service import _combined
from backend.services import inventory_report_etl_service as etl


def workbook_bytes(*, duplicate=False):
    book = Workbook()
    sheet = book.active
    sheet.title = "2025年4月1日(含头程)"
    sheet.append(["部门", "总货值", "海外仓/FBA在库金额", "90-180库龄成本",
                  "海外仓90-180货值（8.5）", "4月销售目标", "4月目标达成率"])
    sheet.append(["AMZ-US2-MJ", 100, 50, 7, 999, 12, 0.25])
    sheet.append(["AMZ-US1-ZXY", None, None, None, None, None, None])
    sheet.append(["AMZ-US3", 200, 80, 8, 888, 20, 0.5])
    if duplicate:
        book.copy_worksheet(sheet).title = "2025年4月1日"
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def test_parse_preserves_us3_and_blank_values_and_prefers_age_cost():
    parsed = history.parse_history_workbook(workbook_bytes(), "history.xlsx")
    assert len(parsed) == 1
    sheet = parsed[0]
    assert (sheet["report_month"], sheet["stat_month"]) == ("2025-04", "2025-03")
    assert (sheet["source_row_count"], sheet["row_count"]) == (3, 4)
    assert [item["department_code"] for item in sheet["items"]] == [
        "AMZ-US2-MJ", "AMZ-US1-ZXY", "AMZ-US3", "AUTO-PARTS-TOTAL",
    ]
    assert sheet["items"][0]["inventory_age_90_180_cost"] == "7"
    assert sheet["items"][1]["total_goods_value"] is None
    assert sheet["items"][2]["sales_target_usd"] == "20"
    assert sheet["items"][3]["department_name"] == "汽配小计"
    assert sheet["items"][3]["total_goods_value"] == "200"
    assert sheet["items"][3]["sales_target_usd"] == "20"
    assert _combined("overseas_end_inventory_total_cost", "fba_end_inventory_total_cost")(
        sheet["items"][1]
    ) is None


def test_duplicate_report_month_rejected():
    with pytest.raises(ValueError, match="重复Sheet"):
        history.parse_history_workbook(workbook_bytes(duplicate=True), "history.xlsx")


def test_import_checks_preview_digest_and_only_passes_group_payload(monkeypatch):
    content = workbook_bytes()
    calls = []
    monkeypatch.setattr(repo, "insert_history_group_snapshots", lambda payloads: (
        calls.extend(payloads) or ["2025-03"], []
    ))
    with pytest.raises(ValueError, match="预览"):
        history.import_history(content, "history.xlsx", "wrong")
    digest = history.hashlib.sha256(content).hexdigest()
    result = history.import_history(content, "history.xlsx", digest)
    assert result["imported_months"] == ["2025-03"]
    assert len(calls) == 1
    assert calls[0][1]["historical_import"] is True
    assert calls[0][1]["items"][-2]["department_code"] == "AMZ-US3"
    assert calls[0][1]["items"][-1]["department_code"] == "AUTO-PARTS-TOTAL"


def test_repository_import_skips_existing_month_and_never_updates(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [True, None]
    cursor.rowcount = 1
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(repo, "db_connection", lambda: connection)
    imported, skipped = repo.insert_history_group_snapshots([
        ("2025-03", {"items": []}), ("2025-04", {"items": []}),
    ])
    assert imported == ["2025-04"]
    assert skipped == ["2025-03"]
    inserts = [call.args[0] for call in cursor.execute.call_args_list
               if call.args[0].startswith("INSERT")]
    assert len(inserts) == 1
    assert "INSERT IGNORE" in inserts[0]
    assert "UPDATE" not in inserts[0]
    connection.commit.assert_called_once()


def test_imported_group_month_has_no_synthetic_store_or_owner(monkeypatch):
    monkeypatch.setattr(repo, "view_snapshot", lambda month, dimension: (
        {"historical_import": True, "items": []} if dimension == "GROUP" else None
    ))
    monkeypatch.setattr(repo, "dimension_summary", lambda *_args: pytest.fail(
        "historical upload must not calculate other dimensions"
    ))
    for dimension in ("STORE", "OWNER"):
        data = etl.get_dimension_summary(dimension, "2025-03")
        assert data["items"] == []
        assert data["total"] is None
