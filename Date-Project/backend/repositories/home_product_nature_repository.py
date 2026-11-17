"""New report tables only. Source reads share a repeatable-read snapshot.

Live materialization makes filtered details database-paginated; it never changes
the active-listing populations or recalculates a frozen month.
"""
import hashlib
import json
from contextlib import contextmanager

from backend.config import settings
from backend.database import db_connection
from backend.parsers.performance_common import normalize_principal, normalize_text

SUMMARY = 'dws_home_product_nature_monthly'
DETAIL = 'dwd_home_product_nature_sku_monthly'


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


@contextmanager
def transaction(*, write=False):
    with db_connection() as conn, conn.cursor() as cur:
        locked = False
        try:
            if write:
                cur.execute("SELECT GET_LOCK('jmh:home-product-nature',10) acquired")
                if cur.fetchone()['acquired'] != 1:
                    raise ValueError('新老品报表正在生成，请稍后重试')
                locked = True
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT' + ('' if write else ', READ ONLY'))
            yield conn
            if write:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise
        finally:
            if locked:
                cur.execute("SELECT RELEASE_LOCK('jmh:home-product-nature')")


def amz_shops_sql(database):
    # Same store-prefix -> warehouse -> enabled region config as replenishment.
    # LEFT JOIN preserves the full active population instead of filtering it.
    return f'''SELECT sl.sid,sl.store_name,sl.country_code,
        GROUP_CONCAT(DISTINCT fc.region_group ORDER BY fc.region_group) nature_regions
        FROM `{database}`.shop_list sl
        LEFT JOIN `{database}`.warehouse wh
          ON wh.name=CONCAT('CTUAMZ-',SUBSTRING_INDEX(TRIM(COALESCE(sl.store_name,'')),'-',1),'中转仓')
        LEFT JOIN `{database}`.amz_replenishment_formula_config fc
          ON fc.enabled=1 AND fc.region_group IN ('US','EU') AND FIND_IN_SET(wh.name,fc.marketplaces)>0
        WHERE sl.platform_code='10001'
        GROUP BY sl.sid,sl.store_name,sl.country_code ORDER BY sl.sid,sl.store_name,sl.country_code'''


def load_source(conn, platform, month):
    database = (settings.shop_source_database.strip() or 'jmh_data_platform').replace('`', '``')
    with conn.cursor() as cur:
        cur.execute('''SELECT group_code,rule_type,match_key,principal_name
            FROM dwd_performance_owner_rule WHERE platform=%s AND stat_month=%s
            ORDER BY group_code,rule_type,match_key,principal_name''',
                    ('amazon' if platform == 'amz' else 'ebay', month))
        rules = {}
        for r in cur.fetchall():
            key = (normalize_text(r['group_code']).upper(), normalize_text(r['rule_type']).upper(),
                   normalize_text(r['match_key']))
            owner = normalize_principal(r['principal_name'])
            if key in rules and rules[key] != owner:
                raise ValueError('当月负责人规则存在冲突，请检查规则表')
            rules[key] = owner
        if platform == 'amz':
            cur.execute("SELECT sync_batch_id,pulled_at,published_at,row_count FROM ods_lingxing_amz_listing_state WHERE id=1")
            sync = cur.fetchone()
            cur.execute(amz_shops_sql(database))
            shops = {}
            for shop in cur.fetchall():
                key = str(shop['sid'])
                if key in shops and shops[key] != shop:
                    raise ValueError('AMZ店铺SID存在不同名称或站点，请检查店铺表')
                shops[key] = shop
            cur.execute('''SELECT sid,seller_sku,local_sku,marketplace,open_date,
                pulled_at AS sync_time FROM ods_lingxing_amz_listing_latest
                WHERE status=1 AND is_delete=0 ORDER BY id''')
            rows = list(cur.fetchall())
            for r in rows:
                shop = shops.get(str(r['sid']), {})
                r.update(store_name=shop.get('store_name'), site=shop.get('country_code') or r['marketplace'],
                         store_id=str(r['sid']), first_listing_date=r['open_date'],
                         replenishment_regions=(shop.get('nature_regions') or '').split(','))
            ready = bool(sync)
        else:
            cur.execute(f'''SELECT id,status,start_time,end_time FROM `{database}`.data_sync_log
                WHERE sync_type='ebay_listing' AND status<>'SKIPPED' ORDER BY id DESC LIMIT 1''')
            sync = cur.fetchone()
            # Same exact site_name+full MSKU MIN as first_listing_date_by_sku,
            # including non-active listings when finding the first date.
            cur.execute(f'''SELECT msku,site_name,MIN(listing_start_time) first_date
                FROM `{database}`.ebay_product_listing
                WHERE msku IS NOT NULL AND TRIM(msku)<>''
                  AND site_name IS NOT NULL AND TRIM(site_name)<>'' AND listing_start_time IS NOT NULL
                GROUP BY site_name,msku''')
            dates = {}
            for r in cur.fetchall():
                key = (normalize_text(r['site_name']), normalize_text(r['msku']).upper())
                day = r['first_date']
                if key not in dates or day < dates[key]:
                    dates[key] = day
            cur.execute(f'''SELECT store_id,store_name,msku,local_sku,site_name AS site,sync_time
                FROM `{database}`.ebay_product_listing WHERE listing_status=1 ORDER BY id''')
            rows = list(cur.fetchall())
            for r in rows:
                r['first_listing_date'] = dates.get((normalize_text(r['site']), normalize_text(r['msku']).upper()))
            ready = bool(sync and sync['status'] == 'SUCCESS')
    return dict(rows=rows, rules=rules, sync=sync, ready=ready)


def source_token(conn, platform, month, today, version):
    """Small freshness queries on every request, no stale TTL on changed rules.

    AMZ raw writes are atomic and tracked by the published state row. eBay
    also includes table timestamps/counts because its older sync is not atomic.
    """
    database = (settings.shop_source_database.strip() or 'jmh_data_platform').replace('`', '``')
    parts = [platform, month, today, version]
    with conn.cursor() as cur:
        cur.execute('''SELECT group_code,rule_type,match_key,principal_name FROM dwd_performance_owner_rule
            WHERE platform=%s AND stat_month=%s ORDER BY group_code,rule_type,match_key,principal_name''',
            ('amazon' if platform=='amz' else 'ebay',month))
        parts.append(cur.fetchall())
        if platform=='amz':
            cur.execute('SELECT * FROM ods_lingxing_amz_listing_state WHERE id=1')
            parts.append(cur.fetchone())
            cur.execute(amz_shops_sql(database))
            parts.append(cur.fetchall())
        else:
            cur.execute(f'''SELECT id,status,start_time,end_time FROM `{database}`.data_sync_log
                WHERE sync_type='ebay_listing' AND status<>'SKIPPED' ORDER BY id DESC LIMIT 1''')
            parts.append(cur.fetchone())
            cur.execute(f'''SELECT COUNT(*) n,MAX(sync_time) synced,MAX(updated_at) updated
                FROM `{database}`.ebay_product_listing''')
            parts.append(cur.fetchone())
    return digest(parts)


def read_report(conn, platform, month, kind):
    with conn.cursor() as cur:
        cur.execute(f'''SELECT payload_json FROM {SUMMARY}
            WHERE stat_month=%s AND platform=%s AND period_kind=%s AND scope='PLATFORM' ''', (month, platform, kind))
        row = cur.fetchone()
        return decode(row['payload_json']) if row else None


def stored_kind(platform):
    return 'MONTHLY' if platform == 'amz' else 'FROZEN'


def read_month_report(conn, platform, month):
    report = read_report(conn, platform, month, stored_kind(platform))
    # Preserve any v1 AMZ frozen history without rewriting it from today's source.
    if report is None and platform == 'amz':
        report = read_report(conn, platform, month, 'FROZEN')
    return report


def publish(conn, report, facts, kind):
    """Caller owns the lock and transaction; failures roll back both tables."""
    platform, month = report['platform'], report['stat_month']
    if kind == 'MONTHLY' and platform != 'amz':
        raise ValueError('按月覆盖仅适用于AMZ，eBay历史保持冻结')
    if kind == 'FROZEN' and read_report(conn, platform, month, kind):
        raise ValueError('历史月份已冻结，不允许覆盖')
    with conn.cursor() as cur:
        for table in (DETAIL, SUMMARY):
            if kind == 'MONTHLY':
                # Exactly one AMZ dataset per month; replace v1 data only for
                # this same month, never delete any earlier month or eBay rows.
                cur.execute(f'DELETE FROM {table} WHERE stat_month=%s AND platform=%s', (month, platform))
            else:
                cur.execute(f'DELETE FROM {table} WHERE stat_month=%s AND platform=%s AND period_kind=%s', (month, platform, kind))
            if kind == 'LIVE':
                cur.execute(f"DELETE FROM {table} WHERE platform=%s AND period_kind='LIVE' AND stat_month<>%s", (platform, month))
        values = []
        for scope, items in [('PLATFORM', [report]), ('GROUP', report['groups']), ('OWNER', report['owners'])]:
            for item in items:
                counts = item['counts']
                values.append((month, platform, kind, scope, item.get('group_code', ''), item.get('owner_key', ''),
                    report['rule_version'], month, item['sku_count'], *[counts[n] for n in ('NEW','OLD','UNKNOWN','CONFLICT')],
                    report['batch_id'], report['source_fingerprint'], report['captured_at'], encode(item)))
        cur.executemany(f'''INSERT INTO {SUMMARY} (stat_month,platform,period_kind,scope,group_code,owner_key,
            rule_version,rule_month,sku_count,new_count,old_count,unknown_count,conflict_count,sync_batch_id,
            source_fingerprint,captured_at,payload_json) VALUES ({','.join(['%s']*17)})''', values)
        for start in range(0, len(facts), 500):
            cur.executemany(f'''INSERT INTO {DETAIL} (stat_month,platform,period_kind,fact_key,group_code,
                owner_key,principal_name,store_id,site,sku,nature,platform_nature,group_nature,rule_version,
                sync_batch_id,payload_json) VALUES ({','.join(['%s']*16)})''', [
                (month,platform,kind,r['fact_key'],r['group_code'],r['owner_key'],r['principal_name'],r['store_id'],
                 r['site'],r['sku'],r['nature'],r['platform_nature'],r['group_nature'],report['rule_version'],
                 report['batch_id'],encode(r)) for r in facts[start:start+500]])


def details(conn, platform, month, kind, *, group_code=None, owner_key=None, nature=None, sku=None, page=1, page_size=50):
    clauses = ['stat_month=%s', 'platform=%s', 'period_kind=%s']
    args = [month, platform, kind]
    for column, value in [('group_code',group_code), ('owner_key',owner_key)]:
        if value is not None:
            clauses.append(f'{column}=%s'); args.append(value)
    if nature:
        # Filter the same dedup nature used by the chosen summary level; retain
        # original site-level nature in each payload for conflict inspection.
        column = 'group_nature' if group_code else 'platform_nature'
        clauses.append(f'{column}=%s'); args.append(nature)
    if sku:
        clauses.append('LOCATE(%s,sku)>0'); args.append(sku.upper())
    where = ' AND '.join(clauses)
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) total FROM {DETAIL} WHERE {where}', args)
        total = cur.fetchone()['total']
        cur.execute(f'''SELECT payload_json FROM {DETAIL} WHERE {where}
            ORDER BY group_code,owner_key,fact_key LIMIT %s OFFSET %s''', (*args,page_size,(page-1)*page_size))
        return dict(items=[decode(r['payload_json']) for r in cur.fetchall()], total=total, page=page, page_size=page_size,
                    total_grain='store_site_sku_rows')


def segment_owner_rows(conn, platform, month, kind, batch_id):
    """Read compact saved dimensions only; never use current source/owner rules."""
    with conn.cursor() as cur:
        cur.execute(f'''SELECT owner_key,principal_name,sku,
            JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.segment_key')) segment_key,
            JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.segment_nature')) segment_nature
            FROM {DETAIL} WHERE stat_month=%s AND platform=%s AND period_kind=%s
              AND sync_batch_id=%s''', (month, platform, kind, batch_id))
        return list(cur.fetchall())


def history(conn, platform, end_month, start_month):
    with conn.cursor() as cur:
        # MONTHLY for AMZ, FROZEN for eBay. Include older v1 AMZ frozen months.
        cur.execute(f'''SELECT payload_json FROM {SUMMARY} WHERE platform=%s AND period_kind IN (%s,'FROZEN')
            AND scope='PLATFORM' AND stat_month BETWEEN %s AND %s
            ORDER BY stat_month, CASE WHEN period_kind='MONTHLY' THEN 1 ELSE 0 END''',
            (platform,stored_kind(platform),start_month,end_month))
        return [decode(r['payload_json']) for r in cur.fetchall()]
