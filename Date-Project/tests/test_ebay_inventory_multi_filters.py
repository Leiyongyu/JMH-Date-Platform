"""Multi-value filters share live/history, paging and export paths; no DB writes."""
from copy import deepcopy
from io import BytesIO

import pytest
from openpyxl import load_workbook

from backend.api.v1 import ebay_inventory_detail as api
from backend.services import ebay_inventory_detail_service as service
from backend.services import ebay_inventory_detail_export_service as exporter
from test_ebay_inventory_detail import graded, isolated, source
from test_ebay_inventory_pivot_api_export import client


def install_rows(isolated):
    isolated([
        source(sku="DAS-10053-0121", **graded("A")),
        source(sku="JMH-10053-0121-YXQ", **graded("S")),
        source(sku="MCD-20017-0071", **graded("B")),
        source(sku="MCD-20017-0071", site="英国", **graded("B")),
        source(sku="DAS-100530-0121", **graded("A")),
        source(sku="DAS-00123-0121", **graded("A")),
        source(sku="DAS-123-0121", **graded("A")),
    ])


def test_multi_value_or_and_cross_field_and_before_paging(isolated):
    install_rows(isolated)
    filters = dict(site="德国", sku=" 10053,20017,10053, ,", brand="jmh,MCD", grade="S,B")
    first = service.list_inventory(**filters, page_size=1)
    second = service.list_inventory(**filters, page_size=1, page=2)
    assert first["pagination"]["total"] == second["pagination"]["total"] == 2
    assert first["items"][0]["sku"] != second["items"][0]["sku"]
    all_rows = service.list_inventory(**filters, paginate=False)["items"]
    assert {row["sku_middle_code"] for row in all_rows} == {"10053", "20017"}
    merged = next(row for row in all_rows if row["sku_middle_code"] == "10053")
    # graded() 现在通过 sales_qty_30d 给观测值：A档10 + S档30 = 40。
    assert merged["sales_qty_30d"] == "40"  # Whole merged group, not just matching alias.
    assert merged["merged_sku_count"] == 2
    assert service.list_inventory(sku="1005")["pagination"]["total"] == 0
    assert [row["sku_middle_code"] for row in service.list_inventory(sku="00123")["items"]] == ["00123"]
    assert service.list_inventory(sku=" , ,")["pagination"]["total"] == 6


def test_export_all_and_selected_use_identical_multi_filters(isolated):
    install_rows(isolated)
    filters = dict(site="德国", sku="10053,20017", brand="DAS,MCD", grade="A,B")
    rows = service.list_inventory(**filters, paginate=False)["items"]
    _, content = exporter.export_inventory(**filters)
    book = load_workbook(BytesIO(content), read_only=True)
    try:
        data = list(book.active.values)
        sku_col = data[0].index("SKU")
        assert [row[sku_col] for row in data[1:]] == [row["sku"] for row in rows]
    finally:
        book.close()
    key = {name: rows[0][name] for name in ("site", "sku")}
    assert len(service.list_inventory(**filters, selected_keys=[key], paginate=False)["items"]) == 1
    with pytest.raises(ValueError, match="不在当前筛选"):
        service.list_inventory(**filters, selected_keys=[{"site": "德国", "sku": "DAS-123-0121"}])


def test_history_missing_middle_matches_without_recalculation_or_dedup(isolated, monkeypatch):
    install_rows(isolated)
    rows, meta, warnings, _ = service.load_calculated_inventory()
    rows = [row for row in rows if row["sku_middle_code"] == "00123"]
    rows[0].pop("sku_middle_code")
    rows[0]["history_origin"] = "EXCEL_IMPORT"
    rows[0]["record_key"] = "DE:1"
    rows.append({**rows[0], "record_key": "DE:2"})
    before = deepcopy(rows)
    monkeypatch.setattr(service.history_repository, "read_inventory_day", lambda day: (rows, meta, warnings))
    monkeypatch.setattr(service, "load_calculated_inventory", lambda: pytest.fail("must not recalculate history"))
    data = service.list_inventory(stat_date="2026-09-16", sku="00123,20017", brand="DAS,MCD", grade="A,S")
    assert data["pagination"]["total"] == 2
    assert {row["record_key"] for row in data["items"]} == {"DE:1", "DE:2"}
    assert rows == before


@pytest.mark.parametrize("sku", ["10053，20017", "DAS-10053-0121", "10053 OR 1=1", "10053\n20017", "１００５３"])
def test_invalid_middle_filters_fail_before_source_read(monkeypatch, sku):
    monkeypatch.setattr(service, "load_calculated_inventory", lambda: pytest.fail("unexpected data read"))
    with pytest.raises(ValueError, match="数字中间码"):
        service.list_inventory(sku=sku)


@pytest.mark.parametrize("field", ["sku", "brand", "grade"])
def test_limits_are_enforced_before_source_read(monkeypatch, field):
    monkeypatch.setattr(service, "load_calculated_inventory", lambda: pytest.fail("unexpected data read"))
    with pytest.raises(ValueError, match="100项"):
        service.list_inventory(**{field: ",".join(str(n) for n in range(101))})
    with pytest.raises(ValueError, match="2048"):
        service.list_inventory(**{field: "1" * 2049})


def test_api_list_export_accept_same_long_csv_and_report_invalid_filter(client, monkeypatch):
    filters = {"sku": ",".join(str(10000 + n) for n in range(50)), "brand": "DAS,MCD", "grade": "A,S"}
    calls = []
    original = service.list_inventory
    monkeypatch.setattr(service, "list_inventory", lambda **kw: calls.append(kw) or {"items": []})
    response = client.get("/api/v1/finance/ebay-inventory-detail/list", params=filters)
    assert response.status_code == 200
    assert {key: calls[-1][key] for key in filters} == filters
    monkeypatch.setattr(api, "export_inventory", lambda **kw: calls.append(kw) or ("test.xlsx", b"PKtest"))
    response = client.post("/api/v1/finance/ebay-inventory-detail/export", json=filters)
    assert response.status_code == 200
    assert {key: calls[-1][key] for key in filters} == filters
    monkeypatch.setattr(service, "list_inventory", original)
    response = client.get("/api/v1/finance/ebay-inventory-detail/list", params={"sku": "10053，20017"})
    assert response.status_code == 400
    assert "英文逗号" in response.json()["detail"]
