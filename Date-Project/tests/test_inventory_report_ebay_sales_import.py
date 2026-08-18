from __future__ import annotations

from io import BytesIO

import pandas as pd

from backend.parsers.inventory_report_ebay_sales_parser import (
    parse_inventory_report_ebay_sales_excel,
)
from backend.services import inventory_report_etl_service as service


def _workbook_bytes(rows: list[dict]) -> bytes:
    output = BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False, sheet_name="sheet1")
    return output.getvalue()


def test_parser_uses_selected_month_and_sales_plus_shipping():
    content = _workbook_bytes(
        [
            {
                "SKU": "BMW-30001-0001",
                "图片": "https://example.com/a.jpg",
                "是否多属性": "否",
                "商品销售额": "1,000.25",
                "应收运费": "20.75",
            }
        ]
    )

    result = parse_inventory_report_ebay_sales_excel(
        content, "SKU利润表.xlsx", "2026-07", "tester"
    )

    assert result["stat_month"] == "2026-07"
    assert result["source_rows"] == 1
    assert result["total_amount"] == service.Decimal("1021.000000")
    assert result["rows"][0]["brand_code"] == "BMW"
    assert result["rows"][0]["amount"] == service.Decimal("1021.000000")


def test_parser_rejects_missing_sku_with_amount():
    content = _workbook_bytes(
        [{"SKU": "", "商品销售额": 10, "应收运费": 0}]
    )

    try:
        parse_inventory_report_ebay_sales_excel(
            content, "SKU利润表.xlsx", "2026-07"
        )
    except ValueError as exc:
        assert "SKU为空" in str(exc)
    else:
        raise AssertionError("missing SKU must fail")


def test_ebay_sales_cleaning_matches_owner_and_updates_actual():
    rule_rows = [
        {
            "rule_type": "EBAY_BRAND",
            "match_key": "BMW",
            "principal_name": "陈丽",
        }
    ]
    rules = service._ebay_rule_map(rule_rows)
    clean_rows, stats = service._clean_ebay_sales(
        "2026-07",
        [
            {
                "id": 1,
                "sku": "BMW-30001-0001",
                "brand_code": "BMW",
                "product_sales_amount": service.Decimal("100"),
                "receivable_shipping_amount": service.Decimal("5"),
                "amount": service.Decimal("105"),
            }
        ],
        rules,
    )

    assert stats == {
        "ebay_sales_matched_rows": 1,
        "ebay_sales_unmatched_rows": 0,
    }
    assert clean_rows[0]["principal_name"] == "陈丽"
    assert clean_rows[0]["department_code"] == "EBAY-1"
    summary = service._department_summaries(
        "2026-07", [], [], [], ebay_sales_rows=clean_rows
    )
    ebay = next(row for row in summary if row["department_code"] == "EBAY-1")
    total = next(
        row for row in summary if row["department_code"] == "AUTO-PARTS-TOTAL"
    )
    assert ebay["actual_achievement_amount"] == service.Decimal("105")
    assert total["actual_achievement_amount"] == service.Decimal("105")


def test_ebay_actual_upload_rebuilds_business_month_sales_only(monkeypatch):
    parsed = {
        "stat_month": "2026-08",
        "batch_id": "batch-1",
        "source_rows": 1,
        "rows": [{"stat_month": "2026-08", "sku": "BMW-1"}],
        "skipped_rows": 0,
        "total_amount": service.Decimal("105"),
    }
    monkeypatch.setattr(
        service,
        "parse_inventory_report_ebay_sales_excel",
        lambda *_args, **_kwargs: parsed,
    )
    monkeypatch.setattr(
        service.repo,
        "replace_ebay_sales_source_month",
        lambda month, rows: {"deleted_rows": 0, "inserted_rows": len(rows)},
    )
    monkeypatch.setattr(
        service,
        "rebuild_monthly_inventory_ebay_sales",
        lambda month: {"stat_month": month, "dwd_rows": 1},
    )
    monkeypatch.setattr(
        service,
        "rebuild_monthly_inventory_report",
        lambda _month: (_ for _ in ()).throw(
            AssertionError("eBay业务月上传不应重建同月库存报表")
        ),
    )

    result = service.import_inventory_report_ebay_sales(
        b"xlsx", "SKU利润表.xlsx", "2026-08", "tester"
    )

    assert result["stat_month"] == "2026-08"
    assert result["inserted_rows"] == 1
    assert result["rebuild"]["dwd_rows"] == 1
