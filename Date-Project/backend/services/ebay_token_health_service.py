"""Monthly health checks are independent of listing refresh and expiry reminders."""
from collections import Counter, defaultdict
from datetime import datetime
from time import sleep
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.ebay_api.health import HealthClient
from backend.ebay_api.workbook_accounts import read_workbook_accounts
from backend.repositories import ebay_token_health_repository as repo

TASK_CODE = 'ebay_token_health_check'
TASK_NAME = 'eBay店铺密钥月末健康检查'


def build_report(source, previous, *, client_factory=HealthClient, pause=sleep, now=None):
    now = now or datetime.now(ZoneInfo('Asia/Shanghai'))
    rows, identities = [], defaultdict(list)
    for index, account in enumerate(source['accounts']):
        if index:
            pause(0.5)
        client = None
        try:
            client = client_factory(account['_credentials'])
            result = client.check(account['source_login'])
        except Exception:
            # Continue to the next store; never serialize an exception that may contain request secrets.
            result = {'status': 'REVIEW', 'reason': 'UNEXPECTED_PROBE_ERROR', 'seller_account': None, 'listing_count': None}
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
        expires = account['expires_on']
        days = (expires - now.date()).days if expires else None
        row = {**result, 'source_row': account['source_row'], 'shop_name': account['shop_name'],
               'browser_id': account['browser_id'], 'previous_count': None,
               'expires_on': expires.isoformat() if expires else None, 'days_remaining': days,
               'expiry_status': ('UNKNOWN' if expires is None else 'EXPIRED' if days <= 0 else
                                 'EXPIRING' if now.date() >= account['remind_on'] else 'VALID')}
        if row['seller_account']:
            identities[row['seller_account'].casefold()].append(row)
        old = previous.get(row['browser_id'])
        if row['status'] == 'HEALTHY':
            if old and old['seller_account'].casefold() == row['seller_account'].casefold():
                row['previous_count'] = old['listing_count']
            count, before = row['listing_count'], row['previous_count']
            if count == 0:
                row.update(status='SUSPICIOUS', reason='ZERO_ACTIVE_LISTINGS')
            elif before and count * 2 <= before:
                row.update(status='SUSPICIOUS', reason='LISTINGS_DROP_AT_LEAST_50_PERCENT')
        rows.append(row)
    for same_identity in identities.values():
        if len(same_identity) > 1:
            for row in same_identity:
                row.update(status='MISMATCH', reason='DUPLICATE_SELLER_ACCOUNT')
    return {'sync_batch_id': str(uuid4()), 'checked_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            'timezone': 'Asia/Shanghai', 'accounts': rows, 'summary': dict(Counter(r['status'] for r in rows)),
            'skipped_rows': len(source['missing_credentials']), 'extract_rows': len(rows), 'ods_rows': len(rows)}


def check_ebay_token_health():
    try:
        source = read_workbook_accounts(allow_duplicate_tokens=True)
        report = build_report(source, repo.baselines())
        repo.save_report(report)
        return report
    except Exception:
        # Scheduler persists this string. A file/DB exception must not leak its parameter values.
        raise ValueError('eBay健康检查无法完成：请检查凭证文件格式、配置及健康检查表是否已初始化；未输出敏感正文') from None
