"""Account-scoped atomic latest snapshots in the Python database."""
from __future__ import annotations

import json
from itertools import islice

from backend.database import db_connection

TABLE = 'ods_ebay_store_listing_latest'
STATE_TABLE = 'ods_ebay_store_listing_state'
FIELDS = ('seller_user_id', 'seller_account', 'item_id', 'sku', 'title', 'site',
          'current_price', 'currency', 'buy_it_now_price', 'buy_it_now_currency',
          'quantity', 'quantity_available', 'quantity_sold', 'watch_count', 'listing_type',
          'listing_duration', 'time_left', 'start_time', 'view_item_url', 'image_url',
          'source_page', 'api_total', 'response_meta_json', 'normalized_json', 'raw_xml',
          'sync_batch_id', 'pulled_at')


class AccountIdentityConflict(ValueError):
    """Safe diagnostic for a legacy ID conflict; never contains credentials."""


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def record_values(record, batch_id, pulled_at):
    item, seller = record['item'], record['seller']
    price, buy = item['current_price'], item['buy_it_now_price']
    return (seller['userId'], seller['username'], item['item_id'], item.get('sku'), item.get('title'),
            item.get('site'), price['value'], price['currency'], buy['value'], buy['currency'],
            *(item.get(key) for key in FIELDS[10:20]), record['page'], record['total'],
            dumps(record['meta']), dumps({k: v for k, v in item.items() if k != 'raw_xml'}),
            item['raw_xml'], batch_id, pulled_at)


def replace_snapshots(records, accounts, *, batch_id, pulled_at):
    """All requested accounts publish together. Unrequested accounts are untouched."""
    expected = {a['userId']: a['row_count'] for a in accounts}
    if not expected or len(expected) != len(accounts):
        raise ValueError('发布账号为空或重复')
    names = {a['userId']: a['username'] for a in accounts}
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
                    cursor.execute(f'DELETE FROM {TABLE} WHERE seller_user_id=%s', (user_id,))
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
                    cursor.execute(f'SELECT COUNT(*) AS n FROM {TABLE} WHERE seller_user_id=%s', (account['userId'],))
                    if cursor.fetchone()['n'] != account['row_count']:
                        raise ValueError('数据库写入行数校验失败')
                    cursor.execute(f'''INSERT INTO {STATE_TABLE}
                        (seller_user_id,seller_account,row_count,sync_batch_id,pulled_at,published_at)
                        VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                        seller_account=VALUES(seller_account),row_count=VALUES(row_count),
                        sync_batch_id=VALUES(sync_batch_id),pulled_at=VALUES(pulled_at),published_at=VALUES(published_at)''',
                        (account['userId'], account['username'], account['row_count'], batch_id, pulled_at, account['published_at']))
            connection.commit()
            return {'ods_rows': sum(counts.values()), 'inserted_rows': sum(counts.values()), 'deleted_rows': deleted}
        except Exception:
            connection.rollback()
            raise
