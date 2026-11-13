"""飞书汽配订单同步 + 补货2.0 物流状态；飞书与数据库全部 mock。"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pymysql.err import ProgrammingError

from backend.integrations.feishu.client import FeishuRequestError
from backend.services import ebay_replenishment_purchase_logistics as logistics
from backend.services import feishu_auto_parts_order_sync_service as service

CHINA = timezone(timedelta(hours=8))
FIELDS = [*service.REQUIRED_FIELDS, *service.OPTIONAL_FIELDS]
WAREHOUSE_OPTIONS = ["CTUebay-UK中转仓", "CTUeBay-DE中转仓", "CTUebay-US中转仓", "CTUAMZ-EU中转仓",
                     "CTUeBay-UK中转仓", "CTUAMZ-US1中转仓", ""]


def ms(day):
    return str(int(datetime(day.year, day.month, day.day, tzinfo=CHINA).timestamp() * 1000))


def record(record_id, **fields):
    fields.setdefault("采购仓库", "CTUeBay-DE中转仓")  # 同步只收 eBay 仓的单
    return {"record_id": record_id, "fields": fields, "last_modified_time": ms(date(2026, 11, 10))}


class FakeClient:
    def __init__(self, records, field_names=FIELDS, error=None, warehouse_options=WAREHOUSE_OPTIONS):
        self.records, self.field_names, self.error = records, field_names, error
        self.warehouse_options = warehouse_options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def list_fields(self, app_token, table_id):
        if self.error:
            raise self.error
        return [{"field_name": name, **({"property": {"options": [{"name": o} for o in self.warehouse_options]}}
                                        if name == "采购仓库" else {})} for name in self.field_names]

    def fetch_records(self, app_token, table_id, view_id, **kwargs):
        assert view_id == "", "不依赖视图"
        assert kwargs.get("automatic_fields") is True
        self.filter = kwargs.get("filter")
        return self.records


@pytest.fixture
def stored(monkeypatch):
    calls = []
    monkeypatch.setattr(service.repo, "replace_all",
                        lambda rows: calls.append(rows) or {"inserted_rows": len(rows), "deleted_rows": 3})
    return calls


@pytest.mark.parametrize("warehouse,expected", [
    ("CTUeBay-DE中转仓", ("EBAY", "德国")),
    ("CTUebay-UK中转仓", ("EBAY", "英国")),
    ("CTUeBay-UK中转仓", ("EBAY", "英国")),
    ("CTUebay-US中转仓", ("EBAY", "美国")),
    ("CTUAMZ-EU中转仓", ("AMZ", None)),
    ("CTUAMZ-US1中转仓", ("AMZ", None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_warehouse_maps_to_platform_and_ebay_site(warehouse, expected):
    assert service.warehouse_site(warehouse) == expected


def test_rows_are_mapped_and_whole_table_replaced(stored):
    records = [
        record("rec1", **{"实际采购SKU": " bmw-30122-0128 ", "采购仓库": "CTUebay-UK中转仓", "订单状态": "待发货",
                          "下单日期": ms(date(2026, 11, 2)), "预计发货时间": ms(date(2026, 11, 20)), "PO": "PO1",
                          "数量": Decimal("10"), "订单金额": Decimal("8400.5"),
                          "采购员 (人员 )": [{"name": "王凯"}], "品名": [{"type": "text", "text": "减震器"}]}),
        record("rec2", **{"实际采购SKU": "PSA-60001-0056", "采购仓库": "CTUeBay-DE中转仓", "订单状态": "已付款"}),
    ]
    client = FakeClient(records)
    result = service.sync_feishu_auto_parts_orders(client_factory=lambda: client)
    assert client.filter == {"conjunction": "and", "conditions": [
        {"field_name": "订单状态", "operator": "isNot", "value": ["已完成"]},
        {"field_name": "订单状态", "operator": "isNot", "value": ["已取消"]},
        {"field_name": "采购仓库", "operator": "contains",
         "value": ["CTUebay-UK中转仓", "CTUeBay-DE中转仓", "CTUebay-US中转仓", "CTUeBay-UK中转仓"]},
    ]}, "飞书服务端只拉 eBay 仓、未完成的单；AMZ 仓选项不在里面"
    row = stored[0][0]
    assert row["sku"] == "BMW-30122-0128", "去空格并统一大写，和补货2.0精确匹配"
    assert (row["platform"], row["site"]) == ("EBAY", "英国")
    assert row["order_date"] == date(2026, 11, 2) and row["expected_ship_date"] == date(2026, 11, 20)
    assert row["quantity"] == Decimal("10") and row["order_amount"] == Decimal("8400.5")
    assert row["purchaser"] == "王凯" and row["product_name"] == "减震器"
    assert row["feishu_updated_at"] == datetime(2026, 11, 10)
    assert result["fetched_rows"] == 2 and result["ebay_rows"] == 2 and result["ebay_open_rows"] == 2
    assert result["extract_rows"] == 2 and result["ods_rows"] == 2 and result["sync_batch_id"]
    assert result["deleted_rows"] == 3


def test_missing_required_field_fails_before_writing(stored):
    names = [name for name in FIELDS if name != "预计发货时间"]
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="预计发货时间") as caught:
        service.sync_feishu_auto_parts_orders(client_factory=lambda: FakeClient([record("rec1")], names))
    assert caught.value.stage == "EXTRACT" and stored == []


def test_empty_table_never_wipes_local_copy(stored):
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="0行"):
        service.sync_feishu_auto_parts_orders(client_factory=lambda: FakeClient([]))
    assert stored == []


def test_duplicate_record_ids_abort(stored):
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="重复"):
        service.sync_feishu_auto_parts_orders(client_factory=lambda: FakeClient([record("rec1"), record("rec1")]))
    assert stored == []


def test_permission_error_mentions_role_and_keeps_old_data(stored):
    client = FakeClient([], error=FeishuRequestError("reason=HTTP 403"))
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="店铺巡查"):
        service.sync_feishu_auto_parts_orders(client_factory=lambda: client)
    assert stored == []


def test_optional_field_missing_only_warns(stored):
    names = [name for name in FIELDS if name != "品名"]
    result = service.sync_feishu_auto_parts_orders(client_factory=lambda: FakeClient([record("rec1")], names))
    assert any("品名" in warning for warning in result["warnings"])


def test_task_is_registered_with_its_own_lock():
    from backend.services import scheduler_service
    spec = scheduler_service.TASK_SPECS[service.TASK_CODE]
    assert spec.lock_name(None) == "feishu:auto-parts-order:replace"
    assert service.FeishuAutoPartsOrderSyncError in scheduler_service._STAGED_ERRORS


# ------------------------------------------------------------------ 物流状态


def order(status, expected=None, ordered=None, po="PO1", quantity=Decimal("5")):
    return {"site": "德国", "sku": "FRD-1", "po": po, "order_status": status, "quantity": quantity,
            "order_date": ordered, "expected_ship_date": expected, "purchaser": "韦霄健"}


def stock(**values):
    return {key: None for key, *_ in logistics.STOCK_STAGES} | {k: Decimal(str(v)) for k, v in values.items()}


def phase_rows(value, key):
    phase = next(p for p in value["phases"] if p["key"] == key)
    return [(i["label"], i["order_count"], i["quantity"]) for i in phase["items"]], phase


def test_build_two_phases_list_every_item_with_zero_and_totals():
    today = date(2026, 11, 13)
    value = logistics.build([
        order("待发货", date(2026, 11, 10), date(2026, 11, 1), "PO1"),
        order("已付款", date(2026, 11, 20), date(2026, 11, 5), "PO2", Decimal("30")),
        order("", None, date(2026, 11, 6), "PO3", Decimal("2.5")),
        order("待发货", date(2026, 11, 25), date(2026, 11, 8), "PO4"),
    ], today, stock(chengdu_pending_qc=5, chengdu_available=11, goodcang_onway=20, goodcang_available=7))
    assert [p["label"] for p in value["phases"]] == ["采购下单 → 成都仓", "成都仓 → 谷仓"]
    first, phase1 = phase_rows(value, "to_chengdu")
    assert first == [("已下单", 0, "0"), ("待付款", 0, "0"), ("已付款", 1, "30"), ("待发货", 2, "10"),
                     ("状态未填", 1, "2.5"), ("成都待检待上架", None, "5"), ("成都可用", None, "11")], \
        "固定列出全部状态，没有的为 0"
    assert (phase1["order_count"], phase1["quantity"]) == (4, "58.5")
    second, phase2 = phase_rows(value, "to_goodcang")
    assert second == [("准备发往谷仓（可用锁定）", None, "0"), ("调拨在途（待到谷仓）", None, "20"),
                      ("已到谷仓（谷仓可用）", None, "7")], "领星没有的数（可用锁定为 None）也显示 0"
    assert phase2["quantity"] == "27"
    assert value["chain_total_quantity"] == "85.5" and value["total_quantity"] == "42.5"
    assert value["status_summary"] == ("已付款1单30件 · 待发货2单10件 · 状态未填1单2.5件 · 待上架5件 · 成都可用11件"
                                       " · 在途谷仓20件 · 谷仓可用7件"), "单元格摘要只列有数的项"
    assert value["earliest_expected_ship_date"] == "2026-11-10" and value["overdue_count"] == 1
    assert value["orders"][0] == {"po": "PO1", "order_status": "待发货", "quantity": "5", "order_date": "2026-11-01",
                                  "expected_ship_date": "2026-11-10", "purchaser": "韦霄健", "overdue": True}
    assert value["orders"][2]["order_status"] == "状态未填" and value["orders"][2]["overdue"] is False


def test_unexpected_status_is_appended_after_the_fixed_ones():
    value = logistics.build([order("已退回", date(2026, 11, 30))], date(2026, 11, 13), None)
    labels = [label for label, *_ in phase_rows(value, "to_chengdu")[0]]
    assert labels[:5] == ["已下单", "待付款", "已付款", "待发货", "状态未填"] and labels[5] == "已退回"


def test_build_shows_stock_without_open_orders_and_none_when_nothing():
    today = date(2026, 11, 13)
    value = logistics.build([], today, stock(chengdu_pending_qc=3, chengdu_available=0))
    assert value["status_summary"] == "待上架3件" and value["order_count"] == 0
    assert phase_rows(value, "to_chengdu")[1]["order_count"] == 0
    only_goodcang = logistics.build([], today, stock(goodcang_onway=12))
    assert only_goodcang["status_summary"] == "在途谷仓12件" and only_goodcang["chain_total_quantity"] == "12"
    unknown_qc = logistics.build([], today, stock(chengdu_available=7))
    assert ("成都待检待上架", None, "0") in phase_rows(unknown_qc, "to_chengdu")[0], "待检量没同步时按 0 显示"
    assert logistics.build([], today, stock(chengdu_pending_qc=0, goodcang_available=0)) is None
    assert logistics.build([], today, None) is None


def test_attach_only_fills_sku_rows_and_matches_case_insensitively(monkeypatch):
    seen = {}

    def open_orders(cursor, keys):
        seen["keys"] = list(keys)
        return [order("待发货", date(2026, 11, 30))], datetime(2026, 11, 13, 8, 0, 5)

    monkeypatch.setattr(logistics.repo, "open_orders", open_orders)
    monkeypatch.setattr(logistics, "warehouse_stock", lambda cursor, pairs: (
        {("德国", "FRD-2"): stock(chengdu_pending_qc=4)}, datetime(2026, 11, 13, 0, 30)))
    items = [{"site": "德国", "sku": "frd-1", "node_kind": "sku"},
             {"site": "德国", "sku": "FRD-2"},
             {"site": "德国", "sku": "FRD-3"},
             {"site": "德国", "sku": "", "node_kind": "site"}]
    meta = logistics.attach(object(), items)
    assert seen["keys"] == [("德国", "FRD-1"), ("德国", "FRD-2"), ("德国", "FRD-3")], "汇总行不查"
    assert items[0]["purchase_logistics"]["order_count"] == 1
    assert items[1]["purchase_logistics"]["status_summary"] == "待上架4件", "只有库存也显示"
    assert items[2]["purchase_logistics"] is None, "没有采购单也没有库存"
    assert "purchase_logistics" not in items[3]
    assert meta == {"purchase_logistics_available": True, "purchase_logistics_synced_at": "2026-11-13 08:00:05",
                    "inventory_stock_synced_at": "2026-11-13 00:30:00"}


def test_attach_tolerates_missing_table(monkeypatch):
    def missing(cursor, keys):
        raise ProgrammingError(1146, "Table 'date-project.ods_feishu_auto_parts_order' doesn't exist")

    monkeypatch.setattr(logistics.repo, "open_orders", missing)
    monkeypatch.setattr(logistics, "warehouse_stock", lambda cursor, pairs: ({}, None))
    items = [{"site": "德国", "sku": "FRD-1"}]
    assert logistics.attach(object(), items)["purchase_logistics_available"] is False
    assert items[0]["purchase_logistics"] is None


def test_warehouse_stock_splits_chengdu_and_goodcang_columns():
    cursor = RecordingCursor([{"synced_at": datetime(2026, 11, 13, 0, 30)},
                              [{"site": "美国", "sku": "frd-1", "chengdu_pending_qc": None,
                                "chengdu_available": Decimal("11.0000"), "goodcang_locked": Decimal("0"),
                                "goodcang_onway": Decimal("30"), "goodcang_available": Decimal("9")}]])
    result, synced_at = logistics.warehouse_stock(cursor, [("美国", "FRD-1")])
    sql, params = cursor.sql[1]
    assert "wid IN ('18674','18675','18676','18699','18700','18701','18702')" in sql
    assert "WHEN '18700' THEN '美国'" in sql and "WHEN '18701' THEN '美国'" in sql, "美国新泽西 + 加州合并"
    assert "CASE WHEN wid IN ('18674','18675','18676') THEN CAST(NULLIF(TRIM(product_qc_num),'')" in sql
    assert "CASE WHEN wid IN ('18699','18700','18701','18702') THEN CAST(NULLIF(TRIM(product_lock_num),'')" in sql
    assert "CASE WHEN wid IN ('18699','18700','18701','18702') THEN CAST(NULLIF(TRIM(product_onway),'')" in sql
    assert "CASE WHEN wid IN ('18699','18700','18701','18702') THEN CAST(NULLIF(TRIM(product_valid_num),'')" in sql
    assert "CASE WHEN COUNT(chengdu_pending_qc)=0 THEN NULL" in sql, "待检量整列为空时不当 0"
    assert params == ["FRD-1", "美国", "FRD-1"]
    assert result == {("美国", "FRD-1"): {"chengdu_pending_qc": None, "chengdu_available": Decimal("11"),
                                         "goodcang_locked": Decimal("0"), "goodcang_onway": Decimal("30"),
                                         "goodcang_available": Decimal("9")}}
    assert synced_at == datetime(2026, 11, 13, 0, 30)


class RecordingCursor:
    def __init__(self, results):
        self.results, self.sql = list(results), []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

    def fetchone(self):
        return self.results.pop(0)

    def fetchall(self):
        return self.results.pop(0)


def test_open_orders_query_excludes_closed_statuses_and_upper_cases_sku():
    from backend.repositories import feishu_auto_parts_order_repository as repo
    cursor = RecordingCursor([{"synced_at": None}, []])
    rows, synced_at = repo.open_orders(cursor, [("德国", " frd-1 "), ("", "X"), ("英国", None)])
    sql, params = cursor.sql[1]
    assert "(site,sku) IN ((%s,%s))" in sql and "NOT IN (%s,%s)" in sql
    assert params == ["德国", "FRD-1", "已完成", "已取消"]
    assert rows == [] and synced_at is None


def test_record_id_is_case_sensitive_in_the_table():
    """飞书 record_id 区分大小写；主键用 _ci 排序规则会把只差大小写的两条记录当成重复（首拉实测 1062）。"""
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1] / "migrations" / "20261113_feishu_auto_parts_order.sql").read_text("ascii")
    assert "`record_id` VARCHAR(32) COLLATE utf8mb4_bin NOT NULL" in sql


def test_only_permission_errors_suggest_granting_the_role(stored):
    temporary = FakeClient([], error=FeishuRequestError("reason=飞书业务码 1255002：Something went wrong"))
    with pytest.raises(service.FeishuAutoPartsOrderSyncError) as caught:
        service.sync_feishu_auto_parts_orders(client_factory=lambda: temporary)
    assert "店铺巡查" not in str(caught.value)


def test_bitable_internal_error_is_retried():
    from backend.integrations.feishu.client import RETRYABLE_CODES
    assert 1255002 in RETRYABLE_CODES


def test_closed_orders_leaking_through_the_filter_abort(stored):
    leaked = [record("rec1", **{"实际采购SKU": "A-1", "采购仓库": "CTUeBay-DE中转仓", "订单状态": "已完成"})]
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="过滤条件可能失效"):
        service.sync_feishu_auto_parts_orders(client_factory=lambda: FakeClient(leaked))
    assert stored == []


def test_amz_orders_leaking_through_the_filter_abort(stored):
    leaked = [record("rec1", **{"实际采购SKU": "A-1", "采购仓库": "CTUAMZ-EU中转仓", "订单状态": "已付款"})]
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="非 eBay 仓"):
        service.sync_feishu_auto_parts_orders(client_factory=lambda: FakeClient(leaked))
    assert stored == []


def test_missing_ebay_warehouse_options_fail_before_pulling(stored):
    client = FakeClient([record("rec1")], warehouse_options=["CTUAMZ-EU中转仓"])
    with pytest.raises(service.FeishuAutoPartsOrderSyncError, match="没有名字带 eBay 的选项"):
        service.sync_feishu_auto_parts_orders(client_factory=lambda: client)
    assert stored == []
