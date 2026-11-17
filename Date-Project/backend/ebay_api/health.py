"""Read-only bounded probes; never emit tokens, response bodies or exception text."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import requests

from .client import TOKEN_URL, TRADING_URL

NS = '{urn:ebay:apis:eBLBaseComponents}'


class ProbeFailure(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason
        super().__init__(reason)


class HealthClient:
    def __init__(self, credentials, *, session=None, sleep=time.sleep):
        self.credentials = credentials
        self.session = session or requests.Session()
        self.sleep = sleep

    def close(self):
        self.session.close()

    def _request(self, operation, **kwargs):
        for attempt in range(3):
            try:
                return self.session.post(timeout=(10, 30), verify=True, allow_redirects=False, **kwargs)
            except requests.exceptions.SSLError:
                raise ProbeFailure('REVIEW', operation + '_TLS_ERROR') from None
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise ProbeFailure('REVIEW', operation + '_NETWORK_ERROR') from None
                self.sleep((5, 15)[attempt])
            except requests.RequestException:
                raise ProbeFailure('REVIEW', operation + '_TRANSPORT_ERROR') from None

    def _token(self):
        c = self.credentials
        response = self._request('OAUTH', url=TOKEN_URL, auth=(c.client_id, c.client_secret),
                                 data={'grant_type': 'refresh_token', 'refresh_token': c.refresh_token})
        try:
            payload = response.json()
        except (ValueError, TypeError):
            raise ProbeFailure('REVIEW', 'OAUTH_RESPONSE_INVALID') from None
        if response.status_code == 400 and isinstance(payload, dict) and payload.get('error') == 'invalid_grant':
            raise ProbeFailure('INVALID', 'OAUTH_INVALID_GRANT')
        if response.status_code != 200:
            raise ProbeFailure('REVIEW', f'OAUTH_HTTP_{response.status_code}')
        token = payload.get('access_token') if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise ProbeFailure('REVIEW', 'OAUTH_TOKEN_MISSING')
        return token

    def _trading(self, call, token, body):
        response = self._request(call.upper(), url=TRADING_URL,
            headers={'X-EBAY-API-CALL-NAME': call, 'X-EBAY-API-SITEID': '0',
                     'X-EBAY-API-COMPATIBILITY-LEVEL': '1193', 'X-EBAY-API-IAF-TOKEN': token,
                     'Content-Type': 'text/xml; charset=utf-8'},
            data=(f'<{call}Request xmlns="urn:ebay:apis:eBLBaseComponents">{body}</{call}Request>').encode())
        if response.status_code != 200:
            raise ProbeFailure('REVIEW', f'{call.upper()}_HTTP_{response.status_code}')
        content = response.content
        try:
            text = content.decode('utf-8-sig')
            if len(content) > 2_000_000 or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
                raise ValueError()
            root = ET.fromstring(text)
        except (UnicodeError, ValueError, ET.ParseError):
            raise ProbeFailure('REVIEW', call.upper() + '_XML_INVALID') from None
        if root.tag != NS + call + 'Response':
            raise ProbeFailure('REVIEW', call.upper() + '_ROOT_INVALID')
        if root.findtext(NS + 'Ack') != 'Success':
            codes = [e.findtext(NS + 'ErrorCode', '') for e in root.findall(NS + 'Errors')]
            codes = [c for c in codes if c.isascii() and c.isdigit() and len(c) <= 10]
            raise ProbeFailure('REVIEW', call.upper() + '_ACK_ERROR' + (':' + ','.join(codes[:3]) if codes else ''))
        if any(e.findtext(NS + 'SeverityCode') == 'Error' for e in root.findall(NS + 'Errors')):
            raise ProbeFailure('REVIEW', call.upper() + '_API_ERROR')
        return root

    def check(self, expected_login):
        """Email is compared only in memory; it is never in the returned report."""
        try:
            token = self._token()
            root = self._trading('GetUser', token, '<DetailLevel>ReturnAll</DetailLevel>')
            user = root.find(NS + 'User')
            username = '' if user is None else (user.findtext(NS + 'UserID') or '').strip()
            if not username or len(username) > 200:
                raise ProbeFailure('REVIEW', 'USER_ID_MISSING')
            expected = str(expected_login or '').strip().casefold()
            if not expected:
                raise ProbeFailure('REVIEW', 'EXPECTED_ACCOUNT_MISSING')
            actual = (user.findtext(NS + 'Email') or '').strip().casefold() if '@' in expected else username.casefold()
            if not actual or actual in {'invalid request', 'email not available'}:
                raise ProbeFailure('REVIEW', 'ACCOUNT_EMAIL_UNAVAILABLE')
            if expected != actual:
                return {'status': 'MISMATCH', 'reason': 'ACCOUNT_MISMATCH', 'seller_account': username, 'listing_count': None}
            root = self._trading('GetMyeBaySelling', token,
                '<ActiveList><Include>true</Include><Pagination><EntriesPerPage>1</EntriesPerPage>'
                '<PageNumber>1</PageNumber></Pagination></ActiveList>'
                '<SoldList><Include>false</Include></SoldList><UnsoldList><Include>false</Include></UnsoldList>'
                '<ScheduledList><Include>false</Include></ScheduledList>')
            count = root.findtext(f'{NS}ActiveList/{NS}PaginationResult/{NS}TotalNumberOfEntries', '').strip()
            if not count.isascii() or not count.isdigit() or len(count) > 12:
                raise ProbeFailure('REVIEW', 'LISTING_COUNT_INVALID')
            return {'status': 'HEALTHY', 'reason': 'OK', 'seller_account': username, 'listing_count': int(count)}
        except ProbeFailure as exc:
            return {'status': exc.status, 'reason': exc.reason, 'seller_account': None, 'listing_count': None}

