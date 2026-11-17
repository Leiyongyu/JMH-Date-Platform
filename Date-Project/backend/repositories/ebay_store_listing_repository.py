"""Account-scoped atomic monthly snapshots in the Python database.

同一张表按月累积：每个账号每个月一份，键是(月份,账号,ItemID)。同步任务每月跑
一次，同月补跑按(月份,账号)先删后插，所以一个月始终只有一份。
"""
from __future__ import annotations

import json
from itertools import islice

from backend.database import db_connection

TABLE = 'ods_ebay_store_listing_latest'
STATE_TABLE = 'ods_ebay_store_listing_state'
# 不再存 raw_xml / response_meta_json / normalized_json / source_page / api_total：
# 前三个实测占 91MB 里的 57MB，按月累积一年就是 1.2GB；且抽样3000行核对过
# normalized_json 的键除 variations 外全部与扁平列重复，后两个只对当次拉取排障
# 有意义。接口返回的是当前状态，随时能重拉，原始XML留着的边际价值很低。
#
# variations 是唯一不能丢的：报表在刊登有变体时按变体的SKU和价格逐个统计、
# 不用父级那行，而扁平列只有父级的单个 sku/price。所以单拎成 variations_json，
# 并剥掉变体自己那份 raw_xml。
FIELDS = ('stat_month', 'seller_user_id', 'seller_account', 'item_id', 'sku', 'title', 'site',
          'current_price', 'currency', 'buy_it_now_price', 'buy_it_now_currency',
          'quantity', 'quantity_available', 'quantity_sold', 'watch_count', 'listing_type',
          'listing_duration', 'time_left', 'start_time', 'view_item_url', 'image_url',
          'variations_json', 'sync_batch_id', 'pulled_at')


class AccountIdentityConflict(ValueError):
    """Safe diagnostic for a legacy ID conflict; never contains credentials."""


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def stat_month(pulled_at):
    """留档月份取自拉取时间，不取当前日期：补跑时才会落在本来那个月。"""
    return pulled_at.strftime('%Y-%m')


def variations_payload(item):
    """只留变体数组，并剥掉每个变体自己的raw_xml；无变体返回None。

    变体的sku与价格是扁平列没有的：报表在刊登有变体时按变体逐个统计、不用父级
    那行，丢了会把多规格刊登塌缩成一个SKU，而且各变体价格不同，分档会错。
    无变体存NULL而不是空数组，统计时好直接判空。
    """
    variations = item.get('variations') or []
    if not variations:
        return None
    return dumps([{k: v for k, v in one.items() if k != 'raw_xml'} for one in variations])


def record_values(record, batch_id, pulled_at):
    item, seller = record['item'], record['seller']
    price, buy = item['current_price'], item['buy_it_now_price']
    # FIELDS[11:21] 是 quantity 起到 image_url 的一段扁平字段，逐个从item取。
    return (stat_month(pulled_at), seller['userId'], seller['username'], item['item_id'],
            item.get('sku'), item.get('title'), item.get('site'),
            price['value'], price['currency'], buy['value'], buy['currency'],
            *(item.get(key) for key in FIELDS[11:21]),
            variations_payload(item), batch_id, pulled_at)


def replace_snapshots(records, accounts, *, batch_id, pulled_at):
    """All requested accounts publish together. Unrequested accounts are untouched.

    按月累积：只动本次拉取那个月的这些账号，其他月份、其他账号一行不碰。
    """
    expected = {a['userId']: a['row_count'] for a in accounts}
    if not expected or len(expected) != len(accounts):
        raise ValueError('发布账号为空或重复')
    names = {a['userId']: a['username'] for a in accounts}
    month = stat_month(pulled_at)
    sql = f"INSERT INTO {TABLE} (" + ','.join(f'`{f}`' for f in FIELDS) + ') VALUES (' + ','.join(['%s'] * len(FIELDS)) + ')'
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                # Do not silently create a second copy when an installation already has REST IDs.
                # Inspect both tables before any DELETE; never migrate identity based on username alone.
                for user_id, name in names.items():
                    if not user_id.startswith('trading:'):
                        continue
                    for table in (TABLE, STATE_TABLE):
                        cursor.execute(f'''SELECT seller_user_id FROM {table}
                            WHERE seller_user_id NOT LIKE %s
                               OR (LOWER(seller_account)=LOWER(%s) AND seller_user_id<>%s) LIMIT 1''',
                            ('trading:%', name, user_id))
                        if cursor.fetchone():
                            raise AccountIdentityConflict('存在旧REST账号数据或同名店铺其他标识，需核对账号映射后再同步；未删除旧数据')
                deleted = 0
                for user_id in expected:
                    # 只清该账号**本月**那一份：同月补跑覆盖，往月的历史一行不动。
                    cursor.execute(f'DELETE FROM {TABLE} WHERE stat_month=%s AND seller_user_id=%s',
                                   (month, user_id))
                    deleted += cursor.rowcount
                counts = dict.fromkeys(expected, 0)
                iterator = iter(records)
                while chunk := list(islice(iterator, 200)):
                    for record in chunk:
                        seller = record['seller']
                        if seller['userId'] not in expected or names[seller['userId']] != seller['username']:
                            raise ValueError('发布记录账号与已验证账号不一致')
                        counts[seller['userId']] += 1
                    cursor.executemany(sql, [record_values(r, batch_id, pulled_at) for r in chunk])
                if counts != expected:
                    raise ValueError('发布行数与已校验源数据不一致')
                for account in accounts:
                    cursor.execute(f'SELECT COUNT(*) AS n FROM {TABLE} WHERE stat_month=%s AND seller_user_id=%s',
                                   (month, account['userId']))
                    if cursor.fetchone()['n'] != account['row_count']:
                        raise ValueError('数据库写入行数校验失败')
                    # row_count=0 也要留行：趋势图要能区分"当月空店"和"当月没同步"。
                    cursor.execute(f'''INSERT INTO {STATE_TABLE}
                        (stat_month,seller_user_id,seller_account,row_count,sync_batch_id,pulled_at,published_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                        seller_account=VALUES(seller_account),row_count=VALUES(row_count),
                        sync_batch_id=VALUES(sync_batch_id),pulled_at=VALUES(pulled_at),
                        published_at=VALUES(published_at)''',
                        (month, account['userId'], account['username'], account['row_count'],
                         batch_id, pulled_at, account['published_at']))
            connection.commit()
            return {'ods_rows': sum(counts.values()), 'inserted_rows': sum(counts.values()),
                    'deleted_rows': deleted, 'stat_month': month}
        except Exception:
            connection.rollback()
            raise
