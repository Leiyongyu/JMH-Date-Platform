from datetime import datetime
from decimal import Decimal

from backend.services.clearance_service import _ebay_inventory_age_rows


def test_ebay_inventory_age_cost_groups_by_age_without_quantity_multiplier():
    rows, stats = _ebay_inventory_age_rows(
        "2026-08",
        "batch-1",
        datetime(2026, 8, 18, 12, 0, 0),
        [
            {
                "source_inventory_age_id": 1,
                "source_goodcang_batch_id": "goodcang-1",
                "source_product_batch_id": "product-1",
                "source_product_sku": "JMH-220085-0056",
                "sku_middle": "220085-0056",
                "sku": "HME-220085-0056",
                "warehouse_code": "USWE",
                "warehouse_name": "加州区",
                "transport_country_code": "US",
                "inventory_quantity": 4,
                "warehouse_age_days": 180,
                "cg_price": Decimal("760"),
                "step_price": Decimal("0"),
                "first_leg_cost": Decimal("63.4567"),
                "candidate_count": 2,
                "non_jmh_count": 1,
                "source_pulled_at": datetime(2026, 8, 18, 10, 0, 0),
            }
        ],
    )

    assert rows[0]["inventory_age_bucket"] == "91_180"
    assert rows[0]["purchase_price"] == Decimal("760")
    assert rows[0]["unit_landed_cost"] == Decimal("823.4567")
    assert rows[0]["inventory_age_cost"] == Decimal("823.4567")
    assert stats["ebay_matched_rows"] == 1


def test_ebay_inventory_age_cost_keeps_unmatched_source_row():
    rows, stats = _ebay_inventory_age_rows(
        "2026-08",
        "batch-1",
        datetime(2026, 8, 18, 12, 0, 0),
        [
            {
                "source_inventory_age_id": 2,
                "source_goodcang_batch_id": "goodcang-1",
                "source_product_sku": "JMH-NOT-FOUND",
                "sku_middle": "NOT-FOUND",
                "warehouse_code": "DE",
                "warehouse_name": "德国区",
                "transport_country_code": "DE",
                "inventory_quantity": 3,
                "warehouse_age_days": 181,
                "candidate_count": 0,
                "non_jmh_count": 0,
                "source_pulled_at": datetime(2026, 8, 18, 10, 0, 0),
            }
        ],
    )

    assert rows[0]["inventory_age_bucket"] == "181_PLUS"
    assert rows[0]["match_status"] == "PRODUCT_NOT_FOUND"
    assert rows[0]["inventory_age_cost"] is None
    assert stats["ebay_unmatched_rows"] == 1
