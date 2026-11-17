"""Multi-account configuration contains credential references, never token values."""
from __future__ import annotations

import json
import os
import re

from backend.config import load_dotenv
from .credentials import EbayApiError, EbayCredentials, read_dpapi_token


def configured_accounts() -> list[dict]:
    load_dotenv()
    if os.getenv('EBAY_SELLER_ACCOUNTS_FILE', '').strip():
        from .workbook_accounts import read_workbook_accounts
        return read_workbook_accounts()['accounts']
    try:
        accounts = json.loads(os.getenv('EBAY_SELLER_ACCOUNTS', '[]'))
    except (ValueError, TypeError):
        raise EbayApiError('EBAY_SELLER_ACCOUNTS必须是账号配置JSON数组') from None
    if not isinstance(accounts, list) or not accounts:
        raise EbayApiError('请配置EBAY_SELLER_ACCOUNTS，禁止无账号配置执行覆盖')
    names, ids = set(), set()
    allowed = {'username', 'user_id', 'token_file', 'refresh_token_env', 'client_id_env', 'client_secret_env'}
    for account in accounts:
        if not isinstance(account, dict) or set(account) - allowed:
            raise EbayApiError('账号配置包含未知字段；仅允许凭证引用，不能填写明文Token')
        for field in ('username', 'user_id'):
            value = account.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise EbayApiError('每个账号须配置有效username及user_id')
            account[field] = value.strip()
        if account['username'].casefold() in names or account['user_id'] in ids:
            raise EbayApiError('账号配置重复')
        names.add(account['username'].casefold())
        ids.add(account['user_id'])
        if bool(account.get('token_file')) == bool(account.get('refresh_token_env')):
            raise EbayApiError('每个账号须且仅须配置token_file或refresh_token_env')
        if account.get('token_file') and not isinstance(account['token_file'], str):
            raise EbayApiError('token_file必须为路径字符串')
        for field in ('refresh_token_env', 'client_id_env', 'client_secret_env'):
            if field in account and (not isinstance(account[field], str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', account[field])):
                raise EbayApiError('凭证环境变量引用名不合法')
    return accounts


def credentials_for(account: dict) -> EbayCredentials:
    if account.get('source') == 'workbook':
        credential = account.get('_credentials')
        if not isinstance(credential, EbayCredentials):
            raise EbayApiError('工作簿账号缺少有效凭证')
        return credential
    client_id = os.getenv(account.get('client_id_env', 'EBAY_CLIENT_ID'), '').strip()
    secret = os.getenv(account.get('client_secret_env', 'EBAY_CLIENT_SECRET'), '').strip()
    if not client_id or not secret:
        raise EbayApiError('店铺应用Client ID或Secret未配置')
    token = (read_dpapi_token(account['token_file']) if account.get('token_file')
             else os.getenv(account['refresh_token_env'], '').strip())
    if not token:
        raise EbayApiError('店铺Refresh Token未配置')
    return EbayCredentials(client_id, secret, token)
