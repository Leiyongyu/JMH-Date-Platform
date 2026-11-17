from decimal import Decimal

import pytest

from backend.services.ebay_replenishment_hierarchy import aggregate_item, node, validate_parent


@pytest.mark.parametrize('level,site,group', [
    ('bad', None, None), ('product', '', None), ('sku', '英国', ''),
    ('site', None, 'FRD-70327'), ('product', '英国', 'FRD-70327'),
])
def test_invalid_parent_is_rejected(level, site, group):
    with pytest.raises(ValueError):
        validate_parent(level, site, group)


def test_ratios_use_weighted_totals_and_means_use_three_periods():
    row = dict(site='英国', group_key='FRD-70327', sku_count=2,
               raw_sales_qty='100', raw_paid_amount='1000', raw_gross_profit_amount='210',
               raw_return_qty='8', raw_quality_return_qty='3', raw_unclassified_return_qty='1',
               overseas_sellable_quantity='20', forecast_sales_quantity='33.34')
    for i, sales in enumerate(('10', '30', '60')):
        row.update({f'm{i}_sales_qty': sales, f'm{i}_gross_profit_amount': '70',
                    f'm{i}_return_qty': '2', f'm{i}_return_amount': '10'})
    item = aggregate_item(row, {'months': ['a', 'b', 'c']}, 'product')
    assert Decimal(item['profit_rate']) == Decimal('.21')
    assert Decimal(item['return_rate']) == Decimal('.08')
    assert Decimal(item['forecast_sales_quantity']) == Decimal(100) / 3
    assert Decimal(item['sell_through_ratio']) == (Decimal(100) / 3) / 20
    assert item['has_children'] and item['node_label'] == 'FRD-70327'
    assert item['quality_return_summary']['quality_return_rate'] == '0.03'


def test_zero_denominator_and_unknown_values_are_not_zero_rates():
    row = dict(site='德国', group_key='', sku_count=1, raw_paid_amount='0',
               raw_gross_profit_amount='1', raw_sales_qty='0', raw_return_qty='0')
    item = aggregate_item(row, {}, 'site')
    assert item['profit_rate'] is None and item['return_rate'] is None
    assert item['forecast_sales_quantity'] is None


def test_node_identity_separates_sites_levels_and_preserves_full_sku():
    uk = node({'site': '英国', 'sku': 'FRD-70327-0076'}, 'sku', 'FRD-70327')
    de = node({'site': '德国', 'sku': 'FRD-70327-0076'}, 'sku', 'FRD-70327')
    assert uk['node_id'] != de['node_id']
    assert uk['node_label'] == 'FRD-70327-0076' and not uk['has_children']
