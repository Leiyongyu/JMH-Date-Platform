"""历史透视独立测试：只使用内存输入与假连接，不访问数据库或领星。"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.repositories import ebay_inventory_pivot_repository as repository
from backend.services import ebay_inventory_detail_service as detail_service
from backend.services import ebay_inventory_pivot_service as service


D = Decimal


def item(sku="SKU-A", owner="李茫茫", site="德国", **values):
    return {
        "sku": sku, "owner": owner, "site": site,
        "overseas_sellable_quantity": D("10"),
        "overseas_total_quantity": D("20"),
        "sales_qty_30d": D("5"),
        "overseas_sellable_value": D("12.004"),
        "overseas_total_value": D("24.008"),
        "warehouse_rent_30d_cny": D("0.004"),
        **values,
    }


def test_aggregate_ratio_is_ratio_of_sums_not_sum_or_average_of_sku_ratios():
    rows = [
        item("SKU-A", overseas_sellable_quantity=D("10"), overseas_total_quantity=D("20"), sales_qty_30d=D("1")),
        item("SKU-B", overseas_sellable_quantity=D("90"), overseas_total_quantity=D("180"), sales_qty_30d=D("9")),
    ]
    group = service.aggregate_inventory(rows)[0]
    assert group["sku_count"] == 2
    assert group["sales_qty_30d"] == 10
    assert group["in_stock_sales_ratio"] == D("10.000000")
    assert group["total_stock_sales_ratio"] == D("20.000000")

    # Unequal per-SKU ratios and sales weights prove this is not their arithmetic mean.
    rows[1]["overseas_sellable_quantity"] = D("9")
    group = service.aggregate_inventory(rows)[0]
    assert group["in_stock_sales_ratio"] == D("1.900000")
    assert group["in_stock_sales_ratio"] != (D("10") + D("1")) / 2


def test_aggregate_owner_and_site_are_independent_and_unassigned_is_retained():
    rows = [
        item("A", owner=None), item("B", owner=" "),
        item("A", owner="李茫茫", site="英国"), item("C", owner="另一人"),
    ]
    groups = {(row["owner"], row["site"]): row for row in service.aggregate_inventory(rows)}
    assert set(groups) == {("未分配", "德国"), ("李茫茫", "英国"), ("另一人", "德国")}
    assert groups[("未分配", "德国")]["sku_count"] == 2
    assert sum(row["sku_count"] for row in groups.values()) == 4


@pytest.mark.parametrize("bad", [
    item("SKU-A"), item(" SKU-A ", owner="另一个负责人"),
    item("", owner="正常"), item("SKU-B", site=""),
])
def test_duplicate_or_blank_site_sku_is_rejected_before_counting(bad):
    with pytest.raises(ValueError, match="重复或空"):
        service.aggregate_inventory([item("SKU-A"), bad])


def test_money_rounds_only_after_whole_group_sum_not_per_sku():
    rows = [
        item("A", **{field: D("0.004") for field in service.AMOUNTS}),
        item("B", **{field: D("0.004") for field in service.AMOUNTS}),
    ]
    original = deepcopy(rows)
    result = service.aggregate_inventory(rows)[0]
    for field in service.AMOUNTS:
        assert result[field] == D("0.01")
    assert rows == original  # capture must not mutate shared live calculation rows.


@pytest.mark.parametrize("missing_first", [True, False])
def test_partial_price_or_rent_sums_present_and_counts_each_missing_sku_once(missing_first):
    present = item("good")
    missing = item("missing", overseas_sellable_value=None, overseas_total_value=None, warehouse_rent_30d_cny=None)
    rows = [missing, present] if missing_first else [present, missing]
    group = service.aggregate_inventory(rows)[0]
    assert group["overseas_sellable_value"] == D("12.00")
    assert group["overseas_total_value"] == D("24.01")
    assert group["warehouse_rent_30d_cny"] == D("0.00")
    assert group["missing_price_count"] == 1
    assert group["missing_rent_count"] == 1
    assert group["sku_count"] == 2
    assert group["overseas_total_quantity"] == 40


def test_missing_rent_does_not_erase_valid_goods_values():
    group = service.aggregate_inventory([item("A", warehouse_rent_30d_cny=None), item("B")])[0]
    assert group["warehouse_rent_30d_cny"] == D("0.00")
    assert group["overseas_sellable_value"] == D("24.01")
    assert group["overseas_total_value"] == D("48.02")
    assert group["missing_price_count"] == 0
    assert group["missing_rent_count"] == 1


def test_all_missing_amounts_stay_none_without_dropping_stock_or_sales():
    rows = [item(sku, **{field: None for field in service.AMOUNTS}) for sku in ("A", "B")]
    group = service.aggregate_inventory(rows)[0]
    assert all(group[field] is None for field in service.AMOUNTS)
    assert group["missing_price_count"] == group["missing_rent_count"] == 2
    assert group["sku_count"] == 2
    assert group["sales_qty_30d"] == 10
    assert group["overseas_total_quantity"] == 40


@pytest.mark.parametrize("field", service.AMOUNTS)
def test_valid_zero_with_missing_amounts_is_zero_not_none(field):
    group = service.aggregate_inventory([item("A", **{field: None}), item("B", **{field: D("0")})])[0]
    assert group[field] == D("0.00")


def test_amounts_skip_missing_independently_and_round_after_sum():
    group = service.aggregate_inventory([
        item("A", overseas_sellable_value=D("0.004"), overseas_total_value=None, warehouse_rent_30d_cny=D("1.234")),
        item("B", overseas_sellable_value=None, overseas_total_value=D("2.345"), warehouse_rent_30d_cny=None),
        item("C", overseas_sellable_value=D("0.004"), overseas_total_value=None, warehouse_rent_30d_cny=D("0.004")),
    ])[0]
    assert group["overseas_sellable_value"] == D("0.01")
    assert group["overseas_total_value"] == D("2.35")
    assert group["warehouse_rent_30d_cny"] == D("1.24")


def test_real_zero_is_preserved_and_zero_sales_ratios_are_zero():
    row = item(**{field: D("0") for field in service.QUANTITIES + service.AMOUNTS})
    group = service.aggregate_inventory([row])[0]
    assert all(group[field] == 0 for field in service.QUANTITIES + service.AMOUNTS)
    assert group["in_stock_sales_ratio"] == 0
    assert group["total_stock_sales_ratio"] == 0
    assert group["missing_price_count"] == group["missing_rent_count"] == 0


@pytest.mark.parametrize("field", service.QUANTITIES)
def test_missing_quantity_never_silently_becomes_zero(field):
    with pytest.raises(ValueError, match="数量缺失"):
        service.aggregate_inventory([item(**{field: None})])


@pytest.mark.parametrize("field", service.AMOUNTS)
def test_nonfinite_money_is_not_published(field):
    with pytest.raises(ValueError, match="非有限"):
        service.aggregate_inventory([item(**{field: D("NaN")})])


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 16, 8, 9, 10, tzinfo=tz)


@pytest.fixture
def capture(monkeypatch):
    state = {"acquired": True, "held": False, "events": []}

    @contextmanager
    def lock(name):
        state["events"].append(("lock", name))
        state["held"] = state["acquired"]
        try:
            yield state["acquired"]
        finally:
            state["held"] = False
            state["events"].append(("unlock", name))

    metadata = {
        "inventory_batch_id": "batch-new", "inventory_snapshot_date": date(2026, 9, 14),
        "inventory_pulled_at": datetime(2026, 9, 14, 16, 38, 43),
        "owner_rule_month": "2026-09",
    }

    def load():
        assert state["held"]
        state["events"].append(("load",))
        return state["rows"], metadata, ["one warning"]

    def save(header, groups):
        assert state["held"]
        state["events"].append(("save",))
        return 42

    state.update(rows=[item()], metadata=metadata)
    loader = MagicMock(side_effect=load)
    saver = MagicMock(side_effect=save)
    monkeypatch.setattr(service, "datetime", FrozenDatetime)
    monkeypatch.setattr(service, "named_lock", lock)
    monkeypatch.setattr(service, "load_calculated_inventory", loader)
    monkeypatch.setattr(service.repository, "replace_day", saver)
    state.update(loader=loader, saver=saver)
    return state


def test_capture_uses_generation_today_not_source_snapshot_day_and_lock_spans_save(capture):
    result = service.capture_snapshot(expected_inventory_batch="batch-new", trigger_type="WEEKLY")
    header, groups = capture["saver"].call_args.args
    assert result["stat_date"] == "2026-09-16"
    assert header["stat_date"] == date(2026, 9, 16)
    assert header["stat_month"] == "2026-09"
    assert header["generated_at"] == datetime(2026, 9, 16, 8, 9, 10)
    assert header["generated_at"].tzinfo is None
    assert header["inventory_snapshot_date"] == date(2026, 9, 14)
    assert header["inventory_pulled_at"] == datetime(2026, 9, 14, 16, 38, 43)
    assert header["trigger_type"] == "WEEKLY"
    assert header["metadata"]["warnings"] == ["one warning"]
    assert result["snapshot_id"] == 42
    assert result["group_count"] == len(groups) == 1
    assert capture["events"] == [
        ("lock", "inventory:ebay-pivot"), ("load",), ("save",), ("unlock", "inventory:ebay-pivot"),
    ]


def test_capture_refuses_when_named_lock_busy_without_read_or_write(capture):
    capture["acquired"] = False
    with pytest.raises(ValueError, match="正在生成"):
        service.capture_snapshot()
    capture["loader"].assert_not_called()
    capture["saver"].assert_not_called()


@pytest.mark.parametrize("mode", ["no_items", "no_batch", "changed_batch", "bad_items"])
def test_capture_failure_never_writes_empty_or_wrong_batch(capture, mode):
    expected = None
    if mode == "no_items":
        capture["rows"] = []
    elif mode == "no_batch":
        capture["metadata"]["inventory_batch_id"] = None
    elif mode == "changed_batch":
        expected = "older-batch"
    else:
        capture["rows"] = [item(), item()]
    with pytest.raises(ValueError):
        service.capture_snapshot(expected_inventory_batch=expected)
    capture["saver"].assert_not_called()
    assert capture["held"] is False


@pytest.mark.parametrize("value", ["20260916", "2026-9-16", "2026-09-31", " 2026-09-16", "2026-09-16T00:00:00", "2026-W38-3"])
def test_date_filter_rejects_noncanonical_or_invalid_dates(monkeypatch, value):
    read = MagicMock()
    monkeypatch.setattr(repository, "read_history", read)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.list_pivot(start_date=value)
    read.assert_not_called()


def test_date_range_reversed_is_rejected_before_read(monkeypatch):
    read = MagicMock()
    monkeypatch.setattr(repository, "read_history", read)
    with pytest.raises(ValueError, match="开始日期"):
        service.list_pivot(start_date="2026-09-16", end_date="2026-09-14")
    read.assert_not_called()


def test_service_normalizes_filters_page_size_and_preserves_decimal_iso_values(monkeypatch):
    read = MagicMock(return_value={
        "items": [{"stat_date": date(2026, 9, 16), "generated_at": datetime(2026, 9, 16, 8),
                   "value": D("0.100001"), "missing": None, "sku_count": 7}],
        "pagination": {"total": 1},
    })
    monkeypatch.setattr(repository, "read_history", read)
    result = service.list_pivot(start_date="2026-09-14", end_date="2026-09-16",
                                owner=" 李茫茫 ", site=" 德国 ", page=0, page_size=999,
                                sort_order="ASCENDING")
    assert read.call_args.kwargs == {
        "start_date": date(2026, 9, 14), "end_date": date(2026, 9, 16),
        "owner": "李茫茫", "site": "德国", "page": 1, "page_size": 200,
        "sort_field": "stat_date", "sort_order": "ascending", "paginate": True,
    }
    assert result["items"] == [{"stat_date": "2026-09-16", "generated_at": "2026-09-16T08:00:00",
                               "value": "0.100001", "missing": None, "sku_count": 7}]


def test_blank_service_filters_and_export_pagination_flag(monkeypatch):
    read = MagicMock(return_value={"items": []})
    monkeypatch.setattr(repository, "read_history", read)
    service.list_pivot(owner="  ", site="", start_date="", paginate=False)
    assert read.call_args.kwargs["owner"] is None
    assert read.call_args.kwargs["site"] is None
    assert read.call_args.kwargs["start_date"] is None
    assert read.call_args.kwargs["paginate"] is False


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.current = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        query = " ".join(query.split())
        self.current = query
        self.connection.events.append(("execute", query, params))
        if self.connection.fail_on and self.connection.fail_on in query:
            raise RuntimeError("simulated statement failure")
        if query.startswith("DELETE FROM"):
            snapshot_id, = params
            self.connection.pending.pop(snapshot_id, None)

    def executemany(self, query, params):
        query = " ".join(query.split())
        params = list(params)
        self.connection.events.append(("executemany", query, params))
        if self.connection.fail_on == "executemany":
            raise RuntimeError("simulated detail insert failure")
        for row in params:
            self.connection.pending.setdefault(row[0], []).append(row)

    def fetchone(self):
        if self.current.startswith("SELECT id FROM"):
            return {"id": 42}
        if self.current.startswith("SELECT COUNT"):
            return {"total": self.connection.total, "detail_count": self.connection.detail_count,
                    "snapshot_count": 2}
        raise AssertionError("unexpected fetchone: " + self.current)

    def fetchall(self):
        if self.current.startswith("SELECT DISTINCT owner"):
            return [{"owner": "李茫茫"}, {"owner": "未分配"}]
        if self.current.startswith("SELECT DISTINCT site"):
            return [{"site": "德国"}]
        if self.current.startswith("SELECT stat_date FROM"):
            return [{"stat_date": date(2026, 9, 16)}, {"stat_date": date(2026, 9, 14)}]
        if self.current.startswith("SELECT g.*"):
            return [{"snapshot_id": 42, "stat_date": date(2026, 9, 16), "owner": "李茫茫",
                     "site": "负责人汇总", "row_type": "OWNER_TOTAL", "site_count": 1,
                     "sort_site": "德国"}]
        if self.current.startswith("SELECT s.id AS snapshot_id"):
            return [{"snapshot_id": 42, "stat_date": date(2026, 9, 16), "owner": "李茫茫",
                     "site": "德国", "row_type": "DETAIL"}]
        raise AssertionError("unexpected fetchall: " + self.current)


class FakeConnection:
    def __init__(self, *, fail_on=None, total=101, detail_count=202):
        self.fail_on, self.total = fail_on, total
        self.detail_count = detail_count
        self.events = []
        self.saved = {41: ["older-day-kept"], 42: ["today-before-replace"]}
        self.pending = None
        self._cursor = FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor

    def begin(self):
        self.events.append(("begin",))
        self.pending = deepcopy(self.saved)

    def commit(self):
        self.events.append(("commit",))
        self.saved = deepcopy(self.pending)
        self.pending = None

    def rollback(self):
        self.events.append(("rollback",))
        self.pending = None


def install_connection(monkeypatch, **kwargs):
    connection = FakeConnection(**kwargs)
    monkeypatch.setattr(repository, "db_connection", lambda: connection)
    return connection


def header():
    return {
        "stat_date": date(2026, 9, 16), "stat_month": "2026-09",
        "generated_at": datetime(2026, 9, 16, 8), "inventory_batch_id": "batch",
        "inventory_snapshot_date": date(2026, 9, 14),
        "inventory_pulled_at": datetime(2026, 9, 14, 16), "trigger_type": "TEST",
        "item_count": 2, "metadata": {"precise": D("1.001"), "date": date(2026, 9, 14), "说明": "冻结"},
    }


def test_replace_transaction_deletes_only_selected_day_snapshot_and_keeps_other_history(monkeypatch):
    connection = install_connection(monkeypatch)
    groups = service.aggregate_inventory([item("A"), item("B")])
    result = repository.replace_day(header(), groups)
    assert result == 42
    assert connection.events[0] == ("begin",)
    assert connection.events[-1] == ("commit",)
    assert ("rollback",) not in connection.events
    deletes = [event for event in connection.events if event[0] == "execute" and event[1].startswith("DELETE")]
    assert deletes == [("execute", "DELETE FROM ebay_inventory_pivot_owner WHERE snapshot_id=%s", (42,))]
    assert connection.saved[41] == ["older-day-kept"]
    assert len(connection.saved[42]) == 1
    assert connection.saved[42][0][:4] == (42, "李茫茫", "德国", 2)
    statements = [event[1] for event in connection.events if event[0] in {"execute", "executemany"}]
    assert not any("TRUNCATE" in sql.upper() for sql in statements)
    assert any("ON DUPLICATE KEY UPDATE" in sql for sql in statements)
    assert any("WHERE stat_date=%s FOR UPDATE" in sql for sql in statements)
    first_insert = next(event for event in connection.events if event[0] == "execute" and event[1].startswith("INSERT"))
    assert '"precise": "1.001"' in first_insert[2][-1]
    assert "冻结" in first_insert[2][-1]


@pytest.mark.parametrize("fail_on", ["INSERT INTO ebay_inventory_pivot_snapshot", "SELECT id FROM", "DELETE FROM", "executemany"])
def test_replace_failure_rolls_back_old_today_and_older_dates(monkeypatch, fail_on):
    connection = install_connection(monkeypatch, fail_on=fail_on)
    before = deepcopy(connection.saved)
    with pytest.raises(RuntimeError, match="simulated"):
        repository.replace_day(header(), service.aggregate_inventory([item()]))
    assert connection.saved == before
    assert connection.events[-1] == ("rollback",)
    assert ("commit",) not in connection.events


def test_replace_batches_detail_inserts_in_groups_of_500(monkeypatch):
    connection = install_connection(monkeypatch)
    groups = service.aggregate_inventory([item(str(index), owner="owner-" + str(index)) for index in range(1001)])
    repository.replace_day(header(), groups)
    batches = [event for event in connection.events if event[0] == "executemany"]
    assert [len(event[2]) for event in batches] == [500, 500, 1]


def test_read_uses_frozen_tables_exact_filters_parameterized_values_and_stable_paging(monkeypatch):
    connection = install_connection(monkeypatch)
    owner = "x' OR 1=1 --"
    result = repository.read_history(
        start_date=date(2026, 9, 14), end_date=date(2026, 9, 16), owner=owner, site="德国",
        page=3, page_size=20, sort_field="sku_count", sort_order="ascending",
    )
    queries = [event for event in connection.events if event[0] == "execute"]
    assert queries[0][1] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
    assert connection.events[-1] == ("commit",)
    selected = next(event for event in queries if event[1].startswith("SELECT g.*"))
    assert "ORDER BY g.sku_count IS NULL, g.sku_count ASC,g.stat_date DESC,g.owner" in selected[1]
    assert "LIMIT %s OFFSET %s" in selected[1]
    assert owner not in selected[1]
    assert selected[2] == (date(2026, 9, 14), date(2026, 9, 16), owner, "德国", 20, 40)
    assert "inventory_detail_weekly" not in selected[1]
    assert "owner_rule" not in selected[1]
    assert result["pagination"] == {"page": 3, "page_size": 20, "total": 101}
    assert result["options"] == {"owners": ["李茫茫", "未分配"], "sites": ["德国"], "dates": ["2026-09-16", "2026-09-14"]}
    assert result["metadata"] == {"snapshot_count": 2, "detail_count": 202,
                                  "owner_total_count": 101, "pagination_unit": "owner_date"}
    detail_query = next(event for event in queries if event[1].startswith("SELECT s.id AS snapshot_id"))
    assert "(d.snapshot_id,d.owner) IN ((%s,%s))" in detail_query[1]
    assert "LIMIT" not in detail_query[1]
    assert detail_query[2] == (date(2026, 9, 14), date(2026, 9, 16), owner, "德国", 42, "李茫茫")
    assert result["items"][0]["row_type"] == "DETAIL"
    assert result["owner_totals"][0]["row_type"] == "OWNER_TOTAL"
    assert "sort_site" not in result["owner_totals"][0]


@pytest.mark.parametrize("sort_field", ["s.stat_date", "stat_date; DROP TABLE x", "owner DESC", "unknown"])
def test_invalid_sort_field_rejected_before_db_access(monkeypatch, sort_field):
    connect = MagicMock()
    monkeypatch.setattr(repository, "db_connection", connect)
    with pytest.raises(ValueError, match="排序字段"):
        repository.read_history(sort_field=sort_field)
    connect.assert_not_called()


def test_sort_direction_injection_cannot_enter_sql(monkeypatch):
    connection = install_connection(monkeypatch)
    attack = "asc; DROP TABLE x"
    repository.read_history(sort_order=attack)
    sql = next(event[1] for event in connection.events
               if event[0] == "execute" and event[1].startswith("SELECT g.*"))
    assert attack not in sql
    assert "g.stat_date DESC" in sql


def test_export_has_no_pagination_and_enforces_safe_maximum(monkeypatch):
    connection = install_connection(monkeypatch, total=20000, detail_count=30000)
    repository.read_history(paginate=False)
    sql = next(event[1] for event in connection.events
               if event[0] == "execute" and event[1].startswith("SELECT g.*"))
    assert "LIMIT" not in sql and "OFFSET" not in sql
    detail_sql = next(event[1] for event in connection.events
                      if event[0] == "execute" and event[1].startswith("SELECT s.id AS snapshot_id"))
    assert " IN " not in detail_sql
    connection = install_connection(monkeypatch, total=20000, detail_count=30001)
    with pytest.raises(ValueError, match="50000"):
        repository.read_history(paginate=False)
    assert connection.events[-1] == ("rollback",)
    assert not any(event[0] == "execute" and event[1].startswith("SELECT g.*") for event in connection.events)


def test_read_error_rolls_back_and_never_writes(monkeypatch):
    connection = install_connection(monkeypatch, fail_on="SELECT g.*")
    with pytest.raises(RuntimeError):
        repository.read_history()
    assert connection.events[-1] == ("rollback",)
    assert not any(event[0] == "execute" and event[1].startswith(("DELETE", "INSERT", "UPDATE")) for event in connection.events)


def test_shared_loader_returns_unfiltered_unrounded_decimal_rows_and_month_metadata(monkeypatch):
    source = [{"site": "德国", "sku": "A"}, {"site": "英国", "sku": "A"}]
    source_metadata = {"inventory_batch_id": "batch", "rent_pull_month": "2026-08"}
    original_metadata = deepcopy(source_metadata)
    raw_items = [item("A", overseas_sellable_value=D("0.004")), item("A", site="英国")]
    raw_rules = [{"rule_type": "BRAND"}]
    rules = object()
    sku_map = {"A": "B"}
    owner_rules = MagicMock(return_value=raw_rules)
    rule_map = MagicMock(return_value=rules)
    product_map = MagicMock(return_value=sku_map)
    build = MagicMock(return_value=(raw_items, []))
    monkeypatch.setattr(detail_service, "datetime", FrozenDatetime)
    monkeypatch.setattr(detail_service.repository, "read_snapshot", lambda: (source, source_metadata, [], {}))
    monkeypatch.setattr(detail_service.owner_repository, "owner_rules", owner_rules)
    monkeypatch.setattr(detail_service, "_ebay_rule_map", rule_map)
    monkeypatch.setattr(detail_service, "_ebay_product_sku_map", product_map)
    monkeypatch.setattr(detail_service, "_build_items", build)
    items, metadata, warnings = detail_service.load_calculated_inventory()
    assert items is raw_items
    assert items[0]["overseas_sellable_value"] == D("0.004")
    assert len(items) == 2
    owner_rules.assert_called_once_with("2026-09", "ebay")
    rule_map.assert_called_once_with(raw_rules)
    product_map.assert_called_once_with("2026-09", include_next=False)
    build.assert_called_once_with(source, [], {}, source_metadata, rules, sku_map)
    assert metadata["owner_rule_month"] == "2026-09"
    assert metadata["rent_pull_month"] == "2026-08"
    assert source_metadata == original_metadata
    assert warnings == []


def test_shared_loader_empty_snapshot_skips_owner_queries_and_emits_warning(monkeypatch):
    owner_rules = MagicMock()
    sku_map = MagicMock()
    monkeypatch.setattr(detail_service.repository, "read_snapshot",
                        lambda: ([], {"inventory_batch_id": None}, [], {}))
    monkeypatch.setattr(detail_service.owner_repository, "owner_rules", owner_rules)
    monkeypatch.setattr(detail_service, "_ebay_product_sku_map", sku_map)
    items, metadata, warnings = detail_service.load_calculated_inventory()
    assert items == []
    owner_rules.assert_not_called()
    sku_map.assert_not_called()
    assert any("没有可用的成功周报库存快照" in warning for warning in warnings)
