"""Execute the isolated stock CTE against fixtures; no production writes or APIs."""
import sqlite3

import pytest

from backend.repositories import ebay_inventory_detail_repository as repository
from backend.services.ebay_inventory_shared import inventory_ctes


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE ods_lingxing_inventory_detail_weekly (
            id INTEGER PRIMARY KEY, sync_batch_id TEXT,snapshot_date TEXT,pulled_at TEXT,
            wid INTEGER,product_id INTEGER,seller_id TEXT,sku TEXT,
            product_total NUMERIC,product_valid_num NUMERIC,product_onway NUMERIC,quantity_receive NUMERIC
        );
        CREATE TABLE ops_weekly_export_file (
            export_code TEXT,sync_batch_id TEXT,snapshot_date TEXT,status TEXT,generated_at TEXT
        );
    """)
    yield conn
    conn.close()


def batch(db, name="new", day="2026-09-14", status="SUCCESS", generated="2026-09-14"):
    db.execute("INSERT INTO ops_weekly_export_file VALUES (?,?,?,?,?)",
               ("weekly_inventory_bin", name, day, status, generated))


def stock(db, *, name="new", day="2026-09-14", wid=18699, product=1, seller="0",
          sku="FRD-001", total=10, available=8, transit=2, receive=3):
    db.execute("INSERT INTO ods_lingxing_inventory_detail_weekly VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)",
               (name, day, day + " 10:00:00", wid, product, seller, sku, total, available, transit, receive))


def rows(db):
    return [dict(row) for row in db.execute(
        "WITH " + repository._weekly_inventory_ctes() + " SELECT * FROM inventory_summary ORDER BY site,sku")]


@pytest.mark.parametrize("status", ["SUCCESS", "DELETE_PENDING", "DELETED"])
def test_only_latest_successful_source_batch_not_latest_export(db, status):
    batch(db, "old", "2026-09-10", generated="2026-09-30")
    stock(db, name="old", day="2026-09-10", available=999)
    batch(db, status=status)
    stock(db)
    # Newer failed/running/unregistered data cannot replace the last good batch.
    for index, state in enumerate(["FAILED", "RUNNING", None], 15):
        day = f"2026-09-{index}"
        if state:
            batch(db, state, day, status=state)
        stock(db, name=str(state), day=day, available=777)
    result = rows(db)
    assert len(result) == 1
    assert result[0]["overseas_sellable_quantity"] == 8


def test_whole_row_dedup_does_not_add_sellers_or_mix_column_maxima(db):
    batch(db)
    stock(db, total=20, available=3, transit=7, seller="0")
    stock(db, total=10, available=9, transit=99, seller="9")
    result = rows(db)[0]
    assert result["overseas_sellable_quantity"] == 3
    assert result["overseas_in_transit_quantity"] == 7
    assert result["pending_outbound_quantity"] == 20  # Same whole-row representative.


def test_representative_tie_and_null_total_match_weekly_export(db):
    batch(db)
    stock(db, total=None, seller="99", available=999)
    stock(db, total=0, seller="0", available=2)
    stock(db, total=0, seller="9", available=4)
    assert rows(db)[0]["overseas_sellable_quantity"] == 4


def test_exact_seven_warehouses_and_all_four_quantities(db):
    batch(db)
    for wid in [18674,18675,18676,18699,18700,18701,18702,18677,19561,99999]:
        stock(db, wid=wid)
    result = {r["site"]: r for r in rows(db)}
    assert set(result) == {"德国", "英国", "美国"}
    for site, multiplier in [("德国", 1), ("英国", 1), ("美国", 2)]:
        assert result[site]["overseas_sellable_quantity"] == 8 * multiplier
        assert result[site]["overseas_in_transit_quantity"] == 2 * multiplier
        assert result[site]["chengdu_sellable_quantity"] == 8
        assert result[site]["chengdu_in_transit_quantity"] == 3
        assert result[site]["pending_outbound_quantity"] == 10 * (multiplier + 1)


def test_pending_outbound_uses_only_selected_batch_and_null_product_total_is_zero(db):
    batch(db, "old", "2026-09-10")
    stock(db, name="old", day="2026-09-10", total=999)
    batch(db)
    stock(db, total=None)
    assert rows(db)[0]["pending_outbound_quantity"] == 0


def test_full_sku_not_suffix_null_numbers_and_no_warehouse_fallback(db):
    batch(db)
    stock(db, sku=" FRD-001 ", available=None, transit=None)
    stock(db, product=2, sku="JMH-001", available=4)
    stock(db, product=3, sku=" ", available=999)
    batch(db, "old", "2026-09-10")
    stock(db, name="old", day="2026-09-10", wid=18702, available=999)
    result = rows(db)
    assert [r["sku"] for r in result] == ["FRD-001", "JMH-001"]
    assert result[0]["overseas_sellable_quantity"] == 0
    assert result[0]["overseas_in_transit_quantity"] == 0
    assert result[1]["overseas_sellable_quantity"] == 4


def test_missing_successful_snapshot_does_not_use_unpublished_data(db):
    stock(db)
    assert rows(db) == []
    batch(db, status="FAILED")
    assert rows(db) == []


def test_multiple_exports_do_not_multiply_stock_and_other_consumers_stay_old(db):
    batch(db)
    batch(db, status="DELETED")
    stock(db)
    assert rows(db)[0]["overseas_sellable_quantity"] == 8
    assert "jmh_data_platform.warehouse_inventory_detail" in inventory_ctes()
    assert "ods_lingxing_inventory_detail_weekly" not in inventory_ctes()


def test_metadata_and_source_share_the_same_snapshot_selector():
    from unittest.mock import MagicMock
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"inventory_batch_id": "new"}, {"rent_batch_count": 0}, {}, {}]
    metadata = repository._source_metadata(cursor)
    query = cursor.execute.call_args_list[0].args[0]
    assert repository._weekly_snapshot_cte() in query
    assert repository._weekly_snapshot_cte() in repository._weekly_inventory_ctes()
    assert "inventory_pulled_at" in query and metadata["inventory_batch_id"] == "new"
