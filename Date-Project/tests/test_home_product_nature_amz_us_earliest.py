from copy import deepcopy
from datetime import timedelta

import pytest

from backend.services import home_product_nature_service as s
from test_home_product_nature import NOW, row, source


def us(age, store_id='1', sku='ABC-1', **extra):
    return {**row(sku, store='US1-甲店-US', age=age), 'store_id': store_id, 'site': 'US', **extra}


@pytest.mark.parametrize('ages,expected,age', [
    ([10, 61], 'OLD', 61), ([61, 10], 'OLD', 61),
    ([1, 60], 'NEW', 60), ([10, None], 'NEW', 10),
    ([None, None], 'OLD', None), ([-1, 61], 'OLD', 61),
])
def test_us_earliest_valid_date_and_boundary(ages, expected, age):
    data = source([us(value, str(i)) for i, value in enumerate(ages)])
    original = deepcopy(data)
    report, facts = s.build('amz', data, NOW)
    segment = next(x for x in report['segments'] if x['segment_key'] == 'US')
    assert segment['sku_count'] == 1
    assert segment['counts'][expected] == 1
    assert segment['counts']['CONFLICT'] == 0
    assert report['counts'][expected] == 1
    for fact in facts:
        assert fact['nature'] == fact['segment_nature'] == fact['group_nature'] == expected
        assert fact['age_days'] == age
        assert fact['first_listing_date'] == ((NOW - timedelta(days=age)).date().isoformat() if age is not None else None)
        assert fact['date_merge_policy'] == 'US_REGION_SKU_MIN_VALID_OPEN_DATE'
    assert data == original
    assert [f['variants'][0]['age_days'] for f in facts] == ages


def test_us_same_fact_variants_merge_without_losing_raw_dates():
    report, facts = s.build('amz', source([us(10), us(100)]), NOW)
    assert len(facts) == 1 and len(facts[0]['variants']) == 2
    assert facts[0]['age_days'] == 100
    assert report['counts']['OLD'] == 1
    assert 'CROSS_LISTING_NATURE_CONFLICT' not in facts[0]['reasons']


def test_us_date_scope_crosses_sites_and_owners_but_not_eu_or_other_skus():
    rows = [us(10), us(61, '2', site='CA', store_name='US2-乙店-CA'),
            us(5, '3', sku='ABC-2'), row(age=200), {**row(age=10), 'store_id': '4'}]
    report, facts = s.build('amz', source(rows), NOW)
    us_facts = [f for f in facts if f['segment_key'] == 'US']
    assert [f['age_days'] for f in us_facts] == [61, 61, 5]
    assert [f['principal_name'] for f in us_facts] == ['甲', '乙', '甲']
    eu = next(x for x in report['segments'] if x['segment_key'] == 'EU')
    assert eu['counts']['OLD'] == 1 and eu['counts']['CONFLICT'] == 0
    assert [f['age_days'] for f in facts if f['segment_key'] == 'EU'] == [200, 200]


def test_invalid_date_ignored_when_same_us_sku_has_valid_date():
    report, facts = s.build('amz', source([us(10), us(None, '2', first_listing_date='invalid')]), NOW)
    assert report['counts']['NEW'] == 1
    assert facts[1]['age_days'] == 10
    assert facts[1]['variants'][0]['reason'] == 'INVALID_OPEN_DATE'


def test_version_invalidates_cached_old_us_conflict_report():
    assert s.AMZ_VERSION == 'amz-region-earliest-v6'
