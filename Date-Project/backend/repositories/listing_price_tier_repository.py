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
    # 每个币种各自取"不晚于当月、且该字段有正值"的最新一个月，作为兜底：
    # 月度汇率同步还没跑时不至于整份报表卡住，同币种也不会被另一个币种的
    # 缺失连累。不取未来月份——预先录入的下月汇率此刻尚未生效。
    # (rate_month,currency_code) 唯一，同币种同月不会有第二行。
    cursor.execute(f'''SELECT c.currency_code,c.rate_month,c.{rate_field} rate
                       FROM dim_lingxing_currency_month c
                       WHERE c.rate_month<=%s AND c.{rate_field} IS NOT NULL AND c.{rate_field}>0
                         AND c.rate_month=(SELECT MAX(x.rate_month) FROM dim_lingxing_currency_month x
                                           WHERE x.currency_code=c.currency_code AND x.rate_month<=%s
                                             AND x.{rate_field} IS NOT NULL AND x.{rate_field}>0)
                       ORDER BY c.currency_code''',(month,month))
    picked = list(cursor.fetchall())
    rates = {r['currency_code'].strip().upper(): str(r['rate']) for r in picked}
    # 记下每个币种实际取自哪个月：回退发生时页面能说清用的是哪一版汇率，
    # 也让 read_report 的 stale 比对能发现"汇率换月了"。
    rate_months = {r['currency_code'].strip().upper(): r['rate_month'] for r in picked}
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
    return decode(dumps(dict(rate_month=month,rates=rates,rate_months=rate_months,source=state,shops=shops)))


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
    rate_field = 'rate_org' if platform == 'ebay' else 'my_rate'
    lock = 'jmh:usd-price-tier:ebay' if platform == 'ebay' else 'jmh:cny-price-tier:amz'
    with db_connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT GET_LOCK(%s,0) acquired',(lock,))
        if cursor.fetchone()['acquired']!=1: raise ReportBusy('本平台报表正在计算，请稍后再试')
        try:
            begin(connection,cursor)
            ctx = context(cursor,platform)
            candidates,empty,count = source(cursor,platform,ctx)
            report = engine.summarize(candidates,ctx['rates'],empty,target_currency=currency)
            # 缺当月汇率会让该币种的商品整批换算不出来、被排除在占比之外。
            # 只留一行角标提示的话，页面看着仍然正常，却可能少掉大半SKU
            # （例：缺EUR/GBP时eBay只剩USD站点，17050→5061）。与批次、行数
            # 校验一样按"整份拒绝、保留旧报表"处理，不发布残缺口径。
            # missing_currencies 只收集真实出现过的币种，FX表里无关币种为空不会误报。
            if report['missing_currencies']:
                raise ValueError(
                    f"{'、'.join(report['missing_currencies'])}在汇率表里没有任何可用的"
                    f"{rate_field}（已回退查找不晚于{ctx['rate_month']}的全部月份），"
                    f"{report['missing_rate_rows']}条商品无法换算成{currency}；"
                    f"已保留上一次报表，请先补齐这些币种的汇率再重新统计")
            report.update(platform=platform,rate_month=ctx['rate_month'],rates=ctx['rates'],
                          rate_months=ctx['rate_months'],source_listing_count=count,
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
    # 档位数随币种变（人民币5档、美元7档），不能再写死5。
    labels, ranges = engine.labels_for(currency), engine.ranges_for(currency)
    size = len(labels)
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
            if i not in range(size): raise ValueError('统计仓库档位异常，请重新统计')
            node['tiers'].append(dict(tier_no=i+1,label=labels[i],range=ranges[i],sku_count=row['sku_count'],sku_percent=str(row['sku_percent'])))
        if any(len(n['tiers'])!=size or sum(t['sku_count'] for t in n['tiers'])!=n['group_sku_count'] for n in nodes.values()):
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
