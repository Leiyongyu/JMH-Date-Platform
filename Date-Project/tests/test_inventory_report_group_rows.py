from copy import deepcopy

from backend.services.inventory_report_group_rows import with_group_display_rows
from backend.services import inventory_report_etl_service as etl


def _row(code, amount, *, ctu=None, rate=None):
    return {
        "department_code": code,
        "department_name": code,
        "is_total": 0,
        "total_goods_value": amount,
        "local_end_inventory_total_cost": amount,
        "ctu_over_30_cost": ctu,
        "target_achievement_rate": rate,
    }


def test_existing_computed_snapshot_gains_us3_without_changing_total():
    original = {
        "stat_month": "2026-08",
        "items": [
            _row("EBAY-1", "50"),
            _row("AMZ-US2-MJ", "100", ctu="25", rate="0.2"),
            _row("AMZ-US1-ZXY", "200", ctu="25", rate="0.3"),
            {"department_code": "AUTO-PARTS-TOTAL", "is_total": 1,
             "total_goods_value": "350", "ctu_over_30_cost": "25"},
        ],
    }
    before = deepcopy(original)
    result = with_group_display_rows(original)
    assert original == before
    assert [row["department_code"] for row in result["items"]] == [
        "EBAY-1", "AMZ-US2-MJ", "AMZ-US1-ZXY", "AMZ-US3", "AUTO-PARTS-TOTAL",
    ]
    us3 = result["items"][3]
    assert us3["total_goods_value"] == "300"
    assert us3["target_achievement_rate"] == "0.5"
    assert us3["ctu_over_30_cost"] == "25"
    assert result["items"][-1] == original["items"][-1]
    assert with_group_display_rows(result) == result


def test_historical_subtotal_uses_us3_instead_of_split_rows():
    payload = {"historical_import": True, "items": [
        _row("EBAY-1", "50", rate="0.1"),
        _row("AMZ-US2-MJ", "100", rate="0.2"),
        _row("AMZ-US1-ZXY", "200", rate="0.3"),
        _row("AMZ-US3", "300", rate="0.5"),
    ]}
    result = with_group_display_rows(payload)
    subtotal = result["items"][-1]
    assert subtotal["is_total"] == 1
    assert subtotal["total_goods_value"] == "350"
    assert subtotal["target_achievement_rate"] == "0.6"
    assert with_group_display_rows(result) == result


def test_snapshot_read_adds_us3_without_live_recalculation(monkeypatch):
    saved = {"stat_month": "2026-08", "items": [
        _row("AMZ-US2-MJ", "10"), _row("AMZ-US1-ZXY", "20"),
        {"department_code": "AUTO-PARTS-TOTAL", "is_total": 1,
         "total_goods_value": "30"},
    ]}
    monkeypatch.setattr(etl.repo, "view_snapshot", lambda _month, _dimension: saved)
    result = etl.get_department_summary("2026-08")
    assert [row["department_code"] for row in result["items"]] == [
        "AMZ-US2-MJ", "AMZ-US1-ZXY", "AMZ-US3", "AUTO-PARTS-TOTAL",
    ]
    assert result["items"][2]["total_goods_value"] == "30"
    assert saved["items"][-1]["total_goods_value"] == "30"
