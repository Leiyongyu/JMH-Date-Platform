from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from backend.parsers.inventory_age_cost_parser import parse_inventory_age_cost_excel
from backend.services.clearance_service import _group


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "2026-07"
    sheet.append(["部门", "海外仓90-180货值", "海外仓180+货值"])
    sheet.append(["AMZ-EU", 171475.12, 135230.14])
    sheet.append(["AMZ-US2-MJ", 39396.31, 8226.16])
    sheet.append(["AMZ-US1-ZXY", 81276.97, 66893.43])
    sheet.append(["EBAY-1", 287378, 396720.99])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_inventory_age_cost_month_and_groups():
    result = parse_inventory_age_cost_excel(_workbook_bytes(), "7月库存成本.xlsx")

    assert result["cost_month"] == "2026-07"
    assert result["amz_rows"] == 3
    assert len(result["rows"]) == 4
    assert result["rows"][0]["group_code"] == "EU"
    assert result["rows"][1]["group_code"] == "US2-MJ"
    assert result["rows"][2]["group_code"] == "US1-ZXY"
    assert result["rows"][3]["group_code"] is None
    assert str(result["rows"][1]["inventory_91_180_cost"]) == "39396.31"


def test_us3_store_split_and_existing_groups_unchanged():
    shops = {
        "1": "US3-新志楠-US",
        "2": "US3-富琳顿-CA",
        "3": "US3-富林顿-MX",
        "4": "US3-吉西瑞雅-US",
        "5": "EU-某店-DE",
        "6": "US2-某店-US",
    }

    assert _group({}, "1", shops)[0] == "US2-MJ"
    assert _group({}, "2", shops)[0] == "US2-MJ"
    assert _group({}, "3", shops)[0] == "US2-MJ"
    assert _group({}, "4", shops)[0] == "US1-ZXY"
    assert _group({}, "5", shops)[0] == "EU"
    assert _group({}, "6", shops)[0] == "US2"
