from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from openpyxl import load_workbook

from backend.services.amazon_profit_sync_service import _transform_row
from backend.parsers.performance_owner_rule_parser import _raw
from backend.services.clearance_service import (
    REQUIRED_INVENTORY_FIELDS,
    _inventory_age_fields,
)
from backend.services import clearance_export_service


def test_amazon_profit_transform_keeps_only_required_product_and_amount_fields():
    item = {
        "currency_code": "CNY",
        "gross_profit": "12.34",
        "amount": "100.00",
        "refund_amount": "5.50",
        "price_list": [
            {
                "sid": 12576,
                "seller_sku": "MSKU-1",
                "local_sku": "SKU-1",
                "asin": "B000000001",
            }
        ],
        "seller_store_countries": [{"country": "DE"}],
        "unused_large_field": {"should_not": "be persisted"},
    }

    row, ods_row = _transform_row(
        item, "2026-07", "batch-1", datetime(2026, 8, 6, 20, 0, 0)
    )

    assert row is not None
    assert ods_row["sid"] == "12576"
    assert ods_row["seller_sku"] == "MSKU-1"
    assert ods_row["local_sku"] == "SKU-1"
    assert ods_row["asin"] == "B000000001"
    assert ods_row["gross_profit"] == Decimal("12.34")
    assert ods_row["amount"] == Decimal("100.00")
    assert ods_row["refund_amount"] == Decimal("5.50")
    assert ods_row["net_sales_amount"] == Decimal("94.50")
    assert "raw_json" not in ods_row
    assert "unused_large_field" not in ods_row
    assert "raw_json" not in row


def test_clearance_inventory_transform_keeps_all_and_only_requested_age_fields():
    item = {
        field: str(index + 1)
        for index, field in enumerate(REQUIRED_INVENTORY_FIELDS)
    }
    item["unused_stock_field"] = "999"

    result = _inventory_age_fields(item)

    assert tuple(result) == REQUIRED_INVENTORY_FIELDS
    assert result["inv_age_0_to_30_days"] == Decimal("1")
    assert result["inv_age_365_plus_price"] == Decimal("20")
    assert "unused_stock_field" not in result


def test_owner_rule_raw_row_is_one_structured_rule_per_month():
    rule = {
        "platform": "amazon",
        "stat_month": "2026-07",
        "group_code": "US1",
        "rule_type": "STORE",
        "match_key": "赵昕怡",
        "principal_name": "赵昕怡",
        "source_file_name": "负责人.xlsx",
        "source_sheet": "US1",
        "source_row": 2,
        "import_batch_id": "owner-batch-1",
    }

    result = _raw(rule)

    assert result["stat_month"] == "2026-07"
    assert result["match_key"] == "赵昕怡"
    assert "raw_json" not in result


def test_inventory_age_detail_export_contains_structured_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(
        clearance_export_service,
        "settings",
        SimpleNamespace(export_output_dir=str(tmp_path)),
    )
    monkeypatch.setattr(
        clearance_export_service.repo,
        "inventory_age_details",
        lambda month: {
            "pull_month": month,
            "items": [
                {
                    "pull_month": month,
                    "region_name": "欧洲组",
                    "group_code": "EU",
                    "sid": "12576",
                    "seller_sku": "MSKU-1",
                    "sku": "SKU-1",
                    **{field: Decimal("1.25") for field in REQUIRED_INVENTORY_FIELDS},
                    "pulled_at": datetime(2026, 8, 6, 20, 0, 0),
                    "sync_batch_id": "batch-1",
                }
            ],
        },
    )

    file_path, download_name = clearance_export_service.export_inventory_age_details(
        "2026-08"
    )
    workbook = load_workbook(file_path, read_only=True)
    sheet = workbook["库龄明细"]
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]

    assert download_name.startswith("2026-08-库龄明细-")
    assert headers[:6] == ["快照月份", "区域", "组别", "店铺SID", "MSKU", "SKU"]
    assert "365天以上成本" in headers
    assert "raw_json" not in headers
    assert sheet["A2"].value == "2026-08"
    assert sheet["G2"].value == 1.25
