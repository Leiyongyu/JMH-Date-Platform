from __future__ import annotations

import threading
import time
from hashlib import sha256
from xml.etree import ElementTree as ET

import requests

from .credentials import EbayCredentials, EbayApiError
from .listings import parse_active_page

TOKEN_URL = 'https://api.ebay.com/identity/v1/oauth2/token'
IDENTITY_URL = 'https://apiz.ebay.com/commerce/identity/v1/user/'
TRADING_URL = 'https://api.ebay.com/ws/api.dll'


class EbaySellerClient:
    """单店铺只读客户端；实例级Token缓存，TLS校验开启，拒绝重定向泄露凭证。"""
    def __init__(self, credentials: EbayCredentials, *, session=None, sleep=time.sleep):
        self._credentials = credentials
        self._session = session if session is not None else requests.Session()
        self._sleep = sleep
        self._token = ''
        self._expires_at = 0.0
        self._lock = threading.Lock()
        self._trading_identity_cache = None
        self._trading_identity_token = None
        self._trading_email = ''

    def close(self):
        self._session.close()

    def _request(self, method, url, **kwargs):
        operation = {TOKEN_URL: 'OAuth', IDENTITY_URL: 'Identity', TRADING_URL: 'Trading'}.get(url, 'API')
        # This client only refreshes OAuth tokens and performs read-only seller queries.
        # Retry the same request, never advance the page or retry HTTP/business failures.
        for attempt in range(3):
            try:
                response = self._session.request(method, url, timeout=(10, 60), allow_redirects=False,
                                                 verify=True, **kwargs)
                break
            except requests.exceptions.SSLError:
                raise EbayApiError(f'eBay TLS校验或连接失败；接口={operation}；不输出敏感异常正文') from None
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise EbayApiError(f'eBay网络请求失败；接口={operation}；已尝试3次；不输出敏感异常正文') from None
                self._sleep((5, 15)[attempt])
            except requests.RequestException:
                raise EbayApiError(f'eBay传输请求失败；接口={operation}；不输出敏感异常正文') from None
        if response.status_code != 200:
            raise EbayApiError(f'eBay接口请求失败；接口={operation} HTTP {response.status_code}')
        return response

    @staticmethod
    def _json(response):
        try:
            payload = response.json()
        except ValueError:
            raise EbayApiError('eBay返回无效JSON') from None
        if not isinstance(payload, dict):
            raise EbayApiError('eBay返回JSON结构异常')
        return payload

    def _access_token(self):
        with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            credential = self._credentials
            payload = self._json(self._request('POST', TOKEN_URL,
                auth=(credential.client_id, credential.client_secret),
                data={'grant_type': 'refresh_token', 'refresh_token': credential.refresh_token}))
            token, expires = payload.get('access_token'), payload.get('expires_in')
            if not isinstance(token, str) or not token or type(expires) is not int or expires <= 0:
                raise EbayApiError('OAuth成功响应缺少有效Token或有效期')
            self._token = token
            self._expires_at = time.monotonic() + max(0, expires - 120)
            return token

    def identity(self) -> dict:
        payload = self._json(self._request('GET', IDENTITY_URL,
            headers={'Authorization': 'Bearer ' + self._access_token(), 'Accept': 'application/json'}))
        if not isinstance(payload.get('username'), str) or not payload['username'].strip():
            raise EbayApiError('身份接口没有返回店铺账号，不能确认归属')
        return {key: payload.get(key) for key in ('userId', 'username', 'accountType', 'registrationMarketplaceId')}

    def trading_identity(self, *, expected_login: str) -> dict:
        """Verify the configured username/email; never return GetUser PII or raw XML.

        EIASToken is eBay's immutable user identifier, not an OAuth credential.
        Namespace its hash to avoid confusing it with the legacy REST userId.
        Cache only for this client's current OAuth token; refresh revalidates identity.
        """
        expected = str(expected_login or '').strip().casefold()
        if not expected:
            raise EbayApiError('缺少预期店铺账号，不能确认授权归属')
        token = self._access_token()
        if self._trading_identity_cache is None or self._trading_identity_token != token:
            response = self._request('POST', TRADING_URL,
                data=b'<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents"><DetailLevel>ReturnAll</DetailLevel></GetUserRequest>',
                headers={'X-EBAY-API-CALL-NAME': 'GetUser', 'X-EBAY-API-IAF-TOKEN': token,
                         'X-EBAY-API-COMPATIBILITY-LEVEL': '1193', 'X-EBAY-API-SITEID': '0',
                         'Content-Type': 'text/xml; charset=utf-8'})
            try:
                if len(response.content) > 2_000_000:
                    raise ValueError()
                decoded = response.content.decode('utf-8-sig')
                if '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
                    raise ValueError()
                root = ET.fromstring(decoded)
            except (UnicodeError, ValueError, ET.ParseError):
                raise EbayApiError('Trading GetUser响应XML异常，已停止拉取') from None
            ns = '{urn:ebay:apis:eBLBaseComponents}'
            if (root.tag != ns + 'GetUserResponse' or root.findtext(ns + 'Ack') != 'Success'
                    or any(e.findtext(ns + 'SeverityCode') == 'Error' for e in root.findall(ns + 'Errors'))):
                raise EbayApiError('Trading GetUser身份核验未成功，已停止拉取')
            user = root.find(ns + 'User')
            if user is None:
                raise EbayApiError('Trading GetUser缺少用户信息')
            username = (user.findtext(ns + 'UserID') or '').strip()
            stable_id = (user.findtext(ns + 'EIASToken') or '').strip()
            if not username or len(username) > 128 or not stable_id or len(stable_id) > 4096:
                raise EbayApiError('Trading GetUser缺少有效用户名或稳定账号标识，拒绝覆盖')
            self._trading_identity_cache = {'username': username,
                'userId': 'trading:' + sha256(stable_id.encode('utf-8')).hexdigest(),
                'identity_source': 'Trading.GetUser'}
            self._trading_email = (user.findtext(ns + 'Email') or '').strip().casefold()
            self._trading_identity_token = token
        actual = self._trading_email if '@' in expected else self._trading_identity_cache['username'].casefold()
        if not actual or actual in ('invalid request', 'email not available'):
            raise EbayApiError('Trading GetUser未提供可核对的店铺身份，拒绝覆盖')
        if actual != expected:
            raise EbayApiError('授权店铺与Excel或配置中的预期账号不一致，已停止拉取')
        return dict(self._trading_identity_cache)

    def active_listings_page(self, *, page=1, page_size=100, expected_username: str, identity_source='trading') -> dict:
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError('page须为正整数，page_size须为1到100')
        if not expected_username or not expected_username.strip():
            raise ValueError('必须指定预期店铺账号expected_username')
        if identity_source not in ('trading', 'rest'):
            raise ValueError('未知身份核验来源')
        identity = (self.trading_identity(expected_login=expected_username)
                    if identity_source == 'trading' else self.identity())
        if identity['username'].casefold() != expected_username.strip().casefold():
            raise EbayApiError('授权店铺与预期账号不一致，已停止拉取')
        # 明确只拿在售；不请求订单、客户信息或其他Selling列表。
        body = ('<?xml version="1.0" encoding="utf-8"?>'
                '<GetMyeBaySellingRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
                '<ActiveList><Include>true</Include><Pagination>'
                f'<EntriesPerPage>{page_size}</EntriesPerPage><PageNumber>{page}</PageNumber>'
                '</Pagination></ActiveList><HideVariations>false</HideVariations>'
                '<ScheduledList><Include>false</Include></ScheduledList>'
                '<SoldList><Include>false</Include></SoldList>'
                '<UnsoldList><Include>false</Include></UnsoldList>'
                '</GetMyeBaySellingRequest>')
        response = self._request('POST', TRADING_URL, data=body.encode('utf-8'), headers={
            'X-EBAY-API-CALL-NAME': 'GetMyeBaySelling', 'X-EBAY-API-IAF-TOKEN': self._access_token(),
            'X-EBAY-API-COMPATIBILITY-LEVEL': '1193', 'X-EBAY-API-SITEID': '0', 'Content-Type': 'text/xml'})
        return {'seller': identity, **parse_active_page(response.content, page=page, page_size=page_size)}
