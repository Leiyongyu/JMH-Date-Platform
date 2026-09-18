from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.parsers.performance_common import normalize_text, parse_brand_code_from_sku
from backend.repositories import ebay_owner_sku_repository as repo
from backend.services.inventory_report_etl_service import _ebay_assignment
from backend.services.performance_service import UNASSIGNED
from backend.services.owner_sku_common import include_configured_owners, is_pc_sku


def summarize(rows: list[dict], rules: dict) -> dict:
    # Reuse performance matching except CL: this dashboard uses its monthly rule.
    # Do not supply a warehouse SKU map: listing MSKU is the original sales SKU.
    brands = {}
    for (_, rule_type, key), principal in rules.items():
        if rule_type != 'EBAY_BRAND':
            continue
        brand = normalize_text(key).upper()
        if brand in brands and brands[brand] != principal:
            raise ValueError('eBay品牌负责人配置冲突，请检查当月规则')
        brands[brand] = principal
    owners = defaultdict(set)
    missing_rows = 0
    excluded_pc_rows = 0
    for row in rows:
        sku = normalize_text(row.get('msku')).upper()
        if is_pc_sku(sku):
            excluded_pc_rows += 1
            continue
        if not sku:
            missing_rows += 1
            continue
        if parse_brand_code_from_sku(sku) == 'CL':
            # Dashboard-only exception removal; shared reports remain unchanged.
            principal = brands.get('CL', UNASSIGNED)
        else:
            principal, _ = _ebay_assignment(sku, brands)
        # One full MSKU per owner, regardless of how many shops list it.
        owners[principal].add(sku)
    items = sorted([{'principal_name': name, 'sku_count': len(keys), 'unassigned': name == UNASSIGNED}
                    for name, keys in owners.items()], key=lambda item: (-item['sku_count'], item['principal_name']))
    return {'items': items, 'total': sum(item['sku_count'] for item in items),
            'owner_count': sum(not item['unassigned'] for item in items),
            'unassigned_count': len(owners.get(UNASSIGNED, ())), 'missing_sku_rows': missing_rows,
            'excluded_pc_rows': excluded_pc_rows}


def get_owner_sku_counts() -> dict:
    month = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')
    source = repo.load_source(month)
    result = {'platform': 'ebay', 'rule_month': month, 'source_api': '/basicOpen/multiplatform/ebay/list',
              'dedup_key': ['principal_name', 'msku'], 'listing_status': 1,
              'items': [], 'total': None, 'warnings': []}
    sync = source['sync']
    if sync and sync['status'] != 'SUCCESS':
        return {**result, 'state': 'SOURCE_NOT_READY', 'message':
                'eBay刊登正在同步或最近一次同步未成功，请同步成功后刷新统计。'}
    if not any(key[1] == 'EBAY_BRAND' for key in source['rules']):
        return {**result, 'state': 'MISSING_RULES', 'message': f'缺少{month}的eBay品牌负责人规则，请先导入。'}
    rows = source['rows']
    result.update(summarize(rows, source['rules']))
    include_configured_owners(result, (
        principal for key, principal in source['rules'].items() if key[1] == 'EBAY_BRAND'
    ))
    times = [row['sync_time'] for row in rows if row.get('sync_time')]
    result['source_updated_at'] = max(times).isoformat(sep=' ') if times else None
    result['source_rows'] = len(rows)
    result['state'] = 'READY' if rows else 'EMPTY'
    result['message'] = '' if rows else '当前没有listing_status=1的eBay在售刊登。'
    if not sync:
        result['warnings'].append('未找到eBay刊登同步记录，请确认最近一次同步完整。')
    if result['missing_sku_rows']:
        result['warnings'].append(f"{result['missing_sku_rows']}条记录缺少有效MSKU，未计入统计。")
    return result
