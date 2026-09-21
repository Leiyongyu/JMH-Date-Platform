"""GetMyeBaySelling ActiveList -> complete, account-isolated raw snapshots."""
from __future__ import annotations

import json
from datetime import datetime
from tempfile import TemporaryFile
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.ebay_api import EbaySellerClient, EbayApiError
from backend.ebay_api.accounts import configured_accounts, credentials_for
from backend.repositories import ebay_store_listing_repository as repo

TASK_CODE = 'ebay_store_listing_sync'
TASK_NAME = 'eBay店铺商品信息每月同步'
PAGE_SIZE = 100
MAX_PAGES = 10000


class EbayStoreListingSyncError(ValueError):
    def __init__(self, message, stage, metrics):
        super().__init__(message)
        self.stage, self.metrics = stage, dict(metrics)


def sync_ebay_store_listings():
    batch_id = str(uuid4())
    pulled_at = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
    metrics = {'sync_batch_id': batch_id, 'extract_rows': 0, 'ods_rows': 0, 'shop_count': 0}
    stage, account_no, page, source_row = 'CONFIG', 0, 0, None
    try:
        accounts = configured_accounts()
        completed = []
        identity_ids = set()
        # Spool only non-secret source records; full extraction precedes any DELETE.
        with TemporaryFile(mode='w+t', encoding='utf-8') as spool:
            for account_no, account in enumerate(accounts, 1):
                stage, page = 'EXTRACT', 1
                source_row = account.get('source_row')
                client = EbaySellerClient(credentials_for(account))
                try:
                    if account.get('source') == 'workbook':
                        identity = client.trading_identity(expected_login=account.get('source_login'))
                        if not isinstance(identity.get('userId'), str) or not identity['userId'].strip():
                            raise EbayApiError('身份接口缺少稳定账号ID，拒绝覆盖')
                        account = {**account, 'username': identity['username'], 'user_id': identity['userId']}
                    if account['user_id'] in identity_ids:
                        raise EbayApiError('不同配置行授权到了同一eBay账号，拒绝重复同步')
                    identity_ids.add(account['user_id'])
                    seen, totals = set(), None
                    while True:
                        response = client.active_listings_page(page=page, page_size=PAGE_SIZE,
                            expected_username=account['username'],
                            identity_source='trading' if account.get('source') == 'workbook' else 'rest')
                        if response.get('ack') != 'Success':
                            raise EbayApiError('Trading响应不是纯成功状态，拒绝以可能不完整的数据覆盖')
                        seller = response['seller']
                        if seller.get('userId') != account['user_id'] or seller['username'].casefold() != account['username'].casefold():
                            raise EbayApiError('授权身份与配置账号ID不一致，拒绝覆盖')
                        total, pages = response['total_entries'], response['total_pages']
                        if pages != ((total + PAGE_SIZE - 1) // PAGE_SIZE if total else pages) or (not total and pages not in (0, 1)) or pages > MAX_PAGES:
                            raise EbayApiError('分页总数异常，拒绝覆盖')
                        if totals is None:
                            totals = (total, pages)
                        if totals != (total, pages):
                            raise EbayApiError('拉取期间商品总数或页数变化，请重试完整任务')
                        expected = max(0, min(PAGE_SIZE, total - (page - 1) * PAGE_SIZE))
                        if len(response['items']) != expected:
                            raise EbayApiError('本页条数不完整，拒绝覆盖')
                        # Preserve all envelope fields including future fields, excluding items.
                        meta = {k: v for k, v in response.items() if k not in ('items', 'raw_xml')}
                        if account.get('source') == 'workbook':
                            meta['source_shop'] = {k: account[k] for k in ('source_row', 'shop_name', 'browser_id')}
                        for item in response['items']:
                            if not item.get('item_id') or item['item_id'] in seen:
                                raise EbayApiError('跨页ItemID重复或缺失，拒绝覆盖')
                            seen.add(item['item_id'])
                            spool.write(repo.dumps({'seller': seller, 'item': item, 'page': page, 'total': total, 'meta': meta}) + '\n')
                            metrics['extract_rows'] += 1
                        if page >= pages:
                            if len(seen) != total:
                                raise EbayApiError('完整拉取条数与接口总数不符')
                            completed.append({**seller, 'row_count': len(seen)})
                            break
                        page += 1
                finally:
                    client.close()
            metrics['shop_count'] = len(completed)
            published_at = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
            for account in completed:
                account['published_at'] = published_at
            stage = 'LOAD'
            spool.seek(0)
            metrics.update(repo.replace_snapshots((json.loads(line) for line in spool), completed,
                           batch_id=batch_id, pulled_at=pulled_at))
        return {**metrics, 'accounts': [{'seller_account': a['username'], 'rows': a['row_count']} for a in completed]}
    except Exception as exc:
        detail = str(exc) if isinstance(exc, (EbayApiError, repo.AccountIdentityConflict)) else type(exc).__name__
        raise EbayStoreListingSyncError(
            f'eBay店铺商品同步失败；stage={stage} account_index={account_no} source_row={source_row} page={page} batch={batch_id}；{detail}',
            stage, metrics) from None
