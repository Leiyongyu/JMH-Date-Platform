from contextlib import contextmanager, nullcontext
from copy import deepcopy
from decimal import Decimal

import pytest

from backend.repositories import inventory_report_etl_repository as repo_module
from backend.services import currency_sync_service
from backend.services import inventory_report_etl_service as service
from backend.services import inventory_report_source_sync_service as source_sync
from backend.services import performance_service
from backend.services import scheduler_service


DEPARTMENTS = [code for code, _name, _order in service.DEPARTMENTS]


def _department_row(code, index):
    qty = Decimal(1000 + index * 100)
    return {
        "stat_month": "2026-09",
        "department_code": code,
        "department_name": code,
        "display_order": index,
        "is_total": 0,
        "source_rows": 10,
        "local_end_in_transit_qty": Decimal("5"),
        "local_end_in_transit_total_cost": Decimal("50"),
        "local_end_inventory_qty": Decimal("7"),
        "local_end_inventory_total_cost": Decimal("70"),
        "overseas_end_in_transit_qty": Decimal("20"),
        "overseas_end_in_transit_total_cost": Decimal("2000"),
        "overseas_end_inventory_qty": qty,
        "overseas_end_inventory_total_cost": qty * 30,
        "fba_end_in_transit_qty": Decimal("10"),
        "fba_end_in_transit_total_cost": Decimal("1000"),
        "fba_end_inventory_qty": Decimal("300"),
        "fba_end_inventory_total_cost": Decimal("9000"),
        "next_month_opening_inventory_qty": qty + 300,
    }


def _department_rows():
    rows = [_department_row(code, index) for index, code in enumerate(DEPARTMENTS, 1)]
    total = {"department_code": "AUTO-PARTS-TOTAL", "department_name": "合计",
             "display_order": 99, "is_total": 1, "stat_month": "2026-09"}
    for field in rows[0]:
        if field.endswith("_qty") or field.endswith("_cost") or field == "source_rows":
            total[field] = sum((row[field] for row in rows), Decimal("0"))
    return [*rows, total]


def _dimension_row(dimension, platform, department, value, qty):
    return {
        "stat_month": "2026-09",
        "dimension_type": dimension,
        "platform_code": platform,
        "department_code": department,
        "dimension_value": value,
        "owner_rule_month": "2026-10",
        "source_rows": 3,
        "local_end_in_transit_qty": None,
        "local_end_in_transit_total_cost": None,
        "local_end_inventory_qty": None,
        "local_end_inventory_total_cost": None,
        "overseas_end_in_transit_qty": Decimal("2"),
        "overseas_end_in_transit_total_cost": Decimal("200"),
        "overseas_end_inventory_qty": Decimal(qty),
        "overseas_end_inventory_total_cost": Decimal(qty) * 20,
        "fba_end_in_transit_qty": Decimal("1"),
        "fba_end_in_transit_total_cost": Decimal("100"),
        "fba_end_inventory_qty": Decimal("50"),
        "fba_end_inventory_total_cost": Decimal("1500"),
    }


class World:
    """Inventory frozen on 10-13; October sales and rate arrive later."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.department_rows = _department_rows()
        self.store_rows = [
            _dimension_row("STORE", "AMZ", "AMZ-US1", "示例店铺", 400),
            _dimension_row("STORE", "AMZ", "AMZ-US2-MJ", "MJ店铺", 300),
        ]
        self.owner_rows = [
            _dimension_row("OWNER", "AMZ", "AMZ-US1", "负责人甲", 400),
            _dimension_row("OWNER", "EBAY", "EBAY-1", "负责人乙", 600),
            _dimension_row("OWNER", "EBAY", "EBAY-1", "未分配", 80),
        ]
        self.sales_ready = False
        self.ebay_ready = True
        self.rate = Decimal("7.10")
        self.snapshots = {}
        self.saved = []
        self.events = []
        self._patch()

    def _patch(self):
        mp, repo = self.monkeypatch, service.repo
        mp.setattr(repo, "department_summary", lambda month=None: {
            "stat_month": "2026-09", "items": deepcopy(self.department_rows),
        })
        mp.setattr(repo, "dimension_summary", lambda dimension, month=None: {
            "stat_month": "2026-09",
            "items": deepcopy(self.store_rows if dimension == "STORE" else self.owner_rows),
        })
        mp.setattr(repo, "usd_rate", lambda month: self.rate if self.sales_ready else None)
        mp.setattr(repo, "inventory_age_group_costs", lambda month: {})
        mp.setattr(service.clearance_repo, "ctu_over_30_costs", lambda month: {"US3": Decimal("88")})
        mp.setattr(service, "_inventory_health_maps", lambda *_a, **_k: ({}, {}, {}, set()))
        mp.setattr(service, "_inventory_owner_context", lambda *_a, **_k: ({}, {}, {}))
        mp.setattr(service, "_inventory_age_cost_by_owner", lambda *_a, **_k: ({}, {}))
        mp.setattr(service, "_ctu_cost_by_owner", lambda *_a, **_k: ({}, set()))
        mp.setattr(repo, "owner_rules", lambda *_a: [])
        mp.setattr(service, "_ebay_product_sku_map", lambda *_a, **_k: {})
        mp.setattr(service, "_ebay_assignment", lambda sku, *_a: (
            {"BMW-1": "负责人乙"}.get(sku, service.UNASSIGNED), "TEST",
        ))
        amz_ready = lambda: self.sales_ready
        ebay_ready = lambda: self.sales_ready and self.ebay_ready
        mp.setattr(repo, "amz_sales_volume_by_department", lambda month: {
            "AMZ-EU": Decimal("1000"), "AMZ-US1": Decimal("8000"),
            "AMZ-US2": Decimal("5000"), "AMZ-US2-MJ": Decimal("3000"),
            "AMZ-US1-ZXY": Decimal("1314"),
        } if amz_ready() else None)
        mp.setattr(repo, "amz_sales_amount_by_department", lambda month: {
            code: Decimal("100000") for code in DEPARTMENTS if code.startswith("AMZ-")
        } if amz_ready() else None)
        mp.setattr(repo, "ebay_sales_volume", lambda month: Decimal("8411") if ebay_ready() else None)
        mp.setattr(repo, "ebay_sales_amount", lambda month: Decimal("355000") if ebay_ready() else None)
        mp.setattr(repo, "amz_sales_amount_by_store", lambda month: [
            {"department_code": "AMZ-US1", "store_name": "US1-示例店铺-US", "sales_amount": Decimal("6000")},
        ] if amz_ready() else [])
        mp.setattr(repo, "amz_sales_volume_by_store", lambda month: [
            {"department_code": "AMZ-US1", "store_name": "US1-示例店铺-US", "sales_volume": Decimal("600")},
            {"department_code": "AMZ-US2-MJ", "store_name": "MJ-MJ店铺-US", "sales_volume": Decimal("90")},
        ] if amz_ready() else None)
        mp.setattr(repo, "sales_amount_by_owner", lambda month: {
            ("AMZ", "AMZ-US1", "负责人甲"): Decimal("7000"),
            ("EBAY", "EBAY-1", "负责人乙"): Decimal("9000"),
        } if amz_ready() else {})
        mp.setattr(repo, "amz_sales_volume_by_owner", lambda month: [
            {"department_code": "AMZ-US1", "principal_name": "负责人甲", "sales_volume": Decimal("700")},
        ] if amz_ready() else None)
        mp.setattr(repo, "ebay_sales_volume_rows", lambda month: [
            {"sku": "BMW-1", "sales_volume": Decimal("800")},
            {"sku": "UNKNOWN", "sales_volume": Decimal("11")},
        ] if ebay_ready() else None)
        mp.setattr(repo, "view_snapshot", lambda month, dimension: deepcopy(
            self.snapshots.get((month, dimension))
        ))

        @contextmanager
        def transaction():
            self.events.append("begin")
            yield object()
            self.events.append("commit")

        def for_update(month):
            self.events.append(("lock_rows", month))
            return {dimension: deepcopy(payload)
                    for (stored_month, dimension), payload in self.snapshots.items()
                    if stored_month == month}

        def save(month, payloads, *, only_missing=False, touch_calculated_at=True):
            self.saved.append((month, deepcopy(payloads), touch_calculated_at))
            for dimension, payload in payloads.items():
                self.snapshots[(month, dimension)] = deepcopy(payload)

        @contextmanager
        def named_lock(name):
            self.events.append(("named_lock", name))
            yield True

        mp.setattr(repo, "report_transaction", transaction)
        mp.setattr(repo, "view_snapshots_for_update", for_update)
        mp.setattr(repo, "save_view_snapshots", save)
        mp.setattr(service.performance_repo, "named_lock", named_lock)

    def freeze(self):
        """What the 10-13 calculation saved: inventory complete, sales empty."""
        self.snapshots[("2026-09", "GROUP")] = service.get_department_summary("2026-09", use_snapshot=False)
        self.snapshots[("2026-09", "STORE")] = service.get_dimension_summary("STORE", "2026-09", use_snapshot=False)
        self.snapshots[("2026-09", "OWNER")] = service.get_dimension_summary("OWNER", "2026-09", use_snapshot=False)
        return deepcopy(self.snapshots)

    def live(self, dimension):
        if dimension == "GROUP":
            return service.get_department_summary("2026-09", use_snapshot=False)
        return service.get_dimension_summary(dimension, "2026-09", use_snapshot=False)


def _rows(payload, dimension):
    rows = service._snapshot_rows(dimension, payload)
    return {key: row for key, row in rows.items()}


def _without_refresh_metadata(payload):
    return {key: value for key, value in payload.items() if key != "sales_refresh"}


def test_refresh_fills_saved_snapshot_exactly_like_a_fresh_calculation(monkeypatch):
    world = World(monkeypatch)
    frozen = world.freeze()
    group_before = frozen[("2026-09", "GROUP")]
    total_before = next(i for i in group_before["items"] if i["is_total"] == 1)
    assert total_before["monthly_sales_qty"] is None
    assert total_before["actual_achievement_amount"] is None

    world.sales_ready = True
    result = service.refresh_monthly_inventory_sales_snapshot("2026-10", trigger="test")

    assert result["status"] == "refreshed"
    assert result["stat_month"] == "2026-09"
    assert result["pending_reasons"] == []
    assert ("named_lock", "inventory:monthly-report-source:2026-09") in world.events
    assert world.events[-1] == "commit"
    [(month, payloads, touch)] = world.saved
    assert month == "2026-09" and touch is False
    assert set(payloads) == {"GROUP", "STORE", "OWNER"}
    for dimension in ("GROUP", "STORE", "OWNER"):
        refreshed = payloads[dimension]
        assert refreshed["sales_refresh"]["sales_month"] == "2026-10"
        assert refreshed["sales_refresh"]["trigger"] == "test"
        # Inventory did not change, so the targeted refresh must reproduce the
        # full calculation for every field, including totals and US3.
        assert _without_refresh_metadata(refreshed) == world.live(dimension)

    group = payloads["GROUP"]
    total = next(i for i in group["items"] if i["is_total"] == 1)
    assert Decimal(total["monthly_sales_qty"]) == Decimal("18314") + Decimal("8411")
    us3 = next(i for i in group["items"] if i["department_code"] == "AMZ-US3")
    assert Decimal(us3["monthly_sales_qty"]) == Decimal("4314")
    assert group["usd_rate"] == "7.10" and group["rate_month"] == "2026-10"


def test_refresh_keeps_frozen_inventory_when_live_inventory_moved(monkeypatch):
    world = World(monkeypatch)
    frozen = world.freeze()
    # Today's live DWS/owner rows differ from the month that was frozen.
    for row in world.department_rows:
        if row.get("overseas_end_inventory_qty") is not None:
            row["overseas_end_inventory_qty"] += 999
    world.owner_rows[0]["dimension_value"] = "新负责人"
    world.sales_ready = True

    assert service.refresh_monthly_inventory_sales_snapshot("2026-10")["status"] == "refreshed"

    for dimension in ("GROUP", "STORE", "OWNER"):
        before = _rows(frozen[("2026-09", dimension)], dimension)
        after = _rows(world.snapshots[("2026-09", dimension)], dimension)
        assert before.keys() == after.keys()
        for key, old_row in before.items():
            for field, value in old_row.items():
                if field not in service.SALES_REFRESH_ROW_FIELDS:
                    assert after[key][field] == value, (dimension, key, field)
    group_total = next(
        i for i in world.snapshots[("2026-09", "GROUP")]["items"] if i["is_total"] == 1
    )
    old_total = next(i for i in frozen[("2026-09", "GROUP")]["items"] if i["is_total"] == 1)
    assert group_total["next_month_opening_inventory_qty"] == old_total["next_month_opening_inventory_qty"]
    assert group_total["sales_target_usd"] == old_total["sales_target_usd"]
    assert group_total["opening_inventory_sales_ratio"] is not None


def test_repeated_refresh_is_idempotent_and_does_not_write_again(monkeypatch):
    world = World(monkeypatch)
    world.freeze()
    world.sales_ready = True
    service.refresh_monthly_inventory_sales_snapshot("2026-10")
    first = deepcopy(world.snapshots)

    result = service.refresh_monthly_inventory_sales_snapshot("2026-10")

    assert result["status"] == "unchanged"
    assert len(world.saved) == 1
    assert world.snapshots == first


def test_missing_ebay_stays_blank_and_late_import_fills_it(monkeypatch):
    world = World(monkeypatch)
    world.freeze()
    world.sales_ready = True
    world.ebay_ready = False

    result = service.refresh_monthly_inventory_sales_snapshot("2026-10")

    assert result["status"] == "refreshed"
    assert "eBay月度利润尚未导入" in result["pending_reasons"]
    items = {i["department_code"]: i for i in world.snapshots[("2026-09", "GROUP")]["items"]}
    assert items["EBAY-1"]["monthly_sales_qty"] is None
    assert items["EBAY-1"]["actual_achievement_amount"] is None
    assert items["AUTO-PARTS-TOTAL"]["monthly_sales_qty"] is None
    assert Decimal(items["AMZ-US1"]["monthly_sales_qty"]) == Decimal("8000")

    world.ebay_ready = True
    late = service.refresh_monthly_inventory_sales_snapshot("2026-10", trigger="ebay_profit_import")

    assert late["status"] == "refreshed" and late["pending_reasons"] == []
    items = {i["department_code"]: i for i in world.snapshots[("2026-09", "GROUP")]["items"]}
    assert Decimal(items["EBAY-1"]["monthly_sales_qty"]) == Decimal("8411")
    assert Decimal(items["AUTO-PARTS-TOTAL"]["monthly_sales_qty"]) == Decimal("26725")


def test_late_rate_updates_amounts_without_touching_volumes(monkeypatch):
    world = World(monkeypatch)
    world.freeze()
    world.sales_ready = True
    service.refresh_monthly_inventory_sales_snapshot("2026-10")
    world.rate = Decimal("7.00")

    result = service.refresh_monthly_inventory_sales_snapshot("2026-10", trigger="currency_sync")

    assert result["status"] == "refreshed"
    group = world.snapshots[("2026-09", "GROUP")]
    us1 = next(i for i in group["items"] if i["department_code"] == "AMZ-US1")
    assert group["usd_rate"] == "7.00"
    assert Decimal(us1["actual_achievement_amount_usd"]) == (Decimal("100000") / Decimal("7")).quantize(Decimal("0.01"))
    assert Decimal(us1["monthly_sales_qty"]) == Decimal("8000")


def test_source_that_disappeared_does_not_blank_a_filled_snapshot(monkeypatch):
    world = World(monkeypatch)
    world.freeze()
    world.sales_ready = True
    service.refresh_monthly_inventory_sales_snapshot("2026-10")
    filled = deepcopy(world.snapshots)
    world.ebay_ready = False  # e.g. the eBay month is being re-imported

    result = service.refresh_monthly_inventory_sales_snapshot("2026-10")

    assert result["status"] == "source_incomplete"
    assert result["regressions"]
    assert len(world.saved) == 1
    assert world.snapshots == filled


def test_dry_run_lists_only_sales_fields_without_lock_or_write(monkeypatch):
    world = World(monkeypatch)
    world.freeze()
    world.sales_ready = True

    result = service.refresh_monthly_inventory_sales_snapshot("2026-10", dry_run=True)

    assert result["status"] == "preview"
    assert world.saved == [] and world.events == []
    assert result["changes"]
    assert {c["field"] for c in result["changes"]} <= set(
        service.SALES_REFRESH_ROW_FIELDS
    )
    assert {c["dimension"] for c in result["changes"]} == {"GROUP", "STORE", "OWNER"}


def test_snapshot_that_no_longer_reproduces_is_rejected(monkeypatch):
    world = World(monkeypatch)
    world.freeze()
    group = world.snapshots[("2026-09", "GROUP")]
    us1 = next(i for i in group["items"] if i["department_code"] == "AMZ-US1")
    us1["sales_target_usd"] = "1.00"
    world.sales_ready = True

    with pytest.raises(ValueError, match="sales_target_usd"):
        service.refresh_monthly_inventory_sales_snapshot("2026-10")
    assert world.saved == []

    safe = service.refresh_monthly_inventory_sales_snapshot_safely("2026-10", trigger="test")
    assert safe["status"] == "failed" and "sales_target_usd" in safe["reason"]


def test_historical_import_and_missing_snapshot_are_skipped(monkeypatch):
    world = World(monkeypatch)
    world.sales_ready = True

    missing = service.refresh_monthly_inventory_sales_snapshot("2026-10")
    assert missing["status"] == "no_snapshot"

    world.snapshots[("2026-09", "GROUP")] = {
        "historical_import": True, "report_month": "2026-10", "items": [],
    }
    skipped = service.refresh_monthly_inventory_sales_snapshot("2026-10")
    assert skipped["status"] == "skipped"
    assert world.saved == []


def test_locked_month_is_reported_without_reading_snapshots(monkeypatch):
    world = World(monkeypatch)
    world.freeze()

    @contextmanager
    def busy(_name):
        yield False

    monkeypatch.setattr(service.performance_repo, "named_lock", busy)
    monkeypatch.setattr(service.repo, "view_snapshots_for_update",
                        lambda _m: pytest.fail("locked month must not be read"))

    result = service.refresh_monthly_inventory_sales_snapshot("2026-10")

    assert result["status"] == "locked"


@pytest.mark.parametrize(("report_month", "stat_month"), [("2026-10", "2026-09"), ("2027-01", "2026-12")])
def test_display_month_maps_to_previous_snapshot_partition(monkeypatch, report_month, stat_month):
    reads = []
    monkeypatch.setattr(service.repo, "view_snapshot", lambda month, dimension: reads.append(month))

    result = service.refresh_monthly_inventory_sales_snapshot(report_month, dry_run=True)

    assert result["stat_month"] == stat_month and result["sales_month"] == report_month
    assert set(reads) == {stat_month}


def test_sales_volume_sync_records_refresh_separately(monkeypatch):
    monkeypatch.setattr(source_sync.repo, "amazon_seller_ids", lambda *args, **kwargs: ["1"])
    monkeypatch.setattr(source_sync, "LingXingOrderProfitDomain", lambda: object())
    monkeypatch.setattr(source_sync, "_fetch_order_profit", lambda *_a: ([{"id": 1}], 0))
    monkeypatch.setattr(source_sync.repo, "replace_order_profit_month",
                        lambda *_a: {"inserted_rows": 1, "deleted_rows": 0})
    monkeypatch.setattr(source_sync, "rebuild_monthly_inventory_amz_sales",
                        lambda month: {"dwd_rows": 1, "deleted_rows": 0})
    calls = []
    monkeypatch.setattr(
        source_sync, "refresh_monthly_inventory_sales_snapshot_safely",
        lambda month, **kwargs: calls.append((month, kwargs)) or {"status": "failed", "reason": "boom"},
    )

    result = source_sync.sync_monthly_inventory_sales_volume("2026-10")

    assert result["status"] == "completed"
    assert result["report_refresh"] == {"status": "failed", "reason": "boom"}
    assert calls == [("2026-10", {"trigger": "sales_volume_sync"})]


def test_daily_compensation_task_uses_previous_month_and_reports_lock(monkeypatch):
    spec = scheduler_service.TASK_SPECS["monthly_inventory_report_sales_snapshot_refresh"]
    assert spec.default_previous_month is True
    assert spec.lock_name is None
    monkeypatch.setattr(
        source_sync, "refresh_monthly_inventory_sales_snapshot",
        lambda month, **kwargs: {"status": "refreshed", "changed_rows": 3, "report_month": month},
    )

    result = source_sync.refresh_previous_month_sales_snapshot("2026-10")

    assert result["report_refresh"]["report_month"] == "2026-10"
    assert result["updated_rows"] == 3
    assert {"extract_rows", "ods_rows", "sync_batch_id"} <= set(result)

    monkeypatch.setattr(
        source_sync, "refresh_monthly_inventory_sales_snapshot",
        lambda month, **kwargs: {"status": "locked", "reason": "busy"},
    )
    with pytest.raises(source_sync.InventoryReportSourceSyncError) as error:
        source_sync.refresh_previous_month_sales_snapshot("2026-10")
    assert error.value.stage == "LOCK"


def test_currency_task_refreshes_the_rate_month(monkeypatch):
    monkeypatch.setattr(currency_sync_service, "sync_currency_month",
                        lambda month: {"rate_month": month, "stored_rows": 1})
    calls = []
    monkeypatch.setattr(
        currency_sync_service, "refresh_monthly_inventory_sales_snapshot_safely",
        lambda month, **kwargs: calls.append((month, kwargs)) or {"status": "refreshed"},
    )

    result = currency_sync_service.sync_currency_month_and_refresh_report("2026-10")

    assert calls == [("2026-10", {"trigger": "currency_sync"})]
    assert result["report_refresh"] == {"status": "refreshed"}


@pytest.mark.parametrize("rebuild", [True, False])
def test_ebay_profit_import_refreshes_after_ranking(monkeypatch, rebuild):
    events = []
    monkeypatch.setattr(performance_service, "parse_ebay_profit_excel", lambda *_a, **_k: {
        "stat_month": "2026-10", "rows": [], "raw_rows": [], "file_hash": "x", "totals": {},
    })
    monkeypatch.setattr(performance_service.repo, "performance_connection",
                        lambda: nullcontext(type("C", (), {"commit": lambda self: None})()))
    monkeypatch.setattr(performance_service.repo, "replace_ebay_profit_month", lambda *_a: None)
    monkeypatch.setattr(performance_service.repo, "insert_import_batch", lambda *_a: None)
    monkeypatch.setattr(performance_service, "refresh_performance",
                        lambda *_a, **_k: events.append("ranking") or {"status": "completed"})
    monkeypatch.setattr(
        performance_service, "refresh_monthly_inventory_sales_snapshot_safely",
        lambda month, **kwargs: events.append(("report", month, kwargs["trigger"])) or {"status": "refreshed"},
    )

    result = performance_service.import_ebay_profit(b"", "f.xlsx", rebuild=rebuild)

    if rebuild:
        assert events == ["ranking", ("report", "2026-10", "ebay_profit_import")]
        assert result["report_refresh"] == {"status": "refreshed"}
    else:
        assert events == [] and result["report_refresh"] is None


class _Cursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.log.append(sql)

    def fetchall(self):
        return [{"dimension_type": "GROUP", "payload_json": "{\"items\": []}"}]


class _Connection:
    def __init__(self):
        self.log = []
        self.commits = 0

    def cursor(self):
        return _Cursor(self.log)

    def begin(self):
        self.log.append("BEGIN")

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.log.append("ROLLBACK")


def test_repository_locks_and_saves_without_touching_calculated_at(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(repo_module, "_database_connection", lambda: nullcontext(connection))

    with pytest.raises(RuntimeError):
        repo_module.view_snapshots_for_update("2026-09")
    with repo_module.report_transaction():
        assert repo_module.view_snapshots_for_update("2026-09") == {"GROUP": {"items": []}}
        repo_module.save_view_snapshots("2026-09", {"GROUP": {}}, touch_calculated_at=False)
        assert connection.commits == 0

    assert connection.commits == 1
    assert "FOR UPDATE" in connection.log[1]
    assert "calculated_at" not in connection.log[2]
    assert "payload_json=VALUES(payload_json)" in connection.log[2]


def test_source_sync_refreshes_rate_months_after_rebuild(monkeypatch):
    events = []
    monkeypatch.setattr(source_sync, "_month_scope", lambda _month: (
        "2026-10", "2026-10-01", "2026-10-31",
    ))
    monkeypatch.setattr(source_sync, "sync_inventory_currency_rates", lambda _month: {
        "rate_months": ["2026-10", "2026-11"],
    })
    monkeypatch.setattr(source_sync.repo, "amazon_seller_ids", lambda *args, **kwargs: ["seller-1"])
    monkeypatch.setattr(source_sync.repo, "warehouse_wids", lambda: ["warehouse-1"])
    monkeypatch.setattr(source_sync, "LingXingInventoryDomain", lambda: object())
    monkeypatch.setattr(source_sync, "_fetch_fba", lambda *_a, **_k: [{}])
    monkeypatch.setattr(source_sync, "_fetch_warehouse_report", lambda **_k: [{}])
    monkeypatch.setattr(source_sync.repo, "replace_source_month",
                        lambda *_a: {"deleted_rows": 0, "inserted_rows": 3})
    monkeypatch.setattr(
        source_sync, "rebuild_monthly_inventory_report",
        lambda month, **_k: events.append("rebuild") or {
            "fba_detail_rows": 1, "overseas_detail_rows": 1,
            "local_detail_rows": 1, "amz_sales_detail_rows": 0,
            "dimension_summary_rows": 1, "department_summary_rows": 1,
            "inserted_rows": 5, "deleted_rows": 0,
        },
    )
    monkeypatch.setattr(
        source_sync, "refresh_monthly_inventory_sales_snapshot_safely",
        lambda month, **kwargs: events.append((month, kwargs["lock_held_by_caller"]))
        or {"status": "unchanged"},
    )

    result = source_sync.sync_monthly_inventory_report_sources("2026-10")

    # 2026-11 displays the 2026-10 snapshot whose lock the scheduler holds.
    assert events == ["rebuild", ("2026-10", False), ("2026-11", True)]
    assert [item["status"] for item in result["report_refresh"]] == ["unchanged"] * 2
