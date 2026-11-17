"""Reuse verified seller extraction with an independent monthly price publisher."""
import os

from backend.ebay_api.workbook_accounts import read_workbook_accounts
from backend.repositories import ebay_mixed_sales_price_repository as repo
from backend.services.ebay_store_listing_sync_service import sync_ebay_store_listings

TASK_CODE = 'ebay_mixed_sales_price_sync'
TASK_NAME = '混销-eBay在售售价月度同步'


def sync_prices():
    missing = []
    if os.getenv('EBAY_SELLER_ACCOUNTS_FILE','').strip():
        source = read_workbook_accounts()
        missing = source['missing_credentials']
    result = sync_ebay_store_listings(publisher=repo.replace_snapshots)
    return {**result, 'skipped_rows': len(missing), 'missing_credentials': missing}
