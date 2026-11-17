"""Owner totals are already calculated from all filtered sites before group pagination."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from backend.services import ebay_inventory_pivot_service as service


def detail(owner, site, day=date(2026, 9, 16), **fields):
    return {"owner": owner, "site": site, "stat_date": day, **fields}


def test_complete_groups_interleaved_in_server_total_sort_order_and_only_once():
    data = {
        "items": [detail("B", "英国"), detail("A", "德国"), detail("B", "德国")],
        "owner_totals": [detail("B", "ignored", site_count=2, overseas_total_quantity=Decimal(30)),
                         detail("A", "ignored", site_count=1, overseas_total_quantity=Decimal(10))],
        "pagination": {"page": 1, "page_size": 2, "total": 15},
    }
    result = service._insert_owner_totals(deepcopy(data))
    assert [(r["owner"], r["site"], r["row_type"]) for r in result["items"]] == [
        ("B", "德国", "DETAIL"), ("B", "英国", "DETAIL"), ("B", "负责人汇总", "OWNER_TOTAL"),
        ("A", "德国", "DETAIL"), ("A", "负责人汇总", "OWNER_TOTAL"),
    ]
    assert result["pagination"] == data["pagination"]
    assert "owner_totals" not in result
    assert "row_type" not in data["items"][0]


def test_same_owner_different_dates_do_not_merge():
    yesterday, today = date(2026, 9, 14), date(2026, 9, 16)
    result = service._insert_owner_totals({
        "items": [detail("A", "德国", yesterday), detail("A", "德国", today)],
        "owner_totals": [detail("A", "", today, site_count=1), detail("A", "", yesterday, site_count=1)],
    })
    assert [(r["stat_date"], r["row_type"]) for r in result["items"]] == [
        (today, "DETAIL"), (today, "OWNER_TOTAL"), (yesterday, "DETAIL"), (yesterday, "OWNER_TOTAL")]


@pytest.mark.parametrize("totals", [[], [detail("B", "", site_count=1)],
                                      [detail("A", "", site_count=2)],
                                      [detail("A", "", site_count=1)] * 2])
def test_mismatched_or_duplicate_groups_rejected(totals):
    with pytest.raises(ValueError):
        service._insert_owner_totals({"items": [detail("A", "德国")], "owner_totals": totals})


def test_empty_history_stays_empty():
    assert service._insert_owner_totals({"items": [], "owner_totals": []}) == {"items": []}


def test_list_keeps_totals_decimal_precision_and_page_group_metadata(monkeypatch):
    monkeypatch.setattr(service.repository, "read_history", lambda **kw: {
        "items": [detail("A", "德国", overseas_sellable_value=None)],
        "owner_totals": [detail("A", "", site_count=1, overseas_sellable_value=None,
                                 in_stock_sales_ratio=Decimal("1.234567"), warehouse_rent_30d_cny=Decimal("0.00"))],
        "pagination": {"page": 1, "page_size": 50, "total": 1},
        "metadata": {"pagination_unit": "owner_date", "detail_count": 1, "owner_total_count": 1},
    })
    result = service.list_pivot()
    total = result["items"][-1]
    assert total["in_stock_sales_ratio"] == "1.234567"
    assert total["warehouse_rent_30d_cny"] == "0.00"
    assert total["overseas_sellable_value"] is None
    assert total["stat_date"] == "2026-09-16"
    assert total["row_type"] == "OWNER_TOTAL"
    assert result["pagination"]["total"] == 1
    assert result["metadata"]["detail_count"] == 1
