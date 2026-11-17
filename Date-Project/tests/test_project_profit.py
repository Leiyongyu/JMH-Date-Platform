"""项目利润总表：主体/组别识别、店铺维度口径、小组表公式、eBay 利润明细表解析与接口。"""
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.services import project_profit_service as service


def msku(store, msku_code="SKU-1", **values):
    row = {"store_name": store, "msku": msku_code, "other_fees": values.pop("fees", {})}
    row.update(values)
    return row


def test_entity_of_reads_group_prefix_and_falls_back_for_closed_stores():
    assert service.entity_of("EU-主体01-DE") == ("EU", "主体01")
    assert service.entity_of("US3-主体27-US") == ("US3", "主体27")
    assert service.entity_of("主体03-DE") == ("EU", "主体03"), "无组别前缀的关停店铺照手工表归 EU"
    assert service.entity_of("某新店-US") == (service.UNGROUPED, "某新店")


def test_store_sums_follow_the_finance_sheet_columns():
    rows = [msku("EU-主体01-DE", sales_amount=2212, fba_inventory_credit=383.54, shipping_credits=278.31,
                 promotional_rebates=-25.77, sales_refunds=-1034.23, fee_refunds=107.08, platform_fee=-371.92,
                 fba_delivery_fee=-561.08, ads_cost=-160.15, promotion_fee=-30.77, storage_fee=-916.31,
                 sales_tax=100, market_tax=-90, purchase_cost=-1942.66, first_leg_cost=-371.76,
                 gross_profit=-2517.06, sales_qty=10, refunds_qty=2, fees={"店铺运营费": "-83.33"})]
    values = service.store_sums(rows)[("EU", "主体01")]
    # 手工表样例行：退款额合计 -674.61、平台收入 1920.92（领星口径）
    assert values["refund_total"] == Decimal("-674.61")
    assert values["platform_income"] == Decimal("1920.93")
    assert values["ads"] == Decimal("-190.92")
    assert values["platform_expense"] == Decimal("-2030.23"), "平台支出合计含净税费 100-90"
    assert values["platform_receipt"] == values["platform_income"] + values["platform_expense"]
    assert values["store_operation"] == Decimal("-83.33")
    assert values["sales_qty"] == 10 and values["refunds_qty"] == 2


def test_foreign_msku_of_special_stores_only_keeps_store_operation_fee():
    rows = [msku("EU-主体05-DE", "ZMY-DE-1", sales_amount=100, gross_profit=20, fees={"店铺运营费": -5}),
            msku("EU-主体05-DE", "22-QLA0-M28P", sales_amount=999, gross_profit=500, fees={"店铺运营费": -7})]
    sums = service.store_sums(rows)
    values = sums[("EU", "主体05")]
    assert values["sales_amount"] == 100, "非 zmy 的 MSKU 不算销售额"
    assert values["store_operation"] == -5 and values["gross_profit"] == 20
    assert sums[("US3", "主体27")]["store_operation"] == -7, "它的店铺运营费照 2026-10 手工表记到主体27"


def test_closed_store_xinbojiali_only_counts_xbjl_msku():
    # 2026-09 手工表：主体03只计 XBJL 开头的 MSKU，未配对的 57-YSGX-X294 / XZ-G5MI-KAAM 不在表里。
    rows = [msku("主体03-DE", "XBJL-DE-10002-0002", sales_refunds=-695.92, fee_refunds=77.7),
            msku("主体03-DE", "xbjl-de-20055-0128", storage_fee=-10),
            msku("主体03-DE", "XZ-G5MI-KAAM", sales_amount=2365.35, ads_cost=-500, fees={"店铺运营费": -3}),
            msku("EU-主体01-DE", "57-YSGX-X294", sales_amount=50)]
    sums = service.store_sums(rows)
    values = sums[("EU", "主体03")]
    assert values["platform_income"] == Decimal("-618.22")
    assert values["sales_amount"] == 0 and values["ads"] == 0 and values["storage"] == -10
    assert values["store_operation"] == -3, "被剔除 MSKU 的店铺运营费仍记在主体上"
    assert sums[("EU", "主体01")]["sales_amount"] == 50, "规则只针对主体03"


def test_statement_formulas_match_the_finance_sheet():
    sums = service.store_sums([msku("EU-主体01-DE", sales_amount=1000, platform_fee=-150, purchase_cost=-400,
                                    first_leg_cost=-50, gross_profit=300, sales_qty=8, refunds_qty=1,
                                    removal_cost=-999, transit_loss=-30,
                                    fees={"店铺运营费": -5, "税务风险金": -10, "店租费（法人补贴等）": -4,
                                          "滞销库存费用": -1})])
    items = [
        # 这三项 AMZ 组现在由领星文件自动算，存着的手工值不再生效
        {"group_code": "EU", "item_code": "transit_credit", "amount": 777, "source": "MANUAL"},
        {"group_code": "EU", "item_code": "removal_destroy", "amount": -1, "source": "MANUAL"},
        {"group_code": "EU", "item_code": "manual_allocation", "amount": 888, "source": "MANUAL"},
        {"group_code": "EBAY", "item_code": "manual_allocation", "amount": 7, "source": "MANUAL"},
        {"group_code": "EU", "item_code": "labor_cost", "amount": -60, "source": "MANUAL"},
        {"group_code": "EU", "item_code": "headcount", "amount": 2, "source": "MANUAL"},
        {"group_code": "EU", "item_code": "software_allocation", "amount": -10, "source": "MANUAL"},
        {"group_code": "EU", "item_code": "west_rent", "amount": -25, "source": "MANUAL"},
        {"group_code": "EBAY", "item_code": "platform_income", "amount": 500, "source": "UPLOAD"},
        {"group_code": "EBAY", "item_code": "platform_expense", "amount": -100, "source": "UPLOAD"},
        {"group_code": "EBAY", "item_code": "order_qty", "amount": 2, "source": "UPLOAD"},
        {"group_code": "EBAY", "item_code": "refund_rate", "amount": "0.5", "source": "UPLOAD"},
        {"group_code": "US1", "item_code": "platform_income", "amount": 999, "source": "MANUAL"},
    ]
    statement, columns = service.build_statement(sums, items)
    eu, ebay, total = columns["EU"], columns["EBAY"], columns["TOTAL"]
    assert eu["platform_income"] == 1000 and eu["platform_expense"] == -150
    assert eu["removal_destroy"] == -999 and eu["transit_credit"] == 30, "途损成本 -30 → 抵扣 +30"
    assert eu["manual_allocation"] == 15, "店租 + 税务风险金 + 滞销库存费用 取反加回"
    assert eu["store_operation"] == -20, "店铺运营费仍是全部自定义费用"
    assert eu["variable_subtotal"] == -400 + 30 - 50 - 20, "移除只展示，不进变动成本小计"
    assert eu["project_gross"] == 1000 - 150 - 440
    assert eu["group_net"] == eu["project_gross"] - 60
    assert eu["net_profit"] == eu["group_net"] + 15 - 10 - 25
    assert eu["per_capita"] == 500 and eu["refund_rate"] == Decimal(1) / Decimal(8)
    assert columns["US1"]["platform_income"] is None, "AMZ 自动项不接受手工值；该组没有领星数据时为空而不是 0"
    assert ebay["project_gross"] == 400
    assert ebay["manual_allocation"] == 7 and ebay["net_profit"] == 407, "eBay 的其他店铺运营费上传后仍可手工改"
    assert total["platform_income"] == 1500
    assert total["refund_rate"] == (Decimal(1) / 8 * 8 + Decimal("0.5") * 2) / 10, "合计退款率按销量加权"
    row = next(r for r in statement if r["code"] == "labor_ratio")
    assert row["levels"]["EU"] == "yellow", "人力占毛利 60/410 介于 12% 与 15% 之间"
    income = next(r for r in statement if r["code"] == "platform_income")
    assert income["sources"] == {"EBAY": "UPLOAD", "EU": "AUTO"}
    assert income["values"]["US2"] is None
    assert "EBAY" in income["editable"] and "EU" not in income["editable"]


def test_monitoring_collection_and_target_rows_follow_the_finance_sheet():
    sums = service.store_sums([msku("EU-主体01-DE", sales_amount=1000, purchase_cost=-400, gross_profit=600,
                                    fees={"税务风险金": -10})])
    item = lambda code, amount, group="EU": {"group_code": group, "item_code": code, "amount": amount,  # noqa: E731
                                              "source": "MANUAL"}
    items = [item("headcount", 2), item("labor_cost", -100), item("west_rent", -20), item("east_rent", -30),
             item("software_allocation", -5), item("collection", 800), item("monthly_target", 1200),
             item("goods_loss", -77), item("other_income", 66), item("annual_target", 9000, "US1")]
    statement, columns = service.build_statement(sums, items, prior_gross={"EU": Decimal(2000)},
                                                 annual_targets={"EU": Decimal(10000), "US1": Decimal(1)})
    eu = columns["EU"]
    assert eu["project_gross"] == 1000 - 400 - 10, "货损、其他收入只展示，不进毛利"
    assert eu["goods_loss"] == -77 and eu["other_income"] == 66
    assert eu["per_capita_gross"] == eu["project_gross"] / 2
    assert eu["rent_ratio"] == Decimal(-50) / 1000
    assert eu["monthly_cost"] == eu["variable_subtotal"] + (-50) + (-100) + 10 + (-5), "变动 + 固定 + 人力 + 其他店铺运营费 + 其他费用"
    assert eu["collection_rate"] == Decimal("0.8") and eu["monthly_rate"] == eu["project_gross"] / 1200
    assert eu["annual_target"] == 10000 and eu["annual_rate"] == (eu["project_gross"] + 2000) / 10000, "当年累计毛利 / 年度目标（沿用）"
    assert columns["US1"]["annual_target"] == 9000, "本月填了就用本月的，不沿用"
    assert columns["TOTAL"]["annual_target"] == 19000
    rows = {row["code"]: row for row in statement}
    assert rows["annual_target"]["sources"]["EU"] == "CARRY" and rows["annual_target"]["sources"]["US1"] == "MANUAL"
    assert rows["per_capita_gross"]["levels"]["EU"] == "yellow", "人均毛利 <5 万黄色预警"
    for code in ("goods_loss", "other_income", "collection", "monthly_target", "annual_target"):
        assert set(rows[code]["editable"]) == set(service.GROUPS), code


def test_year_context_sums_prior_months_and_carries_the_annual_target(monkeypatch):
    service._GROSS_CACHE.clear()
    monkeypatch.setattr(service.repo, "months", lambda limit=36: ["2026-10", "2026-09", "2026-08", "2025-12"])
    items = {"2026-08": [{"group_code": "EU", "item_code": "annual_target", "amount": 5000, "source": "MANUAL"}],
             "2026-09": [{"group_code": "EU", "item_code": "annual_target", "amount": 6000, "source": "MANUAL"}]}
    monkeypatch.setattr(service.repo, "items", lambda month: items.get(month, []))
    monkeypatch.setattr(service.repo, "amz_upload", lambda month: {"uploaded_at": month})
    reads = []
    monkeypatch.setattr(service.repo, "msku_rows", lambda month: reads.append(month) or [
        msku("EU-主体01-DE", sales_amount=100 if month == "2026-08" else 200)])
    prior, targets = service._year_context("2026-10")
    assert prior == {"EU": 300} and targets == {"EU": 6000}, "只算当年 10 月以前，目标取最近一次"
    service._year_context("2026-10")
    assert reads == ["2026-08", "2026-09"], "数据没变时用缓存，不重复读库"


def test_save_items_rejects_auto_items_of_amz_groups(monkeypatch):
    monkeypatch.setattr(service.repo, "save_items", lambda *args: pytest.fail("不应写库"))
    with pytest.raises(ValueError, match="不能手工录入"):
        service.save_items({"stat_month": "2026-09", "items": [
            {"group_code": "EU", "item_code": "platform_income", "amount": 1}]}, "admin")
    with pytest.raises(ValueError, match="格式不正确"):
        service.save_items({"stat_month": "2026-09", "items": [
            {"group_code": "EU", "item_code": "labor_cost", "amount": "abc"}]}, "admin")


def test_save_items_passes_clears_as_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(service.repo, "save_items",
                        lambda month, values, operator, source: seen.update(values=values, source=source) or 2)
    result = service.save_items({"stat_month": "2026-09", "items": [
        {"group_code": "eu", "item_code": "labor_cost", "amount": "-1,234.5"},
        {"group_code": "EBAY", "item_code": "platform_income", "amount": ""}]}, "admin")
    assert seen["values"] == [("EU", "labor_cost", Decimal("-1234.5")), ("EBAY", "platform_income", None)]
    assert seen["source"] == "MANUAL" and result["saved"] == 2


def ebay_workbook(month_label="202610"):
    wb = Workbook()
    summary = wb.active
    summary.title = "汇总"
    summary.append(["日期", "平台", "组别", "站点", "平台收入-总(RMB)", "平台支出(RMB）-总", "平台净收入",
                    "销售采购成本(RMB)", "头程成本(RMB)", "海外仓-尾程(RMB)", "海外仓-仓储（RMB）",
                    "店铺运营费用-(紫鸟等)", "资金占用费-超龄货值", "毛利(RMB)", "积分抵扣", "税务风险金", "GU仓销毁"])
    summary.append([month_label, "eBay", "US", "US", 400, -90, 310, -200, -20, -50, -5, -10, -1, 0, 1, -4, -2])
    summary.append([f"{month_label}小计", None, None, None, 1000, -240, 750, -500, -40, -100, -10, -20, -3,
                    750 - 500 - 40 - 100 - 10 - 20 - 3 + 2 - 10 - 6, 2, -10, -6])
    analysis = wb.create_sheet("eaby分析")
    analysis.append([None, None, None, "交易报告指标分析"])
    analysis.append(["组别", "日期", "收款净额（人民币）", "广告费"])
    analysis.append(["ebay", int(month_label), 750, -66])
    tx = wb.create_sheet("eaby交易报告-核算-去除发放款项")
    tx.append(["日期", "店铺", "交易创建日期", "类型", "数量"])
    for kind, qty in (("Order", 1), ("Order", 2), ("Refund", None), ("Other fee", None), ("订单", 3)):
        tx.append([month_label, "s", None, kind, qty])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_parse_ebay_workbook_maps_the_summary_and_keeps_gross_profit():
    values, check = service.parse_ebay_workbook(ebay_workbook(), "2026-10")
    assert values["platform_income"] == 1000
    # 口径照 2026-10 手工表
    assert values["platform_expense"] == -240 - 100 - 10, "平台支出 = 平台支出(RMB)-总 + 谷仓尾程 + 仓储"
    assert values["fba_logistics"] == -110 and values["ads"] == -66
    assert values["purchase_cost"] == -500 - 6 and values["first_leg"] == -40, "采购含 GU仓销毁"
    assert values["transit_credit"] == 2 and values["removal_destroy"] == -6 and values["aged_fee"] == -3
    assert values["store_operation"] == -20 - 10, "店铺运营费不含资金占用费、GU仓销毁"
    assert values["order_qty"] == 6 and values["refund_rate"] == Decimal(1) / Decimal(3)
    assert values["manual_allocation"] == 3 + 10, "其他店铺运营费 = −(资金占用费-超龄货值 + 税务风险金)"
    assert check["method_parts"] == {"platform_expense": 10.0, "aged_capital": 3.0}
    assert check["gross_diff"] == 0, "去掉两处口径差后，与汇总毛利一致"


def test_parse_ebay_workbook_falls_back_to_net_minus_income_without_expense_total():
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(ebay_workbook()))
    summary = wb["汇总"]
    summary.delete_cols([c.value for c in summary[1]].index("平台支出(RMB）-总") + 1)
    buffer = BytesIO()
    wb.save(buffer)
    values, check = service.parse_ebay_workbook(buffer.getvalue(), "2026-10")
    assert values["platform_expense"] == 750 - 1000 - 100 - 10 and check["gross_diff"] == 0


def test_parse_ebay_workbook_leaves_points_and_destroy_empty_when_absent():
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(ebay_workbook()))
    summary = wb["汇总"]
    header = [cell.value for cell in summary[1]]
    summary.cell(row=3, column=header.index("积分抵扣") + 1).value = 0  # 2026-09：明细全空，小计 SUM 出 0
    summary.delete_cols(header.index("GU仓销毁") + 1)
    buffer = BytesIO()
    wb.save(buffer)
    values, _check = service.parse_ebay_workbook(buffer.getvalue(), "2026-10")
    assert values["transit_credit"] is None and values["removal_destroy"] is None, "没有就显示 --，不写 0"


def test_amz_removal_transit_and_other_store_fee_follow_the_exclusion_rule():
    rows = [msku("EU-主体05-DE", "ZMY-1", removal_cost=-10, transit_loss=-2, fees={"税务风险金": -1}),
            msku("EU-主体05-DE", "22-QLA0-M28P", removal_cost=-500, transit_loss=-50,
                 fees={"店租费（法人补贴等）": -3, "店铺运营费": -9})]
    values = service.store_sums(rows)[("EU", "主体05")]
    assert values["removal_cost"] == -10 and values["transit_credit"] == 2, "非本公司 MSKU 的移除、途损不计"
    assert values["other_store_fee"] == 4, "自定义费用照店铺运营费口径：被剔除 MSKU 的也计入（取反加回）"


def test_aged_fee_is_the_slow_moving_stock_fee_by_group():
    rows = [msku("EU-主体01-DE", "A", sales_amount=10, fees={"滞销库存费用": -3, "店铺运营费": -1}),
            msku("EU-主体04-FR", "B", fees={"滞销库存费用": "-2.5"}),
            msku("EU-主体05-DE", "22-QLA0-M28P", fees={"滞销库存费用": -4})]
    statement, columns = service.build_statement(service.store_sums(rows), [
        {"group_code": "EU", "item_code": "aged_fee", "amount": -999, "source": "MANUAL"}])
    assert columns["EU"]["aged_fee"] == Decimal("-9.5"), "按组汇总，负数照记；手工值不再生效"
    assert columns["EU"]["variable_subtotal"] == -1 - 3 - 2.5, "超库龄只展示；主体05非本公司 MSKU 的费用记到 US3 主体27"
    row = next(r for r in statement if r["code"] == "aged_fee")
    assert row["sources"]["EU"] == "AUTO" and "EU" not in row["editable"] and "EBAY" in row["editable"]


def test_parse_ebay_workbook_rejects_other_months():
    with pytest.raises(ValueError, match="没有 2026-09 的小计行.*2026-10"):
        service.parse_ebay_workbook(ebay_workbook(), "2026-09")
    with pytest.raises(ValueError, match="读取文件失败"):
        service.parse_ebay_workbook(b"not an excel", "2026-10")


def test_import_ebay_saves_upload_items(monkeypatch):
    seen = {}
    monkeypatch.setattr(service.repo, "save_upload", lambda month, items, name, operator, at, check:
                        seen.update(month=month, items=dict((c, a) for _g, c, a in items), name=name, check=check))
    result = service.import_ebay(ebay_workbook(), "利润明细表202610-ebay.xlsx", "2026-10", "admin")
    assert seen["month"] == "2026-10" and seen["items"]["platform_income"] == 1000
    assert set(seen["items"]) == set(service.EBAY_UPLOAD_CODES)
    assert result["missing"] == [] and result["check"]["gross_diff"] == 0


def lingxing_workbook(rows, *, drop=None, period="2026-09~2026-09"):
    """仿领星「利润报表-MSKU」导出：第 1 行分组表头（只在每组第一列写组名），第 2 行字段名。"""
    columns = [("基础信息", name) for name in ("日期", "MSKU", "店铺", "品名", "SKU", "币种")]
    for _field, sources in service.AMZ_FILE_COLUMNS.items():
        for group, name in sources:
            columns.append((group or "商品成本-明细", name or f"{group}项"))
    columns += [("平台支出-FBA仓储费", "销毁量"), ("平台收入", "平台收入"), ("自定义费用", "店铺运营费")]
    columns = [column for column in dict.fromkeys(columns) if column[1] != drop]
    order = list(dict.fromkeys(group for group, _name in columns))
    columns = sorted(columns, key=lambda item: order.index(item[0]))  # 同组相邻，组名只写第一列
    wb = Workbook()
    sheet = wb.active
    sheet.append([group if index == 0 or columns[index - 1][0] != group else None
                  for index, (group, _name) in enumerate(columns)])
    sheet.append([name for _group, name in columns])
    for values in rows:
        base = {"日期": period, "币种": "CNY", **values}
        sheet.append([base.get(name) for _group, name in columns])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


LX_ROW = {"MSKU": "LSX-1", "店铺": "EU-主体01-DE", "SKU": "BMW-1", "品名": "后视镜", "FBA销量": 3, "FBM销量": 1,
          "退款量": 1, "FBA销售额": "1,000.50", "FBM销售额": 100, "买家运费": 10, "平台收入-收入退款额项": -50,
          "平台收入-其他收入项": 2, "平台费": -150, "平台支出-FBA仓储费项": -30, "销毁量": 9,
          "入库配置费（原合仓费）": -4, "站外推广费": -6, "店铺运营费": -8, "采购成本": -400, "毛利润": 300,
          "FBA移除采购成本": -20, "FBA移除物流成本": -2, "FBA途损补回采购成本": 5, "FBA发货途损采购成本": -12,
          "FBA发货途损物流成本": "-", "平台收入": 1062.5}


def test_parse_lingxing_msku_file_sums_columns_like_the_api_fields():
    rows, check = service.parse_lingxing_msku_workbook(
        lingxing_workbook([LX_ROW, {**LX_ROW, "FBA销售额": 0, "FBA销量": 0, "FBM销量": 0, "退款量": 0,
                                    "FBM销售额": 0, "买家运费": 0, "平台收入-收入退款额项": 0, "平台收入-其他收入项": 0,
                                    "平台收入": 0, "店铺运营费": -1},
                           {"MSKU": None, "店铺": "EU-主体01-UK", "平台收入": 0, "店铺运营费": -3}]), "2026-09")
    assert len(rows) == 2 and check["rows"] == 2 and check["stores"] == 2
    row = next(item for item in rows if item["msku"] == "LSX-1")
    assert row["sales_qty"] == 4 and row["refunds_qty"] == 1 and row["sales_amount"] == Decimal("1100.50")
    assert row["sales_refunds"] == -50 and row["other_in_amount"] == 2 and row["shipping_credits"] == 10
    assert row["storage_fee"] == -60, "仓储费整组加总（两行合并），不含销毁量 / 移除量 / 入库配置费"
    assert row["inbound_convenience_fee"] == -8 and row["custom_order_fee"] == -12
    assert row["other_fees"] == {"店铺运营费": "-9"}, "同一 店铺+MSKU 多行合并；站外推广费不进自定义费用"
    assert row["removal_cost"] == -44 and row["transit_loss"] == -14, "两行合并后：移除 2×(-22)、途损 2×(5-12)"
    assert row["local_sku"] == "BMW-1" and row["currency_code"] == "CNY"
    store_level = next(item for item in rows if item["msku"] == "-")
    assert store_level["store_name"] == "EU-主体01-UK" and store_level["other_fees"] == {"店铺运营费": "-3"}
    sums = service.store_sums(rows)[("EU", "主体01")]
    assert sums["platform_income"] == Decimal("1062.5") * 2 - Decimal("1062.5"), "计算逻辑不变：直接喂 store_sums"
    assert sums["store_operation"] == -12


def test_parse_lingxing_msku_file_rejects_wrong_currency_month_and_format():
    with pytest.raises(ValueError, match="币种为 EUR.*人民币"):
        service.parse_lingxing_msku_workbook(lingxing_workbook([{**LX_ROW, "币种": "EUR"}]), "2026-09")
    with pytest.raises(ValueError, match="文件日期是 2026-09~2026-09，与所选月份 2026-10 不一致"):
        service.parse_lingxing_msku_workbook(lingxing_workbook([LX_ROW]), "2026-10")
    with pytest.raises(ValueError, match="缺少列：平台支出 / 平台费"):
        service.parse_lingxing_msku_workbook(lingxing_workbook([LX_ROW], drop="平台费"), "2026-09")
    with pytest.raises(ValueError, match="1 行按公式算的平台收入.*第 3 行"):
        service.parse_lingxing_msku_workbook(lingxing_workbook([{**LX_ROW, "平台收入": 999}]), "2026-09")
    with pytest.raises(ValueError, match="第3行「平台费」 不是数字"):
        service.parse_lingxing_msku_workbook(lingxing_workbook([{**LX_ROW, "平台费": "abc"}]), "2026-09")
    with pytest.raises(ValueError, match="没找到表头"):
        service.parse_lingxing_msku_workbook(ebay_workbook(), "2026-09")


def test_import_amz_replaces_the_month(monkeypatch):
    seen = {}
    monkeypatch.setattr(service.repo, "save_amz_upload", lambda month, rows, name, operator, at, check:
                        seen.update(month=month, rows=rows, name=name, op=operator, check=check)
                        or {"deleted_rows": 5, "inserted_rows": len(rows)})
    result = service.import_amz(lingxing_workbook([LX_ROW]), "利润报表-MSKU.xlsx", "2026-09", "admin")
    assert seen["month"] == "2026-09" and seen["op"] == "admin" and len(seen["rows"]) == 1
    assert result["check"]["platform_income"] == 1062.5 and result["deleted_rows"] == 5
    with pytest.raises(ValueError, match="请选择领星利润报表"):
        service.import_amz(b"", "x.xlsx", "2026-09", "admin")


def test_endpoints_forward_month_operator_and_multipart_file(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.deps import require_internal_access
    from backend.api.v1 import project_profit as api

    seen = {}
    monkeypatch.setattr(api.service, "import_ebay", lambda content, name, month, operator:
                        seen.update(size=len(content), name=name, month=month, op=operator) or {"ok": 1})
    monkeypatch.setattr(api.service, "save_items", lambda payload, operator: {"saved": len(payload["items"])})
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None
    content = ebay_workbook()
    with TestClient(app) as client:
        ok = client.post("/api/v1/finance/project-profit/ebay/import",
                         params={"stat_month": "2026-10", "operator": "admin"},
                         files={"file": ("e.xlsx", content, "application/octet-stream")})
        assert ok.status_code == 200 and seen == {"size": len(content), "name": "e.xlsx", "month": "2026-10",
                                                  "op": "admin"}
        assert client.post("/api/v1/finance/project-profit/ebay/import", params={"stat_month": "2026-13"},
                           files={"file": ("e.xlsx", content)}).status_code == 422
        monkeypatch.setattr(api.service, "import_amz", lambda content, name, month, operator:
                            seen.update(amz=(len(content), name, month, operator)) or {"ok": 1})
        amz = client.post("/api/v1/finance/project-profit/amz/import",
                          params={"stat_month": "2026-09", "operator": "admin"},
                          files={"file": ("lx.xlsx", content, "application/octet-stream")})
        assert amz.status_code == 200 and seen["amz"] == (len(content), "lx.xlsx", "2026-09", "admin")
        monkeypatch.setattr(api.service, "import_amz", lambda *args: (_ for _ in ()).throw(ValueError("币种不对")))
        bad = client.post("/api/v1/finance/project-profit/amz/import", params={"stat_month": "2026-09"},
                          files={"file": ("lx.xlsx", content)})
        assert bad.status_code == 400 and bad.json()["detail"] == "币种不对"
        saved = client.put("/api/v1/finance/project-profit/items",
                           json={"stat_month": "2026-10", "items": [{"group_code": "EU"}]})
        assert saved.status_code == 200 and saved.json()["data"]["saved"] == 1


def test_migration_is_ascii_and_selects_the_database():
    text = (Path(__file__).resolve().parents[1] / "migrations" / "20261116_project_profit.sql").read_text("utf-8")
    assert text.isascii()
    assert "USE `date-project`;" in text and "SET NAMES utf8mb4;" in text
    assert "`fin_project_profit_item`" in text and "`fin_project_profit_ebay_upload`" in text
    amz = (Path(__file__).resolve().parents[1] / "migrations" / "20261116_project_profit_amz_upload.sql").read_text("utf-8")
    assert amz.isascii() and "USE `date-project`;" in amz and "SET NAMES utf8mb4;" in amz
    extra = (Path(__file__).resolve().parents[1] / "migrations"
             / "20261117_project_profit_amz_platform_expense.sql").read_text("utf-8")
    assert extra.isascii() and "USE `date-project`;" in extra and "information_schema.columns" in extra
    for column in service.repo.MSKU_COLUMNS:
        assert f"`{column}`" in amz + extra, column


def test_amz_platform_expense_uses_the_file_total_and_partners_swap_foreign_fees():
    rows = [msku("EU-主体01-DE", "A", platform_fee=-100, sales_tax=50, market_tax=-40, platform_expense=-95),
            msku("EU-主体01-DE", "B", platform_fee=-10, sales_tax=3),  # 旧数据没有文件合计列：仍按分项加总
            msku("EU-主体05-DE", "ZMY-1", fees={"店铺运营费": -1}),
            msku("EU-主体05-DE", "22-QLA0-M28P", gross_profit=99, fees={"店铺运营费": -5, "税务风险金": -2}),
            msku("US3-主体27-US", "DSQ-1", fees={"店铺运营费": -10}),
            msku("US3-主体27-US", "SOSO053", fees={"店铺运营费": -20})]
    sums = service.store_sums(rows)
    assert sums[("EU", "主体01")]["platform_expense"] == -95 + (-10 + 3), "有「平台支出」列就用它"
    zmy, ybn = sums[("EU", "主体05")], sums[("US3", "主体27")]
    assert zmy["store_operation"] == -1 - 20 and ybn["store_operation"] == -10 - 7, "非本公司 MSKU 费用互记到对方"
    assert zmy["gross_profit"] == -20 and ybn["gross_profit"] == -7, "对方记来的费用也计入毛利"
    assert zmy["other_store_fee"] == 2, "其他店铺运营费仍记在本店主体"


def test_statement_no_longer_reads_the_api_pulled_table():
    import inspect

    source = inspect.getsource(service.repo)
    assert "ods_lingxing_profit_report_msku_month" not in source.replace(
        "领星接口拉取的 ods_lingxing_profit_report_msku_month 仍归 AMZ 月度利润表使用", "")
    assert service.repo.MSKU_TABLE == "fin_project_profit_amz_msku"
