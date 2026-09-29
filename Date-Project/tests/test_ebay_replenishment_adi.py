from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from pymysql.err import ProgrammingError

from backend.repositories import ebay_replenishment_v2_repository as repo
from backend.services import ebay_replenishment_v2_service as service


@pytest.mark.parametrize('days,n,expected', [
    (0, Decimal('92'), '999.000000'),
    (0, None, '999.000000'),
    (7, Decimal('92'), '13.142857'),
    (7, Decimal('60'), '8.571429'),
    (31, Decimal('92'), '2.967742'),
    (2, None, None),
])
def test_adi_uses_saved_training_days_and_zero_day_sentinel(days, n, expected):
    item = service._assemble_items([{'site': '德国', 'sku': 'BMW-001', 'sales_days': days}],
                                   service._complete_months(date(2026, 9, 28)), training_days=n)[0]
    assert item['sales_days'] == days
    assert item['adi'] == expected


def parameter_database(monkeypatch, values=None, error=None):
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql):
            calls.append(sql)
            if error: raise error
        def fetchone(self): return {'numeric_value': values.pop(0)} if values else None
    class Connection:
        def cursor(self): return Cursor()
    @contextmanager
    def connection(): yield Connection()
    monkeypatch.setattr(repo, 'db_connection', connection)
    return calls


def test_training_days_reload_saved_value_each_request(monkeypatch):
    calls = parameter_database(monkeypatch, [Decimal('92'), Decimal('45')])
    assert repo.training_period_days() == Decimal('92')
    assert repo.training_period_days() == Decimal('45')
    assert len(calls) == 2
    assert all("parameter_key='training_days'" in sql for sql in calls)


@pytest.mark.parametrize('value', [None, Decimal('0'), Decimal('-1'), Decimal('1.5')])
def test_missing_or_invalid_training_days_have_no_hardcoded_fallback(monkeypatch, value):
    parameter_database(monkeypatch, [value])
    assert repo.training_period_days() is None


def test_missing_table_leaves_adi_unavailable_but_other_db_errors_surface(monkeypatch):
    parameter_database(monkeypatch, error=ProgrammingError(1146, 'parameter table missing'))
    assert repo.training_period_days() is None
    parameter_database(monkeypatch, error=ProgrammingError(1054, 'unknown column'))
    with pytest.raises(ProgrammingError): repo.training_period_days()
