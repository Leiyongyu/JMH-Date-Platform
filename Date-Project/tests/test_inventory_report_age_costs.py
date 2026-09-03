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
    requested_ctu_months = []

    def ctu_costs(month):
        requested_ctu_months.append(month)
        return {
            "EBAY-1": Decimal("7"),
            "EU": Decimal("10"),
            "US1": Decimal("20"),
            "US2": Decimal("30"),
            "US3": Decimal("40"),
        }

    monkeypatch.setattr(
        service.clearance_repo, "ctu_over_30_costs", ctu_costs
    )
    monkeypatch.setattr(
        service.repo, "amz_sales_volume_by_department", lambda _month: None
    )
    monkeypatch.setattr(service.repo, "ebay_sales_volume", lambda _month: None)
    monkeypatch.setattr(
        service.repo, "amz_sales_amount_by_department", lambda _month: None
    )
    monkeypatch.setattr(service.repo, "ebay_sales_amount", lambda _month: None)
    monkeypatch.setattr(service.repo, "usd_rate", lambda _month: None)

    result = service.get_department_summary("2026-07")
    rows = {row["department_code"]: row for row in result["items"]}

    assert requested_months == ["2026-08"]
    assert requested_ctu_months == ["2026-08"]
    assert rows["AMZ-EU"]["ctu_over_30_cost"] == "10"
    assert rows["AMZ-US2-MJ"]["ctu_over_30_cost"] == "40"
    assert rows["AMZ-US1-ZXY"]["ctu_over_30_cost"] == "40"
    assert rows["AUTO-PARTS-TOTAL"]["ctu_over_30_cost"] == "107"
    assert rows["AUTO-PARTS-TOTAL"]["ctu_cost_month"] == "2026-08"
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


def test_department_summary_uses_report_month_sales_volume(monkeypatch):
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
    monkeypatch.setattr(
        service.clearance_repo, "ctu_over_30_costs", lambda _month: {}
    )
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
    monkeypatch.setattr(service.repo, "usd_rate", lambda month: Decimal("10"))

    result = service.get_department_summary("2026-07")
    rows = {row["department_code"]: row for row in result["items"]}

    assert rows["EBAY-1"]["ctu_over_30_cost"] is None
    assert rows["AUTO-PARTS-TOTAL"]["ctu_over_30_cost"] is None
    assert rows["EBAY-1"]["ctu_cost_month"] == "2026-08"
    assert rows["EBAY-1"]["monthly_sales_qty"] == "9"
    assert rows["AMZ-EU"]["monthly_sales_qty"] == "12"
    assert rows["AMZ-US1"]["monthly_sales_qty"] == "0"
    assert rows["AUTO-PARTS-TOTAL"]["monthly_sales_qty"] == "21"
    assert rows["AUTO-PARTS-TOTAL"]["sales_volume_month"] == "2026-08"
    assert rows["EBAY-1"]["actual_achievement_amount"] == "90"
    assert rows["AMZ-EU"]["actual_achievement_amount"] == "120"
    assert rows["AUTO-PARTS-TOTAL"]["actual_achievement_amount"] == "210"
    assert rows["EBAY-1"]["actual_achievement_amount_usd"] == "9.00"
    assert rows["AMZ-EU"]["actual_achievement_amount_usd"] == "12.00"
    assert rows["AUTO-PARTS-TOTAL"]["actual_achievement_amount_usd"] == "21.00"
    assert result["rate_month"] == "2026-08"
    assert result["usd_rate"] == "10"
    assert result["report_month"] == "2026-08"

    monkeypatch.setattr(service.repo, "usd_rate", lambda _month: None)
    missing_rate_result = service.get_department_summary("2026-07")
    missing_rate_rows = {
        row["department_code"]: row
        for row in missing_rate_result["items"]
    }
    assert missing_rate_rows["EBAY-1"]["actual_achievement_amount"] == "90"
    assert missing_rate_rows["EBAY-1"]["actual_achievement_amount_usd"] is None
    assert missing_rate_rows["EBAY-1"]["sales_target_usd"] is None
    assert missing_rate_rows["EBAY-1"]["target_achievement_rate"] is None
    assert missing_rate_result["usd_rate"] is None


def test_report_json_precision_is_bounded_without_changing_internal_math():
    row = {
        "sales_target_usd": Decimal("506219.4952943543679395461773"),
        "actual_achievement_amount_usd": Decimal("417383.123456789"),
        "target_achievement_rate": Decimal("0.8245864139721966188835947492"),
    }

    result = service._report_json_ready(row)

    assert result["sales_target_usd"] == "506219.50"
    assert result["actual_achievement_amount_usd"] == "417383.12"
    assert result["target_achievement_rate"] == "0.824586"
    assert row["sales_target_usd"] == Decimal(
        "506219.4952943543679395461773"
    )


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
