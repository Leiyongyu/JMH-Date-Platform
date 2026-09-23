from copy import deepcopy
from datetime import timedelta

import pytest

from backend.services import home_product_nature_service as s
from test_home_product_nature import NOW, row, source


@pytest.mark.parametrize('ages,expected,age', [
    ([10, 91], 'OLD', 91), ([91, 10], 'OLD', 91),
    ([1, 90], 'NEW', 90), ([None, 10], 'NEW', 10),
    ([None, None], 'OLD', None), ([-1, 100], 'OLD', 100),
])
def test_eu_earliest_boundary_and_raw_date_preservation(ages, expected, age):
    data = source([{**row(age=value), 'store_id': str(i)} for i, value in enumerate(ages)])
    original = deepcopy(data)
    report, facts = s.build('amz', data, NOW)
    eu = next(x for x in report['segments'] if x['segment_key'] == 'EU')
    assert eu['sku_count'] == 1 and eu['counts'][expected] == 1
    assert eu['counts']['CONFLICT'] == 0
    for fact in facts:
        assert fact['nature'] == fact['segment_nature'] == expected
        assert fact['age_days'] == age and fact['threshold_days'] == 90
        assert fact['first_listing_date'] == ((NOW - timedelta(days=age)).date().isoformat() if age is not None else None)
        assert fact['date_merge_policy'] == 'EU_REGION_SKU_MIN_VALID_OPEN_DATE'
    assert [f['variants'][0]['age_days'] for f in facts] == ages
    assert data == original


def test_eu_minimum_crosses_owner_but_counting_and_us_stay_independent():
    rows = [row(age=10), {**row(store='EU-甲店-UK', age=100), 'store_id': '2', 'site': 'UK'},
            {**row(store='US1-甲店-US', age=5), 'store_id': '3', 'site': 'US'},
            row('ABC-2', age=20)]
    report, facts = s.build('amz', source(rows), NOW)
    assert [f['age_days'] for f in facts] == [100, 100, 5, 20]
    assert [f['principal_name'] for f in facts] == ['甲', '吴清栩', '甲', '甲']
    eu = next(x for x in report['segments'] if x['segment_key'] == 'EU')
    assert eu['sku_count'] == 3  # Owner+SKU population is intentionally unchanged.
    assert eu['counts'] == dict(NEW=1, OLD=2, UNKNOWN=0, CONFLICT=0)
    assert report['reconciliation']['owner_differences'] == []


def test_eu_invalid_dates_ignore_display_fallback_and_use_other_valid_listing():
    rows = [{**row(age=None), 'first_listing_date': 'invalid', 'open_date_display': '2020-01-01'},
            {**row(age=10), 'store_id': '2'}]
    report, facts = s.build('amz', source(rows), NOW)
    assert report['counts']['NEW'] == 1
    assert facts[0]['age_days'] == 10
    assert facts[0]['variants'][0]['reason'] == 'INVALID_OPEN_DATE'
