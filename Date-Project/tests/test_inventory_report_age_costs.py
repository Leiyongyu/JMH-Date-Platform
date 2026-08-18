from decimal import Decimal

from backend.services import inventory_report_etl_service as service


def test_department_summary_uses_next_month_clearance_age_costs(monkeypatch):
    departments = [
        ("EBAY-1", 0),
        ("AMZ-EU", 0),
        ("AMZ-US1", 0),
        ("AMZ-US2", 0),
        ("AMZ-US2-MJ", 0),
        ("AMZ-US1-ZXY", 0),
        ("AUTO-PARTS-TOTAL", 1),
    ]
    monkeypatch.setattr(
        service.repo,
        "department_summary",
        lambda _month: {
            "stat_month": "2026-07",
            "items": [
                {"department_code": code, "is_total": is_total}
                for code, is_total in departments
            ],
        },
    )
    requested_months = []

    def age_costs(month):
        requested_months.append(month)
        costs = {
            group: {
                "inventory_91_180_cost": Decimal(index * 10),
                "inventory_181_plus_cost": Decimal(index),
            }
            for index, group in enumerate(
                ("EU", "US1", "US2", "US2-MJ", "US1-ZXY"),
                start=1,
            )
        }
        costs["EBAY-1"] = {
            "inventory_91_180_cost": Decimal("7"),
            "inventory_181_plus_cost": Decimal("3"),
        }
        return costs

    monkeypatch.setattr(service.repo, "inventory_age_group_costs", age_costs)
    monkeypatch.setattr(
        service.repo, "amz_sales_volume_by_department", lambda _month: None
    )
    monkeypatch.setattr(service.repo, "ebay_sales_volume", lambda _month: None)
    monkeypatch.setattr(
        service.repo, "amz_sales_amount_by_department", lambda _month: None
    )
    monkeypatch.setattr(service.repo, "ebay_sales_amount", lambda _month: None)

    result = service.get_department_summary("2026-07")
    rows = {row["department_code"]: row for row in result["items"]}

    assert requested_months == ["2026-08"]
    assert rows["AMZ-EU"]["inventory_age_90_180_cost"] == "10"
    assert rows["AMZ-EU"]["inventory_age_180_plus_cost"] == "1"
    assert rows["EBAY-1"]["inventory_age_90_180_cost"] == "7"
    assert rows["EBAY-1"]["inventory_age_180_plus_cost"] == "3"
    assert rows["AUTO-PARTS-TOTAL"]["inventory_age_90_180_cost"] == "157"
    assert rows["AUTO-PARTS-TOTAL"]["inventory_age_180_plus_cost"] == "18"
    assert rows["AUTO-PARTS-TOTAL"]["inventory_age_cost_month"] == "2026-08"
    assert rows["AUTO-PARTS-TOTAL"]["monthly_sales_qty"] is None


def test_next_month_handles_year_boundary():
    assert service._next_month("2026-12") == "2027-01"


def test_department_summary_uses_next_month_sales_volume(monkeypatch):
    departments = [
        ("EBAY-1", 0),
        ("AMZ-EU", 0),
        ("AMZ-US1", 0),
        ("AMZ-US2", 0),
        ("AMZ-US2-MJ", 0),
        ("AMZ-US1-ZXY", 0),
        ("AUTO-PARTS-TOTAL", 1),
    ]
    monkeypatch.setattr(
        service.repo,
        "department_summary",
        lambda _month: {
            "stat_month": "2026-07",
            "items": [
                {"department_code": code, "is_total": is_total}
                for code, is_total in departments
            ],
        },
    )
    monkeypatch.setattr(service.repo, "inventory_age_group_costs", lambda _month: {})
    monkeypatch.setattr(service.repo, "ebay_sales_volume", lambda month: Decimal("9"))
    monkeypatch.setattr(
        service.repo,
        "amz_sales_volume_by_department",
        lambda month: {"AMZ-EU": Decimal("12")},
    )
    monkeypatch.setattr(
        service.repo,
        "amz_sales_amount_by_department",
        lambda month: {"AMZ-EU": Decimal("120")},
    )
    monkeypatch.setattr(service.repo, "ebay_sales_amount", lambda month: Decimal("90"))

    result = service.get_department_summary("2026-07")
    rows = {row["department_code"]: row for row in result["items"]}

    assert rows["EBAY-1"]["monthly_sales_qty"] == "9"
    assert rows["AMZ-EU"]["monthly_sales_qty"] == "12"
    assert rows["AMZ-US1"]["monthly_sales_qty"] == "0"
    assert rows["AUTO-PARTS-TOTAL"]["monthly_sales_qty"] == "21"
    assert rows["AUTO-PARTS-TOTAL"]["sales_volume_month"] == "2026-08"
    assert rows["EBAY-1"]["actual_achievement_amount"] == "90"
    assert rows["AMZ-EU"]["actual_achievement_amount"] == "120"
    assert rows["AUTO-PARTS-TOTAL"]["actual_achievement_amount"] == "210"
    assert result["report_month"] == "2026-08"


def test_month_options_map_inventory_source_to_next_business_month(monkeypatch):
    monkeypatch.setattr(
        service.repo,
        "months",
        lambda _limit: [
            {"stat_month": "2026-12", "department_rows": 7},
            {"stat_month": "2026-07", "department_rows": 7},
        ],
    )

    result = service.list_months(24)

    assert result[0]["report_month"] == "2027-01"
    assert result[1]["report_month"] == "2026-08"
