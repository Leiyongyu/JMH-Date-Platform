"""Performance-owner product nature; no external API calls or business-table writes."""
import calendar
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.parsers.performance_common import normalize_text, parse_brand_code_from_sku
from backend.repositories import home_product_nature_repository as repo
from backend.services import amz_owner_sku_service, ebay_owner_sku_service
from backend.services.inventory_report_etl_service import _amazon_group, _ebay_assignment
from backend.services.owner_sku_common import is_pc_sku
from backend.services.performance_service import UNASSIGNED, _amazon_principal, _amazon_store_rules, _store_segment

VERSION = 'ebay-site-no-amz-v3'
AMZ_VERSION = 'amz-region-earliest-v6'
NATURES = ('NEW', 'OLD', 'UNKNOWN', 'CONFLICT')
UNKNOWN_GROUP = 'UNKNOWN_GROUP'


def rule_version(platform):
    return AMZ_VERSION if platform == 'amz' else VERSION


def is_ebay_amz_sku(value):
    return normalize_text(value).upper().startswith('AMZ')


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai'))


def month_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', value):
        raise ValueError('月份必须为YYYY-MM')
    return value


def shift(month, delta):
    y, m = map(int, month_value(month).split('-'))
    y, m = divmod(y*12+m-1+delta, 12)
    return f'{y:04d}-{m+1:02d}'


def listing_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def amz_open_date(value, site):
    """Parse raw site-local calendar date, without timezone/day shifting.

    The raw API has DD/MM/YYYY for the verified European marketplaces, while
    US/CA/MX/NL use ISO. Never guess slash order for an unknown marketplace.
    """
    parsed = listing_date(value)
    if parsed is not None:
        return parsed
    european = {'UK','GB','DE','FR','IT','ES','NL','BE','PL','SE','IE',
                '英国','德国','法国','意大利','西班牙','荷兰','比利时','波兰','瑞典','爱尔兰'}
    if normalize_text(site).upper() not in european:
        return None
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s|T|$)', normalize_text(value))
    if not match:
        return None
    try:
        day, month, year = map(int,match.groups())
        return date(year,month,day)
    except ValueError:
        return None


def classify(value, today, threshold):
    day = listing_date(value)
    if day is None:
        return 'UNKNOWN', None, None, 'MISSING_LISTING_DATE'
    age = (today-day).days
    if threshold is None:
        return 'UNKNOWN', day.isoformat(), age, 'UNKNOWN_GROUP_THRESHOLD'
    # Same signed-age comparison as replenishment; future dates are visible in
    # the diagnostics instead of quietly changing the established rule.
    return ('NEW' if age <= threshold else 'OLD'), day.isoformat(), age, ('FUTURE_LISTING_DATE' if age < 0 else None)


def collapse(values):
    values = set(values)
    return next(iter(values)) if len(values) == 1 else 'CONFLICT'


def percentage(n, total):
    return str((Decimal(n)*100/total).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if total else None


def metric(values):
    counts = Counter(values)
    total = sum(counts.values())
    return dict(sku_count=total, counts={n: counts[n] for n in NATURES},
                percentages={n: percentage(counts[n], total) for n in NATURES}, denominator=total)


def rule_context(rules):
    stores = _amazon_store_rules(rules)
    brands, store_keys = {}, defaultdict(list)
    for key, owner in rules.items():
        group, kind, match = key
        if kind == 'EBAY_BRAND':
            brand = normalize_text(match).upper()
            if brand in brands and brands[brand] != owner:
                raise ValueError('eBay品牌负责人配置冲突')
            brands[brand] = owner
        if kind == 'STORE' and group != 'EU':
            store_keys[match].append(key)
    return stores, brands, store_keys


def assignment(platform, row, rules, context):
    stores, brands, store_keys = context
    if platform == 'ebay':
        sku = normalize_text(row.get('msku')).upper()
        owner, source = _ebay_assignment(sku, brands)  # original MSKU, never warehouse sku_map
        brand = parse_brand_code_from_sku(sku)
        key = f'FIXED:{brand}' if source == 'EBAY_FIXED_BRAND' else f'EBAY_BRAND:{brand}'
        return owner, 'EBAY-1', source, key
    owner, _, missing = _amazon_principal(row, rules, stores)
    store = normalize_text(row.get('store_name'))
    group = _amazon_group(store)
    if missing:
        return owner, UNKNOWN_GROUP, 'MISSING_STORE', ''
    local = normalize_text(row.get('local_sku')).upper()
    if store.startswith('EU-'):
        if store.upper().endswith('-UK'):
            return owner, 'EU', 'AMAZON_UK_FIXED', 'FIXED:EU-UK'
        segments = [s for s in local.split('-') if s]
        kind = 'OTH_CODE' if local.startswith('OTH-') else 'BRAND'
        key = (segments[1] if len(segments)>1 else '') if kind == 'OTH_CODE' else (segments[0] if segments else '')
        return owner, 'EU', ('UNMATCHED' if owner == UNASSIGNED else f'AMAZON_{kind}'), f'EU:{kind}:{key}'
    key = _store_segment(store)
    alias = key == '重庆茁凯' and key not in stores and '邱存帅' in stores
    if alias:
        key = '邱存帅'
    matches = store_keys.get(key, [])
    if group is None:
        groups = {r[0] for r in matches}
        if len(groups)>1:
            raise ValueError('AMZ无组别店铺匹配到多个规则组，请核对当月规则')
        group = next(iter(groups), UNKNOWN_GROUP)
    source = 'UNMATCHED' if owner == UNASSIGNED else 'AMAZON_STORE_ALIAS' if alias else 'AMAZON_STORE'
    return owner, group, source, '|'.join(':'.join(r) for r in sorted(matches)) or f'STORE:{key}'


def build(platform, source, instant):
    """Pure, testable aggregation. Preserve raw variants for same-grain conflicts."""
    month = instant.strftime('%Y-%m')
    rules, rows = source['rules'], source['rows']
    base = dict(platform=platform, stat_month=month, rule_month=month, rule_version=VERSION,
                sku_count=None, captured_at=instant.replace(tzinfo=None).isoformat(sep=' ',timespec='seconds'),
                live=True, groups=[], owners=[], warnings=[])
    base['rule_version'] = rule_version(platform)
    base['period_kind'] = 'MONTHLY' if platform == 'amz' else 'LIVE'
    base['storage_policy'] = 'OVERWRITE_CURRENT_MONTH' if platform == 'amz' else 'MONTH_END_FREEZE'
    if not source['ready']:
        return dict(base, state='SOURCE_NOT_READY', message='缺少成功的完整刊登源，请先检查源同步'), []
    if not rules or (platform == 'ebay' and not any(k[1]=='EBAY_BRAND' for k in rules)):
        return dict(base, state='MISSING_RULES', message=f'缺少{month}当月负责人规则'), []
    context = rule_context(rules)
    facts = {}
    audit = Counter()
    for row in rows:
        sku = normalize_text(row.get('seller_sku' if platform == 'amz' else 'msku')).upper()
        if platform=='ebay' and is_ebay_amz_sku(sku):
            audit['excluded_amz_rows'] += 1
            continue
        if is_pc_sku(sku) or (platform=='amz' and is_pc_sku(row.get('local_sku'))):
            audit['excluded_pc_rows'] += 1
            continue
        if not sku:
            audit['missing_sku_rows'] += 1
            continue
        owner, group, owner_source, owner_rule_key = assignment(platform,row,rules,context)
        regions = set(row.get('replenishment_regions') or []) & {'US','EU'}
        region = next(iter(regions)) if len(regions)==1 else 'UNKNOWN_REGION'
        segment = (normalize_text(row.get('site')) or 'UNKNOWN_SITE') if platform=='ebay' else region
        threshold = 60 if platform=='ebay' or region=='US' else 90 if region=='EU' else None
        raw_date = row.get('first_listing_date')
        parsed_date = amz_open_date(raw_date,row.get('site') or row.get('marketplace')) if platform=='amz' else raw_date
        nature, day, age, reason = classify(parsed_date, instant.date(), threshold)
        if platform=='amz' and reason=='UNKNOWN_GROUP_THRESHOLD':
            reason = 'UNKNOWN_REGION_THRESHOLD'
        if platform=='amz' and reason=='MISSING_LISTING_DATE' and normalize_text(raw_date):
            reason = 'INVALID_OPEN_DATE'
        # AMZ follows replenishment's CASE WHEN valid date and age<=limit
        # THEN NEW ELSE OLD. Preserve the diagnostic, but not UNKNOWN counts.
        # An unmapped region still has no applicable threshold; do not guess it.
        if platform=='amz' and threshold is not None and parsed_date is None:
            nature = 'OLD'
            audit['missing_or_invalid_date_as_old_rows'] += 1
        audit['included_rows'] += 1
        audit['date_matched_rows' if day else 'date_missing_rows'] += 1
        if group == UNKNOWN_GROUP:
            audit['unknown_group_rows'] += 1
        if reason:
            audit[reason] += 1
        store_id = normalize_text(row.get('store_id') or row.get('sid'))
        site = normalize_text(row.get('site'))
        identity = (platform,group,owner,store_id,site,sku)
        variant = dict(local_sku=normalize_text(row.get('local_sku')), first_listing_date=day,
                       age_days=age,threshold_days=threshold,nature=nature,reason=reason,
                       owner_match_source=owner_source,owner_rule_key=owner_rule_key)
        if platform=='amz':
            variant['open_date_raw'] = normalize_text(raw_date)
            variant['replenishment_regions'] = sorted(regions)
        if identity not in facts:
            facts[identity] = dict(platform=platform,group_code=group,principal_name=owner,owner_key=repo.digest(owner),
                store_id=store_id,store_name=normalize_text(row.get('store_name')),site=site,sku=sku,
                segment_key=segment,
                seller_sku=sku if platform=='amz' else None,msku=sku if platform=='ebay' else None,
                snapshot_month=month,rule_month=month,rule_version=rule_version(platform),fact_key=repo.digest(identity),
                nature_source='ods_lingxing_amz_listing_latest.open_date' if platform=='amz'
                    else 'ebay_product_listing.MIN(listing_start_time) BY site_name,msku',
                source_updated_at=str(row.get('sync_time') or ''),variants=[])
        fact = facts[identity]
        if variant not in fact['variants']:
            fact['variants'].append(variant)
        fact['source_updated_at'] = max(fact['source_updated_at'],str(row.get('sync_time') or ''))
    facts = list(facts.values())
    # Take the earliest valid open_date per region and complete seller SKU,
    # across eligible stores/owners. Never borrow dates from another region.
    # Retain row-level variants for audit and keep owner counting unchanged.
    region_first_dates = {}
    if platform == 'amz':
        for fact in facts:
            if fact['segment_key'] not in {'US', 'EU'}:
                continue
            key = (fact['segment_key'], fact['sku'])
            for variant in fact['variants']:
                day = variant['first_listing_date']
                if day is not None:
                    region_first_dates[key] = min(region_first_dates.get(key, day), day)
    pkeys, gkeys, skeys = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in facts:
        r['nature'] = collapse(v['nature'] for v in r['variants'])
        # Top-level convenience fields only if variants agree; conflicting raw
        # values remain in variants, never pick an arbitrary date/local SKU.
        for field in ('local_sku','first_listing_date','age_days','threshold_days','owner_match_source','owner_rule_key'):
            values = {v[field] for v in r['variants']}
            r[field] = next(iter(values)) if len(values)==1 else None
        if platform == 'amz' and r['segment_key'] in {'US', 'EU'}:
            day = region_first_dates.get((r['segment_key'], r['sku']))
            threshold = 60 if r['segment_key'] == 'US' else 90
            nature, day, age, _ = classify(day, instant.date(), threshold)
            r.update(nature=nature if day is not None else 'OLD',
                     first_listing_date=day, age_days=age, threshold_days=threshold,
                     date_merge_policy=f"{r['segment_key']}_REGION_SKU_MIN_VALID_OPEN_DATE")
        r['reasons'] = sorted({v['reason'] for v in r['variants'] if v['reason']})
        pkeys[(r['owner_key'],r['sku'])].add(r['nature'])
        gkeys[(r['group_code'],r['owner_key'],r['sku'])].add(r['nature'])
        # eBay site+SKU is the business identity. Owner matching is independent
        # and must not cause different sites to conflict with each other.
        segment_owner = r['owner_key'] if platform=='amz' else ''
        skeys[(r['segment_key'],segment_owner,r['sku'])].add(r['nature'])
    pn = {k:collapse(v) for k,v in pkeys.items()}
    gn = {k:collapse(v) for k,v in gkeys.items()}
    sn = {k:collapse(v) for k,v in skeys.items()}
    segment_values = defaultdict(list)
    for (segment,_,_),nature in sn.items():
        segment_values[segment].append(nature)
    if platform=='amz':
        for region in ('US','EU'):
            segment_values.setdefault(region,[])
    groups, owners = defaultdict(list), defaultdict(list)
    names = {r['owner_key']:r['principal_name'] for r in facts}
    for (g,o,_), n in gn.items():
        groups[g].append(n); owners[(g,o)].append(n)
    for r in facts:
        r['platform_nature'] = pn[(r['owner_key'],r['sku'])]
        r['group_nature'] = gn[(r['group_code'],r['owner_key'],r['sku'])]
        r['segment_nature'] = sn[(r['segment_key'],r['owner_key'] if platform=='amz' else '',r['sku'])]
        if 'CONFLICT' in (r['nature'],r['platform_nature'],r['group_nature']):
            r['reasons'].append('CROSS_LISTING_NATURE_CONFLICT')
    # Add zero owners only at their rule-defined groups, never fabricate facts.
    for (g,kind,_), name in rules.items():
        if name in {UNASSIGNED,'注销'} or (platform=='ebay' and kind!='EBAY_BRAND') or (platform=='amz' and g=='EU' and kind=='STORE'):
            continue
        g = 'EBAY-1' if platform=='ebay' else g or UNKNOWN_GROUP
        names[repo.digest(name)] = name
        owners.setdefault((g,repo.digest(name)),[]); groups.setdefault(g,[])
    legacy = (amz_owner_sku_service if platform=='amz' else ebay_owner_sku_service).summarize(rows,rules)
    comparable = ebay_owner_sku_service.summarize(
        [row for row in rows if not is_ebay_amz_sku(row.get('msku'))], rules) if platform=='ebay' else legacy
    comparable_owners = {r['principal_name']:r['sku_count'] for r in comparable['items']}
    previous = {r['principal_name']:r['sku_count'] for r in legacy['items']}
    unified = Counter()
    for o,_ in pn:
        unified[names[o]] += 1
    differences = [dict(principal_name=o,legacy_count=previous.get(o,0),performance_count=unified[o],
                        delta=unified[o]-previous.get(o,0)) for o in sorted(set(previous)|set(unified))
                   if unified[o]!=previous.get(o,0)]
    if platform=='amz' and differences:
        raise ValueError('AMZ平台去重数与现首页负责人统计不一致，停止发布')
    changed = []
    if platform=='ebay':
        for r in facts:
            if parse_brand_code_from_sku(r['sku'])=='CL':
                changed.append(dict(sku=r['sku'],legacy_owner=context[1].get('CL',UNASSIGNED),performance_owner=r['principal_name']))
        changed = list({(r['sku'],r['legacy_owner'],r['performance_owner']):r for r in changed}.values())
        # Population exclusions are intentional. Only validate attribution on
        # the same eligible population; retain raw legacy totals for old cards.
        attribution_differences = {o for o in set(comparable_owners)|set(unified)
                                  if comparable_owners.get(o,0)!=unified[o]}
        if attribution_differences - {x[k] for x in changed for k in ('legacy_owner','performance_owner')}:
            raise ValueError('eBay归属差异超出CL范围，停止发布并核对')
    result = dict(base, **metric(pn.values()), state='READY' if facts else 'EMPTY',
        source_rows=len(rows), detail_rows=len(facts), group_attributed_count=len(gn),
        platform_deduplicated_count=len(pn), cross_group_duplicate_count=len(gn)-len(pn),
        source_updated_at=max((r['source_updated_at'] for r in facts),default=None), source_batch=source['sync'],
        groups=[dict(group_code=g,**metric(values)) for g,values in sorted(groups.items())],
        owners=[dict(group_code=g,owner_key=o,principal_name=names[o],**metric(values)) for (g,o),values in sorted(owners.items())],
        segment_type='REGION' if platform=='amz' else 'SITE',
        segment_grain='region_owner_seller_sku' if platform=='amz' else 'site_msku',
        segments=[dict(segment_key=key,segment_label=({'US':'美国','EU':'欧洲','UNKNOWN_REGION':'区域未匹配'}.get(key,key) if platform=='amz' else ('站点未匹配' if key=='UNKNOWN_SITE' else key)),**metric(values)) for key,values in sorted(segment_values.items())],
        audit=dict(audit), reconciliation=dict(legacy_total=legacy['total'],performance_total=len(pn),
        owner_differences=differences,cl_skus=changed,legacy_card_changed=False,
        comparable_total=comparable['total'],excluded_amz_sku_count=legacy['total']-comparable['total']),
        batch_id=str(uuid4()), source_fingerprint=repo.digest([rule_version(platform),instant.date(),rows,sorted(rules.items()),source['sync']]))
    if changed:
        result['warnings'].append('CL按绩效固定归属；旧首页卡片保持当月规则口径，负责人差异见reconciliation')
    if audit['excluded_amz_rows']:
        result['warnings'].append('本新老品报表排除AMZ开头MSKU；旧负责人卡片未修改，数量差异见reconciliation')
    if audit['date_missing_rows']:
        result['warnings'].append('AMZ已匹配区域的缺失或无效刊登日期按老品计入，原始原因保留在明细' if platform=='amz'
                                  else 'eBay缺刊登日期显示UNKNOWN')
    return result, facts


def segment_owner_summary(report, rows, segment):
    """Owner counts use the exact saved region/site nature and chart population."""
    unavailable = dict(state='NO_SEGMENT_DETAIL', items=[], totals=None,
                       message='该月缺少区域/站点明细快照，不能用当前数据补算')
    if not isinstance(report.get('segments'), list):
        return unavailable
    if any(not r.get('segment_key') or r.get('segment_nature') not in NATURES for r in rows):
        return unavailable
    selected = [r for r in rows if r['segment_key'] == segment]
    expected = next((r for r in report['segments'] if r['segment_key'] == segment), metric([]))
    keys, names, sku_owners = defaultdict(set), {}, defaultdict(set)
    for r in selected:
        keys[(r['owner_key'], r['sku'])].add(r['segment_nature'])
        names[r['owner_key']] = r['principal_name']
        sku_owners[r['sku']].add(r['owner_key'])
    # eBay chart counts site+SKU, so ambiguous ownership cannot be attributed twice.
    if report['platform'] == 'ebay' and any(len(owners) > 1 for owners in sku_owners.values()):
        return dict(state='OWNER_RECONCILIATION_FAILED', items=[], totals=None,
                    message='该快照同站点SKU存在多负责人，不能重复归入个人，请核对快照')
    owner_values = defaultdict(list)
    for (owner, _), values in keys.items():
        owner_values[owner].append(collapse(values))
    totals = metric(n for values in owner_values.values() for n in values)
    if totals['sku_count'] != expected['sku_count'] or totals['counts'] != expected['counts']:
        return dict(state='OWNER_RECONCILIATION_FAILED', items=[], totals=None,
                    message='负责人明细与图表快照数量不一致，请刷新报表后重试')
    items = [dict(owner_key=owner, principal_name=names[owner], **metric(values))
             for owner, values in owner_values.items()]
    items.sort(key=lambda r: (-r['sku_count'], r['principal_name'], r['owner_key']))
    return dict(state='READY', segment_key=segment, items=items, totals=totals,
                reconciled=True, detail_grain='segment_owner_sku')


def validate(platform, month=None):
    if platform not in {'amz','ebay'}:
        raise ValueError('平台只允许amz或ebay')
    month = month_value(month) if month is not None else now().strftime('%Y-%m')
    if month > now().strftime('%Y-%m'):
        raise ValueError('不能查询未来月份')
    return month


def _load(conn, platform, month, instant):
    if month != instant.strftime('%Y-%m'):
        history = repo.read_month_report(conn,platform,month)
        return dict(history,live=False) if history else dict(state='NO_SNAPSHOT',platform=platform,stat_month=month,sku_count=None)
    kind = 'MONTHLY' if platform == 'amz' else 'LIVE'
    token = repo.source_token(conn,platform,month,instant.date(),rule_version(platform))
    cached = repo.read_report(conn,platform,month,kind)
    if cached and cached.get('cache_token') == token:
        return cached
    report, facts = build(platform, repo.load_source(conn,platform,month), instant)
    if report['state'] not in {'READY','EMPTY'}:
        return report
    report['cache_token'] = token
    if now().strftime('%Y-%m') != month:
        raise ValueError('统计期间月份变化，请重试')
    repo.publish(conn,report,facts,kind)
    return report


def get_report(platform, month=None, view='summary', **filters):
    month = validate(platform,month)
    instant = now()
    live = month==instant.strftime('%Y-%m')
    if view not in {'summary','groups','owners','details'}:
        raise ValueError('不支持的报表视图')
    page, size = filters.get('page',1), filters.get('page_size',50)
    if not isinstance(page,int) or not 1<=page<=1000000 or not isinstance(size,int) or not 1<=size<=100:
        raise ValueError('页码需为正整数，每页最多100条')
    if filters.get('nature') is not None and filters['nature'] not in NATURES:
        raise ValueError('性质必须为NEW/OLD/UNKNOWN/CONFLICT')
    owner = filters.get('owner_key')
    if owner is not None and not re.fullmatch(r'[0-9a-f]{64}',owner):
        raise ValueError('负责人键无效')
    for field in ('group_code','sku'):
        if filters.get(field) is not None and len(filters[field])>(64 if field=='group_code' else 512):
            raise ValueError('筛选值过长')
    segment = filters.get('segment_key')
    if segment is not None and (not isinstance(segment, str) or not segment.strip() or len(segment)>64):
        raise ValueError('区域/站点参数无效')
    if segment is not None and (view != 'owners' or filters.get('group_code') is not None):
        raise ValueError('区域/站点仅用于负责人明细，不能同时按业务组筛选')
    if segment is not None and platform == 'amz' and segment not in {'US','EU','UNKNOWN_REGION'}:
        raise ValueError('AMZ区域参数无效')
    batch = filters.get('batch_id')
    if batch is not None and (not isinstance(batch,str) or not re.fullmatch(r'[0-9a-fA-F-]{36}',batch)):
        raise ValueError('快照批次参数无效')
    with repo.transaction(write=live) as conn:
        report = _load(conn,platform,month,instant)
        if report['state'] not in {'READY','EMPTY'}:
            return report
        group = filters.get('group_code')
        if group is not None and group not in {r['group_code'] for r in report['groups']}:
            raise ValueError('组别不在该月份报表中')
        meta = {k:report[k] for k in ('platform','stat_month','rule_month','rule_version','state','captured_at','batch_id','live')}
        meta['storage_policy'] = report.get('storage_policy','MONTH_END_FREEZE')
        if view == 'owners' and segment is not None:
            if batch is not None and batch != report['batch_id']:
                return dict(meta, state='SNAPSHOT_CHANGED', items=[], totals=None,
                            message='当月报表已更新，请关闭弹窗并刷新图表后查看负责人明细')
            kind = report.get('period_kind', 'LIVE' if live else 'FROZEN')
            rows = repo.segment_owner_rows(conn,platform,month,kind,report['batch_id'])
            return {**meta, **segment_owner_summary(report,rows,segment)}
        if view=='details':
            kind = report.get('period_kind', 'LIVE' if live else 'FROZEN')
            return dict(meta, **repo.details(conn,platform,month,kind,**filters))
        if view in {'groups','owners'}:
            return dict(meta,items=[r for r in report[view] if group is None or r['group_code']==group])
        previous = repo.read_month_report(conn,platform,shift(month,-1))
        reason = 'NO_SNAPSHOT' if not previous else 'VERSION_MISMATCH' if previous['rule_version']!=report['rule_version'] else None
        current_pct = report['percentages']['NEW']
        prev_pct = previous['percentages']['NEW'] if previous else None
        if not reason and (current_pct is None or prev_pct is None):
            reason = 'EMPTY_DENOMINATOR'
        return dict(report, new_share_change_pp=None if reason else str(Decimal(current_pct)-Decimal(prev_pct)), comparison_reason=reason)


def get_history(platform, start_month=None, end_month=None, include_current=False):
    validate(platform)
    instant = now(); current = instant.strftime('%Y-%m')
    end = validate(platform,end_month) if end_month is not None else current
    start = validate(platform,start_month) if start_month is not None else shift(end,-11)
    if start > end or shift(start,11) < end:
        raise ValueError('起止月份须有序，最多查询连续12个月（含首尾）')
    live = include_current and end == current
    with repo.transaction(write=live) as conn:
        reports = {r['stat_month']:r for r in repo.history(conn,platform,end,start)}
        if live:
            # Current observation is explicitly provisional, never a fabricated
            # historical snapshot. eBay still writes LIVE, not FROZEN.
            reports[current] = _load(conn,platform,current,instant)
    items = []
    for m in (shift(start,i) for i in range(12)):
        if m > end:
            break
        if m not in reports:
            items.append(dict(stat_month=m,state='NO_SNAPSHOT',sku_count=None))
        else:
            item = {k:reports[m].get(k) for k in ('stat_month','state','sku_count','counts','percentages','rule_version','captured_at','batch_id','message','segment_type','segment_grain','segments')}
            item['provisional'] = m==current and (platform=='amz' or live)
            items.append(item)
    return dict(platform=platform,start_month=start,end_month=end,items=items)


def compare(platform, base_month, target_month, scope='PLATFORM', group_code=None):
    base_month=validate(platform,base_month); target_month=validate(platform,target_month)
    if scope not in {'PLATFORM','GROUP','OWNER'}:
        raise ValueError('比较级别只允许PLATFORM/GROUP/OWNER')
    # Read saved monthly data only; never reconstruct a past month from the latest source.
    with repo.transaction() as conn:
        a=repo.read_month_report(conn,platform,base_month); b=repo.read_month_report(conn,platform,target_month)
    reason = 'NO_SNAPSHOT' if not a or not b else 'VERSION_MISMATCH' if a['rule_version']!=b['rule_version'] else None
    if reason:
        return dict(state=reason,base_month=base_month,target_month=target_month,items=[])
    def index(r):
        rows = [r] if scope=='PLATFORM' else r['groups' if scope=='GROUP' else 'owners']
        return {(i.get('group_code',''),i.get('owner_key','')):i for i in rows if not group_code or i.get('group_code')==group_code}
    left,right=index(a),index(b); items=[]
    for key in sorted(left.keys()|right.keys()):
        x,y=left.get(key),right.get(key)
        # Missing groups/owners are explicit additions/removals, not missing snapshots.
        xc=x['counts'] if x else {n:0 for n in NATURES}; yc=y['counts'] if y else {n:0 for n in NATURES}
        items.append(dict(group_code=key[0],owner_key=key[1],principal_name=(y or x).get('principal_name'),
            base=x,target=y,delta_sku_count=(y['sku_count'] if y else 0)-(x['sku_count'] if x else 0),
            delta_counts={n:yc[n]-xc[n] for n in NATURES},
            delta_percentage_points={n: str(Decimal(y['percentages'][n])-Decimal(x['percentages'][n]))
                if x and y and x['percentages'][n] is not None and y['percentages'][n] is not None else None for n in NATURES}))
    return dict(state='READY',base_month=base_month,target_month=target_month,scope=scope,items=items,
                base_provisional=platform=='amz' and base_month==now().strftime('%Y-%m'),
                target_provisional=platform=='amz' and target_month==now().strftime('%Y-%m'))


def capture_monthly():
    instant=now(); month=instant.strftime('%Y-%m')
    if instant.day != calendar.monthrange(instant.year,instant.month)[1]:
        raise ValueError('新老品历史仅允许北京时间月末采集，不补造或提前冻结历史')
    with repo.transaction(write=True) as conn:
        # AMZ current month is replaceable. eBay remains first-success frozen;
        # a repeat call must not reread its source or overwrite its history.
        existing_ebay = repo.read_report(conn,'ebay',month,'FROZEN')
        prepared=[build('amz',repo.load_source(conn,'amz',month),instant)]
        if existing_ebay is None:
            prepared.append(build('ebay',repo.load_source(conn,'ebay',month),instant))
        else:
            prepared.append((existing_ebay,None))
        if any(r['state'] not in {'READY','EMPTY'} for r,_ in prepared):
            raise ValueError('两平台刊登源和当月规则必须全部就绪，未写入任何历史')
        if now().strftime('%Y-%m') != month:
            raise ValueError('采集期间跨月，取消整个批次')
        batch=str(uuid4())
        for report,facts in prepared:
            if facts is None:
                continue
            kind = repo.stored_kind(report['platform'])
            report.update(batch_id=batch,live=False,period_kind=kind)
            repo.publish(conn,report,facts,kind)
        # Keep the old inventory card's existing attribution intact (CL monthly
        # exception included), while publishing both reports in one transaction.
        from backend.services.home_inventory_service import SNAPSHOT_TABLE, VERSION as SKU_VERSION
        platforms={r['platform']:dict(total=r['reconciliation']['legacy_total'],source_updated_at=r['source_updated_at'],warnings=r['warnings']) for r,_ in prepared}
        old=dict(stat_month=month,rule_version=SKU_VERSION,total=sum(v['total'] for v in platforms.values()),
                 platforms=platforms,captured_at=prepared[0][0]['captured_at'],nature_batch_id=batch)
        with conn.cursor() as cur:
            cur.execute(f'''INSERT INTO {SNAPSHOT_TABLE}
                (stat_month,rule_version,sku_count,amz_sku_count,ebay_sku_count,captured_at,payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE rule_version=VALUES(rule_version),
                sku_count=VALUES(sku_count),amz_sku_count=VALUES(amz_sku_count),ebay_sku_count=VALUES(ebay_sku_count),
                captured_at=VALUES(captured_at),payload_json=VALUES(payload_json)''',
                (month,SKU_VERSION,old['total'],platforms['amz']['total'],platforms['ebay']['total'],old['captured_at'],repo.encode(old)))
        if now().strftime('%Y-%m') != month:
            raise ValueError('发布期间跨月，回滚整个批次')
        return dict(stat_month=month,total=sum(r['sku_count'] for r,_ in prepared),legacy_total=old['total'],
                    captured_at=old['captured_at'],batch_id=batch,already_frozen=False,
                    amz_storage_policy='OVERWRITE_CURRENT_MONTH',ebay_already_frozen=existing_ebay is not None)
