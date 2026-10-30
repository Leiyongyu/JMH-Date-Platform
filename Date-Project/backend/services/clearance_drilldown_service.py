"""Read-only clearance dimensions: Chinese shops, sites and monthly brand owners."""
from datetime import datetime, timedelta
import re

from backend.parsers.performance_common import normalize_text, parse_brand_code_from_sku
from backend.repositories import clearance_repository as repo
from backend.repositories import inventory_report_etl_repository as owners
from backend.services.inventory_report_etl_service import _ebay_assignment, _ebay_rule_map, _resolve_ebay_sku, _amazon_assignment, _amazon_rule_maps
from backend.services.clearance_metrics import FIELDS, compare, total_metrics


GROUPS = {'EBAY-1', 'EU', 'US1', 'US2', 'US2-MJ', 'US1-ZXY'}


def _shop_identity(row):
    shared = str(row.get('sid') or '0').strip() in {'', '0'}
    raw = normalize_text(row.get('warehouse_name') if shared else row.get('store_name'))
    if raw and raw != '0':
        # Remove only known structural parts; never merge by a partial Chinese
        # substring (names may legitimately contain numbers or hyphens).
        name = re.sub(r'^(?:AMZ-)?(?:EU|US[123](?:-MJ|-ZXY)?)-', '', raw, flags=re.I)
        name = re.sub(r'-(?:US|CA|MX|UK|GB|DE|FR|IT|ES|NL|BE|PL|SE|IE|AU|JP)$', '', name, flags=re.I)
        if shared:
            name = re.sub(r'(?:欧洲仓|北美仓|共享仓|海外仓|中转仓|FBA仓)$', '', name, flags=re.I)
        if name.strip():
            return 'STORE:' + name.strip(), name.strip()
    # Missing names cannot be guessed from another store or the group total.
    label = '未匹配中文店铺名' + (f" [SID:{row.get('sid')}]" if not shared else ' [共享仓]')
    return 'UNMATCHED:' + label, label


def _site(warehouse):
    code = normalize_text(warehouse).upper()
    return {'USEA': 'US', 'USWE': 'US', 'US': 'US', 'UK': 'UK', 'GB': 'UK',
            'DE': 'DE', 'CZ': 'DE'}.get(code, '未识别仓库：' + (code or '未知'))


def _compare(rows, month, previous, identity, *, previous_available=None):
    return compare(rows, month, identity, previous_available=previous_available)


def list_dimensions(month: str, group_code: str, site_code: str | None = None, *, dimension=None):
    if group_code not in GROUPS:
        raise ValueError('不支持的滞销清货组别')
    if site_code is not None and group_code != 'EBAY-1':
        raise ValueError('仅 eBay 支持站点筛选')
    if group_code == 'EBAY-1' and site_code is None and dimension != 'OWNER':
        return repo.list_site_dimensions(month)
    previous = (datetime.strptime(month, '%Y-%m') - timedelta(days=1)).strftime('%Y-%m')
    source = repo.drilldown_source_rows(month, group_code)
    warnings = []
    if group_code != 'EBAY-1' and dimension != 'OWNER':
        items = _compare(source, month, previous, _shop_identity)
        dimension = 'STORE'
    else:
        # A site's preceding month may have no stock even though the month
        # exists elsewhere; preserve the same zero/null convention as sites.
        previous_available = any(row['pull_month'] == previous for row in source)
        filtered = [row for row in source if site_code is None or _site(row.get('warehouse_code')) == site_code]
        rules, sku_maps = {}, {}
        platform = 'ebay' if group_code == 'EBAY-1' else 'amazon'
        for rule_month in sorted({row['pull_month'] for row in filtered}):
            raw_rules = owners.owner_rules(rule_month, platform)
            rules[rule_month] = _ebay_rule_map(raw_rules) if platform == 'ebay' else _amazon_rule_maps(raw_rules)
            sku_maps[rule_month] = owners.ebay_product_sku_map(rule_month) if platform == 'ebay' else {}
            if not raw_rules:
                warnings.append(f'{rule_month} 缺少 {platform} 负责人规则；除固定归属外计入未分配，不回退其他月份。')
        prepared = []
        for row in filtered:
            rule_month = row['pull_month']
            sku = row.get('sku') or row.get('source_product_sku')
            if platform == 'ebay':
                owner, _ = _ebay_assignment(sku, rules[rule_month], sku_maps[rule_month])
                brand = parse_brand_code_from_sku(_resolve_ebay_sku(sku, sku_maps[rule_month]))
            else:
                owner, _, _ = _amazon_assignment(normalize_text(row.get('store_name') or row.get('warehouse_name')),
                                                 normalize_text(sku), rules[rule_month])
                brand = parse_brand_code_from_sku(sku)
            prepared.append({**row, 'principal_name': owner or '未分配', 'brand_code': brand})
        items = _compare(prepared, month, previous,
                         lambda row: ('OWNER:' + row['principal_name'], row['principal_name']),
                         previous_available=previous_available)
        dimension = 'OWNER'
    return {'pull_month': month, 'group_code': group_code, 'dimension': dimension,
            'site_code': site_code, 'items': items, 'total': len(items), 'warnings': warnings,
            'site_options': sorted({_site(row.get('warehouse_code')) for row in source}) if dimension == 'OWNER' and group_code == 'EBAY-1' else [],
            'summary': total_metrics(filtered if dimension == 'OWNER' else source, month)}
