from datetime import date

import pytest

from backend.services.inventory_report_source_sync_service import _month_scope


def test_month_scope_defaults_to_previous_complete_natural_month():
    assert _month_scope(None, date(2026, 9, 1)) == (
        "2026-08",
        "2026-08-01",
        "2026-08-31",
    )


def test_month_scope_handles_year_boundary():
    assert _month_scope(None, date(2026, 1, 15)) == (
        "2025-12",
        "2025-12-01",
        "2025-12-31",
    )


def test_month_scope_uses_full_explicit_leap_month():
    assert _month_scope("2024-02") == (
        "2024-02",
        "2024-02-01",
        "2024-02-29",
    )


def test_month_scope_rejects_invalid_month():
    with pytest.raises(ValueError, match="YYYY-MM"):
        _month_scope("2026-13")
