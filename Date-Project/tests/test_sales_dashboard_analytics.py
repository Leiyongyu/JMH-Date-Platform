from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.services import sales_dashboard_analytics as analytics
from backend.services import sales_dashboard_service as source

TODAY = date(2026, 10, 16)


def row(month, platform='ebay', group='US', income=100, profit=20, refund=-10, net=90):
    return {'stat_month': month, '_platform': platform, 'group_code': group,
            'platform_income': income, 'platform_expense': -80, 'gross_profit': profit,
            'refund_amount': refund, 'gross_sales': 200, 'net_amount': net, 'total_receipts': net,
            'gross_margin': Decimal('0.99')}


def install(monkeypatch, data):
    conn, cur = MagicMock(), MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    def execute(sql, params):
        p = 'ebay' if source.TABLES['ebay'] in sql else 'amz'
        selected = params[2:]
        cur.fetchall.return_value = [dict(r, amount=r[source.METRICS[p]], net_sales=r[source.METRICS[p]])
            for r in data if r['_platform'] == p and params[0] <= r['stat_month'] <= params[1]
            and (not selected or r['group_code'] in selected)]
    cur.execute.side_effect = execute
    @contextmanager
    def connection():
        yield conn
    monkeypatch.setattr(source, 'db_connection', connection)
    monkeypatch.setattr(analytics, 'db_connection', connection)
    return conn, cur


def report(platform='ebay', start='2026-09', end='2026-09', groups=(), granularity='month'):
    return analytics.analyze(platform, start, end, groups, granularity, TODAY)


def test_company_sums_platform_mapping_and_keeps_equal_group_names_separate(monkeypatch):
    data = [row(m, p, net=90 if p == 'ebay' else 150) for p in ('ebay', 'amz') for m in ('2025-09', '2026-08', '2026-09')]
    conn, cur = install(monkeypatch, data)
    result = report('all')
    metrics = result['metrics']
    assert metrics['net_sales']['summary']['value'] == '240'
    assert metrics['net_sales']['label'] == '净收款'
    assert metrics['platform_income']['summary']['value'] == '200'
    assert metrics['platform_expense']['summary']['value'] == '-160'
    assert metrics['gross_sales']['summary']['value'] == '400'
    assert metrics['gross_margin']['summary']['value'] == '0.2'
    assert {r['name'] for r in result['breakdown']['group']} == {'eBay / US', 'AMZ / US'}
    assert metrics['net_sales']['summary']['mom']['value'] == '0'
    assert cur.execute.call_count == 4
    conn.commit.assert_not_called()
    filtered = report('all', groups=['amz:US'])
    assert filtered['metrics']['net_sales']['summary']['value'] == '150'
    assert list(filtered['raw_details']) == ['amz']


def test_months_and_quarters_compare_adjacent_equal_length_and_prior_year(monkeypatch):
    data = [row(m, profit=10 if m.startswith('2025') else 20) for m in analytics.months_between('2025-01', '2026-09')]
    install(monkeypatch, data)
    result = report(start='2026-07', end='2026-09', granularity='quarter')
    assert result['months'] == ['2026 Q3']
    assert result['comparisons'] == {'current': ['2026-07', '2026-09'], 'mom': ['2026-04', '2026-06'], 'yoy': ['2025-07', '2025-09']}
    profit = result['metrics']['gross_profit']
    assert profit['summary']['value'] == '60'
    assert profit['summary']['yoy']['value'] == '1'
    assert profit['summary']['yoy']['difference'] == '30'
    assert profit['summary']['mom']['value'] == '0'
    assert profit['year_total'] == ['30']
    multi = report(start='2026-04', end='2026-09', granularity='quarter')
    assert multi['comparisons']['mom'] == ['2025-10', '2026-03']
    assert multi['months'] == ['2026 Q2', '2026 Q3']
    assert multi['metrics']['gross_profit']['point_comparisons'][1]['mom']['start'] == '2026-04'
    monthly = report(start='2026-07', end='2026-09')
    assert monthly['comparisons']['mom'] == ['2026-04', '2026-06']
    assert monthly['metrics']['gross_profit']['point_comparisons'][0]['mom']['start'] == '2026-06'


def test_incomplete_period_keeps_amount_but_hides_growth(monkeypatch):
    data = [row(m) for m in ('2025-07', '2025-08', '2025-09', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08')]
    install(monkeypatch, data)
    summary = report(start='2026-07', end='2026-09', granularity='quarter')['metrics']['gross_profit']['summary']
    assert summary['value'] == '40'
    assert summary['missing_months'] == ['2026-09']
    for kind in ('mom', 'yoy'):
        assert summary[kind]['value'] is None
        assert summary[kind]['reason'] == 'incomplete'
        assert summary[kind]['difference'] == '-20'


def test_missing_platform_group_and_field_are_detected(monkeypatch):
    data = [row('2026-09'), row('2026-08'), row('2025-09')]
    install(monkeypatch, data)
    assert report('all')['metrics']['gross_profit']['summary']['mom']['reason'] == 'incomplete'
    assert report(groups=['US', 'DE'])['metrics']['gross_profit']['summary']['mom']['reason'] == 'incomplete'
    data[0]['gross_profit'] = None
    assert report()['metrics']['gross_profit']['summary']['mom']['reason'] == 'missing_current'
    assert report()['metrics']['platform_income']['summary']['mom']['reason'] is None


@pytest.mark.parametrize('base,current,expected,reason', [(-10, 20, '3', None), (-10, -20, '-1', None),
                                                        (0, 20, None, 'zero_baseline'), (None, 20, None, 'missing_baseline')])
def test_negative_zero_and_missing_baselines(monkeypatch, base, current, expected, reason):
    install(monkeypatch, [row('2026-08', profit=base), row('2026-09', profit=current)])
    comparison = report()['metrics']['gross_profit']['summary']['mom']
    assert comparison['value'] == expected
    assert comparison['reason'] == reason


def test_ratios_use_sums_and_change_in_percentage_points_even_zero_baseline(monkeypatch):
    install(monkeypatch, [row('2026-08', profit=0), row('2026-09', profit=25)])
    result = report()['metrics']['gross_margin']['summary']
    assert result['value'] == '0.25'
    assert result['mom']['value'] == '0.25'
    assert result['mom']['unit'] == 'pp'
    assert result['mom']['reason'] is None


def test_current_quarter_not_complete_even_if_rows_uploaded(monkeypatch):
    install(monkeypatch, [row(m) for m in analytics.months_between('2026-07', '2026-12')])
    result = report(start='2026-10', end='2026-10', granularity='quarter')
    assert (result['start'], result['end']) == ('2026-10', '2026-12')
    assert result['metrics']['gross_profit']['summary']['value'] == '60'
    assert result['metrics']['gross_profit']['summary']['mom']['reason'] == 'incomplete'


@pytest.mark.parametrize('args', [('other','2026-01','2026-02',[],'month'), ('all','2026-01','2026-02',['US'],'month'),
    ('ebay','2026-01','2026-02',['amz:US'],'month'), ('ebay','2026-01','2026-02',[],'day'),
    ('ebay','2026-02','2026-01',[],'month'), ('ebay','2000-01','2026-01',[],'month')])
def test_invalid_scope_rejected_before_db(monkeypatch, args):
    db = MagicMock()
    monkeypatch.setattr(analytics, 'db_connection', db)
    with pytest.raises(ValueError):
        analytics.analyze(*args)
    db.assert_not_called()


def test_analysis_http_route_validates_internal_auth_and_forwards_scope(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import deps
    from backend.api.v1.sales_dashboard import router
    monkeypatch.setattr(deps, 'settings', SimpleNamespace(python_internal_api_token='test-only-token'))
    app = FastAPI()
    app.include_router(router)
    call = MagicMock(return_value={'granularity': 'quarter'})
    monkeypatch.setattr(analytics, 'analyze', call)
    params = {'platform': 'all', 'start_month': '2026-07', 'end_month': '2026-09', 'groups_csv': 'ebay:US,amz:US', 'granularity': 'quarter'}
    with TestClient(app) as client:
        assert client.get('/api/v1/finance/sales-dashboard/report', params=params).status_code == 401
        response = client.get('/api/v1/finance/sales-dashboard/report', params=params, headers={'X-Internal-Token':'test-only-token'})
        assert response.status_code == 200
        assert response.json()['data']['granularity'] == 'quarter'
        call.assert_called_once_with('all', '2026-07', '2026-09', ['ebay:US', 'amz:US'], 'quarter')


def test_special_fields_stay_platform_specific_with_signed_shares(monkeypatch):
    data = []
    for p in ('ebay', 'amz'):
        for month in ('2025-09', '2026-08', '2026-09'):
            item = row(month, p)
            item.update({key: Decimal('-10') for key in analytics.SPECIAL_FIELDS[p]})
            item['advertising_fee'] = Decimal('-20') if p == 'ebay' else Decimal('-50')
            if p == 'ebay':
                item['compensation'] = Decimal('5')
            data.append(item)
    _, cur = install(monkeypatch, data)
    result = report('all')
    assert set(result['specials']['ebay']['metrics']) == set(analytics.SPECIAL_FIELDS['ebay'])
    assert set(result['specials']['amz']['metrics']) == set(analytics.SPECIAL_FIELDS['amz'])
    assert 'advertising_fee' not in result['metrics']  # No ambiguous combined advertising KPI.
    ebay, amz = result['specials']['ebay'], result['specials']['amz']
    assert ebay['metrics']['advertising_fee']['label'] == '广告费'
    assert amz['metrics']['advertising_fee']['label'] == '广告和推广费'
    assert ebay['metrics']['advertising_fee']['summary']['value'] == '-20'
    assert amz['metrics']['advertising_fee']['summary']['value'] == '-50'
    assert ebay['metrics']['advertising_fee']['share']['value'] == '-0.1'
    assert ebay['metrics']['compensation']['share']['value'] == '0.025'
    assert ebay['metrics']['compensation']['summary']['value'] == '5'
    assert all(r['name'].startswith('eBay / ') for r in ebay['groups'])
    assert all(s['name'].startswith('AMZ / ') for s in amz['metrics']['advertising_fee']['series'])
    assert cur.execute.call_count == 4  # No per-field/group database queries.


def test_special_quarter_sums_shares_and_missing_denominator(monkeypatch):
    data = []
    for month in analytics.months_between('2026-04', '2026-09'):
        item = row(month, 'amz')
        item.update(commission=-10, shipping_fee=0, advertising_fee=-20)
        data.append(item)
    install(monkeypatch, data)
    values = report('amz', '2026-07', '2026-09', granularity='quarter')['specials']['amz']['metrics']
    assert values['commission']['summary']['value'] == '-30'
    assert values['commission']['share']['value'] == '-0.05'
    assert values['commission']['summary']['mom']['value'] == '0'
    assert values['shipping_fee']['summary']['value'] == '0'
    assert values['shipping_fee']['share']['value'] == '0'
    data[-1]['commission'] = None
    values = report('amz', '2026-07', '2026-09', granularity='quarter')['specials']['amz']['metrics']
    assert values['commission']['summary']['value'] == '-20'
    assert values['commission']['summary']['mom']['reason'] == 'incomplete'
    data[-1]['gross_sales'] = 0
    values = report('amz')['specials']['amz']['metrics']
    assert values['advertising_fee']['share']['value'] is None
    assert values['advertising_fee']['share']['reason'] == 'zero_denominator'


def test_contribution_reconciles_and_zero_baseline_can_contribute_amount(monkeypatch):
    install(monkeypatch, [row('2026-08', profit=0), row('2026-09', profit=30),
                          row('2026-08', 'amz', profit=20), row('2026-09', 'amz', profit=10)])
    result = report('all')['contributions']['gross_profit']['mom']
    for dimension in ('platform', 'group'):
        contribution = result[dimension]
        assert contribution['reconciled'] is True
        assert contribution['total_difference'] == contribution['covered_difference'] == '20'
        assert {r['difference'] for r in contribution['items']} == {'30', '-10'}
        assert contribution['residual'] == '0'
        assert contribution['unavailable'] == []


def test_contribution_includes_disappeared_groups_without_fabricating_zero(monkeypatch):
    install(monkeypatch, [row('2026-08', profit=10), row('2026-09', profit=20), row('2026-08', group='OLD', profit=50), row('2026-09', group='NEW', profit=60)])
    value = report()['contributions']['gross_profit']['mom']['group']
    assert [r['name'] for r in value['items']] == ['eBay / US']
    assert {r['name'] for r in value['unavailable']} == {'eBay / NEW', 'eBay / OLD'}
    assert value['covered_difference'] == '10'
    assert value['total_difference'] == '20'
    assert value['residual'] == '10'
    assert value['reconciled'] is False
    old = next(r for r in value['unavailable'] if r['name'] == 'eBay / OLD')
    assert old['current'] is None and old['baseline'] == '50'


def test_incomplete_contribution_never_masquerades_as_complete_attribution(monkeypatch):
    install(monkeypatch, [row(m) for m in ('2026-04', '2026-05', '2026-06', '2026-07', '2026-08')])
    value = report(start='2026-07', end='2026-09', granularity='quarter')['contributions']['gross_profit']['mom']['platform']
    assert value['items'] == []
    assert value['unavailable'][0]['reason'] == 'incomplete'
    assert value['reconciled'] is False


def test_prior_year_only_group_does_not_pollute_month_on_month_contribution(monkeypatch):
    install(monkeypatch, [row('2026-08'), row('2026-09'), row('2025-09'), row('2025-09', group='OLD_YEAR')])
    value = report()['contributions']['gross_profit']
    assert value['mom']['group']['reconciled'] is True
    assert value['mom']['group']['unavailable'] == []
    assert [r['name'] for r in value['yoy']['group']['unavailable']] == ['eBay / OLD_YEAR']
