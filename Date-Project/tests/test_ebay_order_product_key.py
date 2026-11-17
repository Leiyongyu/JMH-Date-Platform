from collections import defaultdict

import pytest

from backend.services.ebay_order_product_key import product_key, product_sku, is_used_sku
from backend.services import ebay_replenishment_v2_service as service
from backend.repositories import ebay_replenishment_v2_repository as repo


@pytest.mark.parametrize('sku', ['AMZ', 'AMZ-001', 'amz123-001', '1PC-BMW', '12PC001', '001pc-BMW'])
def test_excludes_amz_and_digit_pc_prefix(sku):
    assert product_key('德国', sku) is None


@pytest.mark.parametrize('sku', ['PC-BMW', 'BMW-2PC-0001', 'XAMZ-1', '2PCS-BMW-X', '123-BMW'])
def test_prefix_filter_is_anchored(sku):
    # 2PCS也以数字PC开头，后续字符不改变前缀规则。
    assert (product_key('德国', sku) is None) == sku.startswith('2PC')


@pytest.mark.parametrize('suffix', ['', '-YXR', '-RXY', '-yxr'])
def test_used_variants_share_product_within_site(suffix):
    assert product_key(' 德国 ', ' BMW-30003-0001' + suffix + ' ') == ('德国', 'BMW-30003-0001')
    assert product_key('美国', 'BMW-30003-0001' + suffix) == ('美国', 'BMW-30003-0001')
    assert is_used_sku('BMW-30003-0001' + suffix) == bool(suffix)


@pytest.mark.parametrize('sku', ['BMW-YXR-0001', 'BMW-0001-YXR-A', 'BMW-0001-RXY2', 'BMW-0001-X', 'BMW-0001YXR'])
def test_only_exact_delimited_final_used_marker_is_removed(sku):
    assert product_sku(sku) == sku


def test_grouping_combines_quantities_not_ratios_and_preserves_sites():
    rows = [('德国', 'BMW-30003-0001', 10, 1), ('德国', 'BMW-30003-0001-YXR', 2, 1),
            ('德国', 'BMW-30003-0001-RXY', 3, 0), ('美国', 'BMW-30003-0001-YXR', 4, 1),
            ('德国', '2PC-BMW-30003-0001', 99, 90), ('德国', 'AMZ-30003', 80, 70)]
    grouped = defaultdict(lambda: [0, 0])
    for site, sku, sales, returns in rows:
        key = product_key(site, sku)
        if key is not None:
            grouped[key][0] += sales
            grouped[key][1] += returns
    assert dict(grouped) == {('德国', 'BMW-30003-0001'): [15, 2], ('美国', 'BMW-30003-0001'): [4, 1]}


def test_search_normalizes_used_variant_before_inner_and_outer_filters():
    assert service._filters(' 德国 ', ' bmw-30003-0001-YXR ', None)[1] == ['德国', '%BMW-30003-0001%']
    assert service._source_filters('德国', 'BMW-30003-0001-RXY', 'recent')[1] == ['德国', '%BMW-30003-0001%']


def test_excluded_sku_cannot_load_forecast(monkeypatch):
    monkeypatch.setattr(repo, 'db_connection', lambda: pytest.fail('Excluded SKU must not query orders'))
    assert repo.forecast_sku_sales('德国', '2PC-BMW') is None
    assert repo.forecast_sku_sales('德国', 'AMZ001') is None
