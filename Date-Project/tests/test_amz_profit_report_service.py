from decimal import Decimal

import pytest

from backend.services import amz_profit_report_service as service


SHOPS = {
    "1": "US1-川服喜-US",
    "2": "US1-川服喜-CA",
    "3": "US3-新志楠-US",
    "4": "EU-智贸云-DE",
    "12519": "US2-斯鑫雅-US",
    "9": "信博嘉立-DE",
}


def settlement(sid, msku, qty, amount, gross, **extra):
    row = {column: Decimal("0") for column in service.MARGIN_BASE_COLUMNS}
    row.update({
        "sid": sid, "msku": msku, "local_sku": extra.pop("local_sku", ""), "store_name": "",
        "total_sales_quantity": qty, "total_sales_amount": Decimal(amount),
        "gross_profit": Decimal(gross), "fba_returns_quantity": extra.pop("returns", 0),
        "refunds_quantity": extra.pop("refunds", 0),
        "total_ads_cost": Decimal(extra.pop("ads_cost", "0")),
        "total_ads_sales": Decimal(extra.pop("ads_sales", "0")),
    })
    row.update({key: Decimal(value) for key, value in extra.items()})
    return row


def order(sid, msku, amount, gross, local_sku=""):
    return {"sid": sid, "msku": msku, "local_sku": local_sku,
            "amount": Decimal(amount), "gross_profit": Decimal(gross)}


@pytest.fixture
def data(monkeypatch):
    months = {
        "2026-09": {
            "settlement": [
                settlement("1", "A", 100, "1000", "200", returns=10, refunds=5,
                           ads_cost="-50", ads_sales="400", total_sales_refunds="-100"),
                settlement("2", "B", 20, "300", "30"),
                settlement("3", "C", 10, "100", "5"),
                settlement("4", "ZMY-1", 5, "50", "10", local_sku="BMW-001"),
                settlement("4", "PLAIN", 7, "70", "7"),     # special store, no zmy/dsq
                settlement("12519", "X", 9, "90", "9"),      # excluded shop
                settlement("9", "Y", 3, "30", "3"),          # no group prefix
            ],
            "order": [order("1", "A", "1100", "330"), order("3", "C", "120", "12")],
        },
        "2026-08": {
            "settlement": [settlement("1", "A", 80, "800", "100")],
            "order": [],
        },
    }
    monkeypatch.setattr(service.repo, "msku_month_rows", lambda m: months.get(m, {}).get("settlement", []))
    monkeypatch.setattr(service.repo, "order_month_rows", lambda m: months.get(m, {}).get("order", []))
    monkeypatch.setattr(service.inventory_repo, "amazon_shop_map", lambda: SHOPS)
    monkeypatch.setattr(service.inventory_repo, "owner_rules", lambda month, platform: [
        {"group_code": "US1", "rule_type": "STORE", "match_key": "川服喜", "principal_name": "张三"},
        {"group_code": "EU", "rule_type": "BRAND", "match_key": "BMW", "principal_name": "李四"},
    ])
    targets = []
    monkeypatch.setattr(service.inventory, "get_dimension_summary", lambda dim, month: (
        targets.append((dim, month)) or {"stat_month": month, "items": [
            {"platform_code": "AMZ", "department_code": "AMZ-US1",
             "dimension_value": "川服喜" if dim == "STORE" else "张三", "sales_target_usd": "2600.00"},
            {"platform_code": "EBAY", "department_code": "EBAY-1",
             "dimension_value": "王五", "sales_target_usd": "999"},
            {"platform_code": "AMZ", "department_code": "AMZ-US2",
             "dimension_value": "旌越问" if dim == "STORE" else "赵六", "sales_target_usd": "500"},
        ]}
    ))
    return targets


def test_store_dimension_merges_sites_and_applies_inventory_exclusions(data):
    report = service.get_report("2026-09", "STORE")

    assert data == [("STORE", "2026-08")]
    assert (report["start_month"], report["end_month"]) == ("2026-09", "2026-09")
    assert (report["previous_start_month"], report["previous_end_month"]) == ("2026-08", "2026-08")
    rows = {(r["department_code"], r["dimension_value"]): r for r in report["rows"]}
    assert set(rows) == {
        ("AMZ-US1", "川服喜"), ("AMZ-US2-MJ", "新志楠"), ("AMZ-EU", "智贸云"), ("AMZ-US2", "旌越问"),
    }
    us1 = rows[("AMZ-US1", "川服喜")]
    assert us1["sales_qty"] == "120"          # US + CA merged
    assert us1["sales_amount"] == "1300.00"
    assert us1["target_usd"] == "2600.00"
    assert us1["achievement_rate"] == "0.500000"
    assert us1["sales_mom"] == "0.625000"     # (1300-800)/800
    assert us1["order_gross_profit"] == "330.00"
    assert us1["order_gross_margin"] == "0.300000"   # 330/1100 order amount
    assert us1["settlement_gross_profit"] == "230.00"
    assert us1["settlement_gross_margin"] == "0.191667"  # 230/(1300-100)
    assert us1["return_rate"] == "0.083333"
    assert us1["refund_rate"] == "0.041667"
    assert us1["acos"] == "0.125000"           # |−50| / 400
    assert us1["ad_ratio"] == "0.038462"       # 50 / 1300
    assert us1["previous"]["sales_amount"] == "800.00"
    assert rows[("AMZ-EU", "智贸云")]["sales_amount"] == "50.00"   # only ZMY-1 kept
    target_only = rows[("AMZ-US2", "旌越问")]
    assert target_only["sales_amount"] == "0.00" and target_only["achievement_rate"] == "0.000000"
    assert report["excluded"] == {
        "excluded_shop": 1, "excluded_special_msku": 1, "unmatched_department": 1,
    }
    assert report["total"]["target_usd"] == "3100.00"
    assert report["total"]["sales_amount"] == "1450.00"


def test_owner_dimension_uses_amazon_owner_rules(data):
    report = service.get_report("2026-09", "OWNER")

    rows = {(r["department_code"], r["dimension_value"]): r for r in report["rows"]}
    assert rows[("AMZ-US1", "张三")]["sales_amount"] == "1300.00"
    assert rows[("AMZ-EU", "李四")]["sales_amount"] == "50.00"     # EU brand from local SKU
    assert rows[("AMZ-US2-MJ", "未分配")]["sales_amount"] == "100.00"
    assert rows[("AMZ-US1", "张三")]["target_usd"] == "2600.00"
    assert ("EBAY-1", "王五") not in rows


def test_missing_order_or_previous_month_is_reported(monkeypatch, data):
    monkeypatch.setattr(service.repo, "order_month_rows", lambda m: [])
    report = service.get_report("2026-10", "STORE")
    assert report["settlement_ready"] is False
    assert report["order_ready"] is False
    assert report["previous_ready"] is True
    assert report["total"]["order_gross_margin"] is None
    # Never-pulled month: blanks instead of zero sales or a 0% achievement.
    assert report["total"]["sales_amount"] is None
    assert report["total"]["achievement_rate"] is None
    assert report["total"]["target_usd"] == "3100.00"


def test_target_failure_does_not_break_report(monkeypatch, data):
    def boom(*_args):
        raise RuntimeError("db down")
    monkeypatch.setattr(service.inventory, "get_dimension_summary", boom)
    report = service.get_report("2026-09", "STORE")
    assert report["target_note"] == "2026-09：月度库存销售目标读取失败"
    assert all(row["target_usd"] is None for row in report["rows"])


def test_invalid_dimension_is_rejected(data):
    with pytest.raises(ValueError):
        service.get_report("2026-09", "BRAND")


def test_export_writes_the_selected_period_summed_like_the_page(monkeypatch):
    from io import BytesIO

    from openpyxl import load_workbook

    monkeypatch.setattr(service, "list_months", lambda limit=24: [
        {"stat_month": "2026-08"}, {"stat_month": "2026-09"},
    ])
    calls = []

    def fake_report(month, dim, end_month=None, currency="USD"):
        calls.append((month, end_month, dim))
        row = {"department_code": "AMZ-US1", "dimension_value": "川服喜" if dim == "STORE" else "张三",
               **{field: None for field, _label, _kind in service.EXPORT_COLUMNS}}
        row.update(sales_qty="12", sales_amount="100.50", achievement_rate="0.5", target_usd=None)
        return {"rows": [row], "total": {**row, "sales_amount": "100.50"},
                "missing_settlement_months": ["2026-07"], "missing_order_months": [],
                "previous_start_month": "2026-04", "previous_end_month": "2026-06", "previous_ready": False}

    monkeypatch.setattr(service, "get_report", fake_report)
    name, content = service.export_report("2026-07", "2026-09", ["STORE", "OWNER"])

    assert name == "AMZ利润报表-2026-07至2026-09-美元.xlsx"   # named after what was chosen
    assert calls == [("2026-07", "2026-09", "STORE"), ("2026-07", "2026-09", "OWNER")]  # one period sum
    book = load_workbook(BytesIO(content))
    assert book.sheetnames == ["店铺", "个人"]
    sheet = book["店铺"]
    assert [cell.value for cell in sheet[1]][:5] == ["统计区间", "组别", "店铺", "业绩目标（USD）", "达成率"]
    assert [cell.value for cell in sheet[2]][:3] == ["2026-07 至 2026-09", "合计", None]
    assert [cell.value for cell in sheet[3]][:3] == ["2026-07 至 2026-09", "US1", "川服喜"]
    assert sheet.max_row == 3 + 1 + 2                        # rows, blank line, two notes
    assert sheet.cell(3, 4).value is None                    # missing target stays blank
    assert sheet.cell(3, 5).value == 0.5 and sheet.cell(3, 5).number_format == "0.00%"
    assert sheet.cell(3, 6).value == 12
    assert "2026-07 结算数据未拉取" in sheet.cell(5, 1).value
    assert "上期 2026-04 至 2026-06" in sheet.cell(6, 1).value
    assert book["个人"].cell(1, 3).value == "负责人"


@pytest.mark.parametrize(("start", "end", "message"), [
    ("2026-09", "2026-08", "开始月份不能晚于结束月份"),
    ("2024-01", "2026-09", "一次最多查询"),
])
def test_export_rejects_invalid_ranges(start, end, message):
    with pytest.raises(ValueError, match=message):
        service.export_report(start, end)


def test_export_rejects_range_without_data(monkeypatch):
    monkeypatch.setattr(service, "list_months", lambda limit=24: [{"stat_month": "2026-09"}])
    with pytest.raises(ValueError, match="没有已拉取的数据"):
        service.export_report("2026-05", "2026-06", ["STORE"])


def test_group_dimension_sums_departments_with_inventory_group_targets(monkeypatch, data):
    monkeypatch.setattr(service.inventory, "get_department_summary", lambda month: {
        "stat_month": month, "items": [
            {"department_code": "AMZ-US1", "sales_target_usd": "2000.00", "is_total": 0},
            {"department_code": "AMZ-US2-MJ", "sales_target_usd": "300.00", "is_total": 0},
            {"department_code": "AMZ-US3", "sales_target_usd": "999.00", "is_total": 0},   # display row
            {"department_code": "EBAY-1", "sales_target_usd": "888.00", "is_total": 0},
            {"department_code": "AUTO-PARTS-TOTAL", "sales_target_usd": "5000.00", "is_total": 1},
        ]})

    report = service.get_report("2026-09", "GROUP")

    rows = {r["department_code"]: r for r in report["rows"]}
    assert set(rows) == {"AMZ-EU", "AMZ-US1", "AMZ-US2-MJ"}
    assert rows["AMZ-US1"]["dimension_value"] == "US1"
    assert rows["AMZ-US1"]["sales_amount"] == "1300.00"      # 川服喜 US + CA
    assert rows["AMZ-US1"]["target_usd"] == "2000.00"
    assert rows["AMZ-US1"]["achievement_rate"] == "0.650000"
    assert rows["AMZ-US2-MJ"]["target_usd"] == "300.00"
    assert rows["AMZ-EU"]["target_usd"] is None
    assert report["total"]["target_usd"] == "2300.00"         # US3 display row and eBay excluded
    assert report["total"]["sales_amount"] == service.get_report("2026-09", "STORE")["total"]["sales_amount"]


def test_export_includes_group_sheet_without_name_column(monkeypatch):
    from io import BytesIO

    from openpyxl import load_workbook

    monkeypatch.setattr(service, "list_months", lambda limit=24: [{"stat_month": "2026-09"}])
    row = {"department_code": "AMZ-US1", "dimension_value": "US1",
           **{field: None for field, _label, _kind in service.EXPORT_COLUMNS}, "sales_qty": "5"}
    monkeypatch.setattr(service, "get_report", lambda month, dim, end_month=None, currency="USD": {"rows": [row], "total": dict(row)})

    name, content = service.export_report("2026-09", "2026-09")
    assert name == "AMZ利润报表-2026-09-美元.xlsx"

    book = load_workbook(BytesIO(content))
    assert book.sheetnames == ["组别", "店铺", "个人"]
    group = book["组别"]
    assert [c.value for c in group[1]][:3] == ["统计区间", "组别", "业绩目标（USD）"]
    assert [c.value for c in group[3]][:2] == ["2026-09", "US1"]
    assert group.cell(3, 5).value == 5 and group.cell(3, 5).number_format == "#,##0"


def test_month_range_sums_months_targets_and_compares_equal_length_period(data):
    report = service.get_report("2026-08", "STORE", end_month="2026-09")

    assert report["months"] == ["2026-08", "2026-09"]
    assert (report["previous_start_month"], report["previous_end_month"]) == ("2026-06", "2026-07")
    assert data == [("STORE", "2026-07"), ("STORE", "2026-08")]   # each month's own target snapshot
    rows = {(r["department_code"], r["dimension_value"]): r for r in report["rows"]}
    us1 = rows[("AMZ-US1", "川服喜")]
    assert us1["sales_amount"] == "2100.00"          # 800 (Aug) + 1300 (Sep)
    assert us1["sales_qty"] == "200"
    assert us1["target_usd"] == "5200.00"            # 2600 per month
    assert us1["achievement_rate"] == "0.403846"
    assert us1["order_gross_profit"] == "330.00"     # only September has order data
    assert report["missing_order_months"] == ["2026-08"]
    assert report["missing_settlement_months"] == []
    assert report["previous_ready"] is False         # June/July never pulled
    assert us1["previous"] is None and us1["sales_mom"] is None


def test_period_with_partly_missing_previous_months_shows_no_arrows(data):
    report = service.get_report("2026-09", "STORE", end_month="2026-10")
    # previous period is 2026-07..2026-08, July missing -> no comparison
    assert report["previous_ready"] is False
    assert report["missing_settlement_months"] == ["2026-10"]
    assert report["settlement_ready"] is True
    assert report["total"]["previous"] is None and report["total"]["sales_mom"] is None
    assert all(row["previous"] is None and row["sales_mom"] is None for row in report["rows"])


def test_month_range_validation(data):
    with pytest.raises(ValueError, match="开始月份不能晚于结束月份"):
        service.get_report("2026-09", "STORE", end_month="2026-08")
    with pytest.raises(ValueError, match="一次最多查询"):
        service.get_report("2024-01", "STORE", end_month="2026-09")


def test_cny_period_uses_the_my_rate_of_its_largest_month(monkeypatch, data):
    asked = []
    monkeypatch.setattr(service.repo, "usd_my_rates", lambda months: asked.extend(months) or {
        "2026-07": Decimal("7.200000"), "2026-08": Decimal("7.000000"), "2026-09": Decimal("6.500000"),
    })

    report = service.get_report("2026-08", "STORE", end_month="2026-09", currency="CNY")

    assert report["currency_code"] == "CNY"
    assert (report["exchange_rate_month"], report["exchange_rate"]) == ("2026-09", "6.500000")
    assert report["previous_exchange_rate"] == "7.200000"    # previous period 06..07 -> July
    assert sorted(asked) == ["2026-07", "2026-09"]           # only each period's last month
    us1 = {(r["department_code"], r["dimension_value"]): r for r in report["rows"]}[("AMZ-US1", "川服喜")]
    assert us1["sales_amount"] == "13650.00"         # (800 + 1300) x 6.5, August not 7
    assert us1["sales_qty"] == "200"                 # quantities are not converted
    assert us1["target_usd"] == "33800.00"           # 5200 x 6.5
    assert us1["order_gross_profit"] == "2145.00"    # 330 x 6.5
    assert us1["achievement_rate"] == "0.403846"     # one rate -> same as USD


def test_cny_single_month_keeps_rates_unchanged_by_currency(monkeypatch, data):
    monkeypatch.setattr(service.repo, "usd_my_rates", lambda months: {"2026-09": Decimal("6.582861")})
    cny = service.get_report("2026-09", "STORE", currency="CNY")
    usd = service.get_report("2026-09", "STORE")
    for key in ("achievement_rate", "settlement_gross_margin", "acos", "ad_ratio", "return_rate"):
        assert cny["total"][key] == usd["total"][key], key
    assert Decimal(cny["total"]["sales_amount"]) == (Decimal(usd["total"]["sales_amount"]) * Decimal("6.582861")).quantize(Decimal("0.01"))


def test_cny_refuses_months_without_my_rate(monkeypatch, data):
    monkeypatch.setattr(service.repo, "usd_my_rates", lambda months: {"2026-08": Decimal("6.5")})
    with pytest.raises(ValueError, match="2026-09 缺少领星 USD「我的汇率」"):
        service.get_report("2026-08", "STORE", end_month="2026-09", currency="CNY")
    # the largest month is enough; earlier months need no rate of their own
    monkeypatch.setattr(service.repo, "usd_my_rates", lambda months: {"2026-09": Decimal("6.5")})
    report = service.get_report("2026-08", "STORE", end_month="2026-09", currency="CNY")
    assert report["previous_exchange_rate"] is None
    assert report["previous_missing_rate"] is False    # June/July have no data: a data gap, not a rate gap


def test_previous_period_without_rate_is_reported_apart_from_missing_data(monkeypatch, data):
    # 2026-09 vs 2026-08: August data is there, only its 我的汇率 is missing
    monkeypatch.setattr(service.repo, "usd_my_rates", lambda months: {"2026-09": Decimal("6.5")})
    report = service.get_report("2026-09", "STORE", currency="CNY")
    assert report["previous_missing_rate"] is True
    assert report["previous_ready"] is False
    assert report["total"]["previous"] is None and report["total"]["sales_mom"] is None
    usd = service.get_report("2026-09", "STORE")
    assert usd["previous_ready"] is True and usd["previous_missing_rate"] is False
    with pytest.raises(ValueError, match="currency 必须是 CNY 或 USD"):
        service.get_report("2026-09", "STORE", currency="EUR")


def test_export_headers_and_note_follow_currency(monkeypatch, data):
    from io import BytesIO

    from openpyxl import load_workbook

    monkeypatch.setattr(service, "list_months", lambda limit=24: [{"stat_month": "2026-09"}])
    monkeypatch.setattr(service.repo, "usd_my_rates", lambda months: {"2026-09": Decimal("6.5")})
    name, content = service.export_report("2026-09", "2026-09", ["STORE"], currency="CNY")
    assert name == "AMZ利润报表-2026-09-人民币.xlsx"
    sheet = load_workbook(BytesIO(content))["店铺"]
    assert sheet.cell(1, 4).value == "业绩目标（CNY）"
    notes = [sheet.cell(row, 1).value for row in range(1, sheet.max_row + 1)]
    assert "说明：金额为人民币，整个时间段统一按最大月份 2026-09 的领星 USD「我的汇率」6.5 换算" in notes
