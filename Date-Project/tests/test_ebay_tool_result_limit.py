"""Offline tests: no eBay calls, credentials or database required."""
import pytest

from backend.ebay_tool import app as tool


def raw_items(count=100, category="cat"):
    return [
        {"itemId": str(i), "title": f"Part {i}",
         "price": {"value": str(count - i), "currency": "EUR"},
         "categories": [{"categoryId": category}]}
        for i in range(count)
    ]


@pytest.mark.parametrize("path", [
    "best_match", "category_locked", "no_category", "category_pool_fallback", "no_pool",
])
def test_all_search_paths_return_100(monkeypatch, path):
    calls = []

    def search(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 2 and path in ("category_pool_fallback", "no_pool"):
            return None, "second search unavailable"
        return {"itemSummaries": raw_items()}, None

    monkeypatch.setattr(tool, "search_ebay", search)
    monkeypatch.setattr(tool, "get_item_product_type", lambda *args: "Part")
    category = "" if path == "no_category" else "missing" if path == "no_pool" else "cat"
    monkeypatch.setattr(tool, "_pick_dominant_category", lambda *args: (category, "Parts", .8, []))
    result = tool.scrape_one_oe("OE-1", "de", search_strategy="best_match" if path == "best_match" else "category_lock")
    assert len(result[0]) == 100
    assert [item["pf"] for item in result[0]] == sorted(item["pf"] for item in result[0])
    assert all(call["limit"] == 100 for call in calls)
    assert result[3] == ("best_match_fallback" if path in ("no_category", "no_pool") else path)


def test_finalize_caps_and_keeps_verification_at_five(monkeypatch):
    verified = []

    def verify(item_id, marketplace):
        verified.append(item_id)
        return "Part"

    monkeypatch.setattr(tool, "get_item_product_type", verify)
    result = tool._finalize_oe(raw_items(130), "OE-1", "category_locked", "EBAY_DE", None, verify=True)
    assert len(result[0]) == 100
    assert len(verified) == tool.VERIFY_TOP_N == 5
    assert all(item["productType"] == "Part" for item in result[0][:5])


def test_fewer_available_items_are_not_padded(monkeypatch):
    monkeypatch.setattr(tool, "search_ebay", lambda *args, **kwargs: ({"itemSummaries": raw_items(7)}, None))
    assert len(tool.scrape_one_oe("OE-1", "de", search_strategy="best_match")[0]) == 7
