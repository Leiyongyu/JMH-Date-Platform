"""One monthly table, account-scoped replacement after complete extraction."""
import json
import re
from itertools import islice

from backend.database import db_connection
from backend.services.ebay_order_product_key import product_sku, product_sku_sql

TABLE = 'ods_ebay_mixed_sales_listing_monthly'


def clean_item(item):
    result = {k: v for k, v in item.items() if k != 'raw_xml'}
    result['variations'] = [{k: v for k, v in row.items() if k != 'raw_xml'} for row in item.get('variations', [])]
    return result


def replace_snapshots(records, accounts, *, batch_id, pulled_at):
    expected = {a['userId']: a for a in accounts}
    if not expected or len(expected) != len(accounts):
        raise ValueError('店铺为空或重复，拒绝发布')
    month = pulled_at.strftime('%Y-%m')
    columns = ('stat_month','seller_user_id','seller_account','shop_name','record_type','item_id',
               'sku','normalized_sku','title','site','current_price','currency','buy_it_now_price',
               'buy_it_now_currency','listing_type','quantity','quantity_available','quantity_sold',
               'view_item_url','image_url','variations_json','raw_json','sync_batch_id','pulled_at','published_at')
    insert = f"INSERT INTO {TABLE} ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))})"
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                deleted = 0
                counts = dict.fromkeys(expected, 0)
                for uid, account in expected.items():
                    cursor.execute(f'SELECT 1 FROM {TABLE} WHERE seller_account=%s AND seller_user_id<>%s LIMIT 1', (account['username'],uid))
                    if cursor.fetchone():
                        raise ValueError('店铺稳定标识与已有记录不一致，拒绝覆盖')
                    cursor.execute(f'DELETE FROM {TABLE} WHERE stat_month=%s AND seller_user_id=%s', (month,uid))
                    deleted += cursor.rowcount
                iterator = iter(records)
                while rows := list(islice(iterator, 200)):
                    values = []
                    for record in rows:
                        uid = record['seller']['userId']
                        account = expected.get(uid)
                        if not account or record['seller']['username'] != account['username']:
                            raise ValueError('商品记录店铺与已核验账号不一致')
                        item = clean_item(record['item'])
                        if not item.get('item_id'):
                            raise ValueError('刊登编号缺失')
                        counts[uid] += 1
                        price, buy = item['current_price'], item['buy_it_now_price']
                        values.append((month,uid,account['username'],account.get('shop_name') or account['username'],
                            'ITEM',item['item_id'],item.get('sku'),product_sku(item.get('sku')) or None,
                            item.get('title'),item.get('site'),price['value'],price['currency'],buy['value'],buy['currency'],
                            *[item.get(k) for k in ('listing_type','quantity','quantity_available','quantity_sold','view_item_url','image_url')],
                            json.dumps(item['variations'],ensure_ascii=False),json.dumps(item,ensure_ascii=False),
                            batch_id,pulled_at,account['published_at']))
                    cursor.executemany(insert, values)
                if counts != {uid:a['row_count'] for uid,a in expected.items()}:
                    raise ValueError('刊登条数与完整拉取结果不一致')
                for uid, account in expected.items():
                    cursor.execute(f'''INSERT INTO {TABLE}
                        (stat_month,seller_user_id,seller_account,shop_name,record_type,item_id,source_listing_count,
                         sync_batch_id,pulled_at,published_at) VALUES (%s,%s,%s,%s,'SHOP','',%s,%s,%s,%s)''',
                        (month,uid,account['username'],account.get('shop_name') or account['username'],
                         counts[uid],batch_id,pulled_at,account['published_at']))
            connection.commit()
            return dict(ods_rows=sum(counts.values()),inserted_rows=sum(counts.values()),deleted_rows=deleted,stat_month=month)
        except Exception:
            connection.rollback()
            raise


def list_prices(*, sku, site=None, stat_month=None, page=1, page_size=20):
    sku = product_sku(sku)
    if not sku:
        raise ValueError('请选择产品SKU')
    if stat_month and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', stat_month):
        raise ValueError('售价月份无效')
    page, size = max(int(page),1), min(max(int(page_size),1),200)
    with db_connection() as connection, connection.cursor() as cursor:
        connection.begin()
        cursor.execute(f"SELECT DISTINCT stat_month FROM {TABLE} WHERE record_type='SHOP' ORDER BY stat_month DESC")
        months = [r['stat_month'] for r in cursor.fetchall()]
        month = stat_month or (months[0] if months else None)
        if not month:
            return dict(items=[],total=0,months=[],statMonth=None,pageNum=page,pageSize=size)
        # Variants have their own SKU and original native price. Never assign a
        # parent listing's single price to all variant SKUs.
        variant_key = product_sku_sql('v.sku')
        source = f'''WITH prices AS (
            SELECT t.seller_account sellerAccount,t.shop_name shopName,t.item_id itemId,t.sku,
                t.normalized_sku productSku,t.site,t.title,t.current_price price,t.currency,
                t.buy_it_now_price buyItNowPrice,t.buy_it_now_currency buyItNowCurrency,
                t.listing_type listingType,t.view_item_url viewItemUrl,t.pulled_at pulledAt
            FROM {TABLE} t WHERE stat_month=%s AND record_type='ITEM'
              AND COALESCE(JSON_LENGTH(t.variations_json),0)=0
            UNION ALL
            SELECT t.seller_account,t.shop_name,t.item_id,v.sku COLLATE utf8mb4_unicode_ci,
                ({variant_key}) COLLATE utf8mb4_unicode_ci,t.site,t.title,
                v.price COLLATE utf8mb4_unicode_ci,v.currency COLLATE utf8mb4_unicode_ci,
                NULL,NULL,t.listing_type,t.view_item_url,t.pulled_at
            FROM {TABLE} t JOIN JSON_TABLE(t.variations_json,'$[*]' COLUMNS(
                sku VARCHAR(255) PATH '$.sku',price VARCHAR(128) PATH '$.price.value',
                currency VARCHAR(16) PATH '$.price.currency')) v ON TRUE
            WHERE t.stat_month=%s AND t.record_type='ITEM'
        )'''
        where = ' WHERE productSku=%s'
        args = [month,month,sku]
        if site:
            code = {'德国':'DE','英国':'UK','美国':'US'}.get(site,site)
            where += ' AND site=%s'
            args.append(code)
        cursor.execute(source+' SELECT COUNT(*) n FROM prices'+where, args)
        total = int(cursor.fetchone()['n'])
        cursor.execute(source+' SELECT * FROM prices'+where+' ORDER BY shopName,sellerAccount,itemId,sku LIMIT %s OFFSET %s',
                       [*args,size,(page-1)*size])
        rows = cursor.fetchall()
    return dict(items=rows,total=total,months=months,statMonth=month,pageNum=page,pageSize=size)
