from datetime import date
from backend.services import ebay_replenishment_v2_service as service


def test_retired_adi_and_sales_days_are_not_returned():
    item = service._assemble_items([{'site': '德国', 'sku': 'BMW-001', 'sales_days': 7}],
                                   service.rolling_periods(date(2026, 9, 28)))[0]
    assert 'sales_days' not in item
    assert 'adi' not in item
