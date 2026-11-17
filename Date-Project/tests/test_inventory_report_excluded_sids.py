from decimal import Decimal

from backend.services import inventory_report_etl_service as service


EXPECTED_EXCLUDED_SIDS = {
    "12518",
    "12519",
    "12598",
    "12599",
    "12600",
    "12601",
    "12602",
    "12603",
    "12604",
    "12605",
    "12662",
    "12642",
    "12643",
    "12644",
}


def test_monthly_inventory_permanently_excludes_exact_sid_set():
    assert service.INVENTORY_EXCLUDED_SIDS == EXPECTED_EXCLUDED_SIDS


def test_clean_fba_excludes_all_configured_shop_sids_and_reports_count():
    excluded_rows = [
        {
            "id": index,
            "sync_batch_id": "batch-1",
            "sid": sid,
            "msku": f"EXCLUDED-{sid}",
            "end_count": "10",
            "end_total_amount": "100",
        }
        for index, sid in enumerate(sorted(EXPECTED_EXCLUDED_SIDS), start=1)
    ]
    allowed_row = {
        "id": 99,
        "sync_batch_id": "batch-1",
        "sid": "99999",
        "msku": "ALLOWED-1",
        "end_count": "7",
        "end_total_amount": "70",
    }

    rows, stats = service._clean_fba(
        "2026-07",
        [*excluded_rows, allowed_row],
        {"99999": "US2-正常店铺-US"},
        service._amazon_rule_maps([]),
    )

    assert stats["fba_excluded_shop_rows"] == len(EXPECTED_EXCLUDED_SIDS)
    assert len(rows) == 1
    assert rows[0]["sid"] == "99999"
    assert rows[0]["msku"] == "ALLOWED-1"


def test_clean_amz_sales_excludes_all_configured_shop_sids_and_reports_count():
    excluded_rows = [
        {
            "id": index,
            "sid": sid,
            "msku": f"EXCLUDED-{sid}",
            "amount": "100",
            "volume": "1",
        }
        for index, sid in enumerate(sorted(EXPECTED_EXCLUDED_SIDS), start=1)
    ]
    allowed_row = {
        "id": 99,
        "sid": "99999",
        "msku": "ALLOWED-1",
        "amount": "200",
        "volume": "2",
    }

    rows, stats = service._clean_amz_sales(
        "2026-07",
        [*excluded_rows, allowed_row],
        {"99999": "US1-正常店铺-US"},
        service._amazon_rule_maps([]),
    )

    assert stats["amz_sales_excluded_shop_rows"] == len(EXPECTED_EXCLUDED_SIDS)
    assert len(rows) == 1
    assert rows[0]["sid"] == "99999"
    assert rows[0]["amount"] == Decimal("200")
    assert rows[0]["volume"] == service.Decimal("2")
