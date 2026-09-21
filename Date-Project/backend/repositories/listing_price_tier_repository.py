"""平台币种报表独立仓库；不更新任何ODS、店铺或汇率源表。"""
import json
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.config import settings
from backend.database import db_connection
from backend.services import listing_price_tier_service as engine

HEAD = 'dws_listing_cny_price_report'
DETAIL = 'dws_listing_cny_price_tier'
USD_HEAD = 'dws_ebay_usd_price_report'
USD_DETAIL = 'dws_ebay_usd_price_tier'


class ReportBusy(ValueError): pass


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def check_platform(platform):
    if platform not in ('amz','ebay'): raise ValueError('不支持的平台')


def begin(connection,cursor):
    connection.rollback()
    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    connection.begin()


def context(cursor,platform):
    month = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')
    rate_field = 'rate_org' if platform == 'ebay' else 'my_rate'
    cursor.execute(f'SELECT currency_code,{rate_field} FROM dim_lingxing_currency_month WHERE rate_month=%s ORDER BY currency_code',(month,))
    rates = {r['currency_code'].strip().upper(): str(r[rate_field]) if r[rate_field] is not None else None for r in cursor.fetchall()}
    shops = {}
    if platform == 'ebay':
        cursor.execute('SELECT seller_user_id,seller_account,row_count,sync_batch_id,pulled_at FROM ods_ebay_store_listing_state ORDER BY seller_user_id')
        state = list(cursor.fetchall())
    else:
        cursor.execute('SELECT sync_batch_id,row_count,pulled_at,published_at FROM ods_lingxing_amz_listing_state WHERE id=1')
        state = cursor.fetchone()
        db = settings.shop_source_database.replace('`','``')
        cursor.execute(f"SELECT sid,store_name,country_code FROM `{db}`.shop_list WHERE platform_code='10001' ORDER BY sid")
        for row in cursor.fetchall():
            sid = str(row['sid'])
            if sid in shops and shops[sid] != row: raise ValueError('AMZ店铺sid对应多个不同店铺，请先检查店铺数据')
            shops[sid] = row
    return decode(dumps(dict(rate_month=month,rates=rates,source=state,shops=shops)))


def source(cursor,platform,ctx):
    if not ctx['source']: raise ValueError('尚无完整原始刊登数据，请先完成商品同步')
    if platform == 'ebay':
        cursor.execute('''SELECT seller_user_id,seller_account,item_id,sku,site,current_price,currency,normalized_json,sync_batch_id
                          FROM ods_ebay_store_listing_latest''')
        rows = list(cursor.fetchall())
        expected = {s['seller_user_id']:s for s in ctx['source']}
        counts = dict.fromkeys(expected,0)
        for row in rows:
            state = expected.get(row['seller_user_id'])
            if not state or row['sync_batch_id']!=state['sync_batch_id'] or row['seller_account']!=state['seller_account']:
                raise ValueError('eBay原始数据与发布批次不一致，保留旧报表')
            counts[row['seller_user_id']] += 1
        if any(counts[k]!=v['row_count'] for k,v in expected.items()): raise ValueError('eBay原始数据行数不完整，保留旧报表')
        empty = [dict(store_key=s['seller_user_id'],store_name=s['seller_account']) for s in ctx['source']]
        return engine.ebay_candidates(rows),empty,len(rows)
    cursor.execute('SELECT sync_batch_id,COUNT(*) n FROM ods_lingxing_amz_listing_latest GROUP BY sync_batch_id')
    batches = cursor.fetchall()
    expected = ctx['source']
    if (expected['row_count'] and (len(batches)!=1 or batches[0]['sync_batch_id']!=expected['sync_batch_id'] or batches[0]['n']!=expected['row_count'])) or (not expected['row_count'] and batches):
        raise ValueError('AMZ原始数据数量或批次不一致，保留旧报表')
    cursor.execute('''SELECT sid,marketplace,seller_sku,currency_code,landed_price,status,is_delete
                      FROM ods_lingxing_amz_listing_latest WHERE status=1 AND is_delete=0''')
    rows = list(cursor.fetchall())
    return engine.amz_candidates(rows,ctx['shops']),[],len(rows)


def rebuild(platform):
    check_platform(platform)
    head_table, detail_table = (USD_HEAD, USD_DETAIL) if platform == 'ebay' else (HEAD, DETAIL)
    currency = 'USD' if platform == 'ebay' else 'CNY'
    lock = 'jmh:usd-price-tier:ebay' if platform == 'ebay' else 'jmh:cny-price-tier:amz'
    with db_connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT GET_LOCK(%s,0) acquired',(lock,))
        if cursor.fetchone()['acquired']!=1: raise ReportBusy('本平台报表正在计算，请稍后再试')
        try:
            begin(connection,cursor)
            ctx = context(cursor,platform)
            candidates,empty,count = source(cursor,platform,ctx)
            report = engine.summarize(candidates,ctx['rates'],empty,target_currency=currency)
            report.update(platform=platform,rate_month=ctx['rate_month'],rates=ctx['rates'],source_listing_count=count,
                          report_id=str(uuid4()),generated_at=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'))
            values = []
            for parent in report['items']:
                for node in [parent]+parent['children']:
                    meta = {k:v for k,v in node.items() if k not in ('tiers','children')}
                    for tier in node['tiers']:
                        values.append((platform,node['node_id'],node['scope'],node['store_key'],node['store_name'],node['site'],
                                       tier['tier_no'],tier['sku_count'],tier['sku_percent'],node['group_sku_count'],dumps(meta),report['report_id']))
            cursor.execute(f'DELETE FROM {detail_table} WHERE platform=%s',(platform,))
            if values:
                cursor.executemany(f'''INSERT INTO {detail_table} (platform,node_id,scope,store_key,store_name,site,tier_no,sku_count,
                                       sku_percent,group_sku_count,node_json,report_id) VALUES ({','.join(['%s']*12)})''',values)
            meta = {k:v for k,v in report.items() if k!='items'}
            cursor.execute(f'''INSERT INTO {head_table} (platform,report_id,generated_at,source_context_json,summary_json) VALUES (%s,%s,%s,%s,%s)
                               ON DUPLICATE KEY UPDATE report_id=VALUES(report_id),generated_at=VALUES(generated_at),
                               source_context_json=VALUES(source_context_json),summary_json=VALUES(summary_json)''',
                           (platform,report['report_id'],report['generated_at'],dumps(ctx),dumps(meta)))
            connection.commit()
            return dict(report,state='READY',stale=False)
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.execute('SELECT RELEASE_LOCK(%s)',(lock,))


def read_report(platform):
    check_platform(platform)
    head_table, detail_table = (USD_HEAD, USD_DETAIL) if platform == 'ebay' else (HEAD, DETAIL)
    expected_version = engine.USD_VERSION if platform == 'ebay' else engine.VERSION
    currency = 'USD' if platform == 'ebay' else 'CNY'
    ranges = engine.USD_RANGES if platform == 'ebay' else engine.RANGES
    with db_connection() as connection,connection.cursor() as cursor:
        begin(connection,cursor)
        cursor.execute(f'SELECT * FROM {head_table} WHERE platform=%s',(platform,))
        head = cursor.fetchone()
        if not head: return dict(platform=platform,state='EMPTY',items=[],stale=False)
        report = decode(head['summary_json'])
        if report.get('version')!=expected_version or report.get('target_currency', 'CNY')!=currency:
            return dict(platform=platform,state='EMPTY',items=[],stale=True,message='统计口径已更新，请重新统计')
        cursor.execute(f'SELECT * FROM {detail_table} WHERE platform=%s AND report_id=%s ORDER BY node_id,tier_no',(platform,head['report_id']))
        nodes = {}
        for row in cursor.fetchall():
            node = nodes.setdefault(row['node_id'],dict(decode(row['node_json']),tiers=[]))
            i = row['tier_no']-1
            if i not in range(5): raise ValueError('统计仓库档位异常，请重新统计')
            node['tiers'].append(dict(tier_no=i+1,label=engine.LABELS[i],range=ranges[i],sku_count=row['sku_count'],sku_percent=str(row['sku_percent'])))
        if any(len(n['tiers'])!=5 or sum(t['sku_count'] for t in n['tiers'])!=n['group_sku_count'] for n in nodes.values()):
            raise ValueError('统计仓库不完整，请重新统计')
        parents = {n['store_key']:dict(n,children=[]) for n in nodes.values() if n['scope']=='SHOP'}
        for node in nodes.values():
            if node['scope']=='SITE':
                if node['store_key'] not in parents: raise ValueError('统计仓库缺少店铺汇总，请重新统计')
                parents[node['store_key']]['children'].append(node)
        if len(parents)!=report['shop_count'] or sum(len(p['children']) for p in parents.values())!=report['site_group_count']:
            raise ValueError('统计仓库分组不完整，请重新统计')
        for parent in parents.values(): parent['children'].sort(key=lambda n:n['site'])
        items = sorted(parents.values(),key=lambda p:(-p['group_sku_count'],p['store_name']))
        return dict(report,state='READY',items=items,stale=decode(head['source_context_json'])!=context(cursor,platform))
