from contextlib import contextmanager
from decimal import Decimal

import pytest

from backend.repositories import ebay_replenishment_v2_repository as repo
from backend.services import ebay_replenishment_v2_service as service


@pytest.mark.parametrize('site,days', [('德国', 67), ('英国', 72), ('美国', 60), ('法国', None)])
def test_unconfigured_rows_use_site_default_in_both_replenishment_formulas(site, days):
    result = service._replenishment_quantities(
        site=site, sku='BMW-1-2', average_monthly_sales=Decimal(30), product_level='A',
        inventory_total=Decimal(10), lead_time_days={},
        formula_configs={'A': {'safety_coefficient': Decimal(1), 'suggest_coefficient': Decimal(2)}})
    assert result == ((str(days), str(days * 2 - 10)) if days else (None, None))


@pytest.mark.parametrize('site,manual,expected', [
    ('德国', None, 67), ('英国', None, 72), ('美国', None, 60),
    ('德国', 0, 0), ('英国', 85, 85), ('美国', 12, 12), ('法国', None, 0),
])
def test_saved_manual_days_override_default_but_null_restores_it(monkeypatch, site, manual, expected):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql): assert sql.lstrip().startswith('SELECT')
        def fetchall(self): return [{
            'site': site, 'sku': 'BMW-1-2', 'chengdu_warehouse_to_warehouse_days': 4,
            'chengdu_qc_outbound_days': 3, 'overseas_transit_to_listing_days': manual,
        }]

    class Connection:
        def cursor(self): return Cursor()

    @contextmanager
    def connection(): yield Connection()

    monkeypatch.setattr(repo, 'db_connection', connection)
    assert repo.lead_time_days_by_sku() == {(site, 'BMW-1-2'): Decimal(expected + 7)}


def test_manual_zero_total_is_not_replaced_with_default():
    assert service._replenishment_quantities(
        site='德国', sku='BMW-1-2', average_monthly_sales=Decimal(30), product_level='A',
        inventory_total=Decimal(10), lead_time_days={('德国', 'BMW-1-2'): Decimal(0)},
        formula_configs={'A': {'safety_coefficient': Decimal(1), 'suggest_coefficient': Decimal(2)}}
    ) == ('0', '0')
