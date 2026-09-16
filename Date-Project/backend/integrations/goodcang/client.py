"""GoodCang V1 warehouse storage API; credentials never enter logs."""
from __future__ import annotations

import hashlib
import json
import logging
import ssl
import time
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from backend.config import settings

PATH = "/finance/get_wh_inventory_storage"
DETAIL_PATH = "/finance/get_wh_inventory_storage_detail"
PAGE_SIZE = 200
DETAIL_PAGE_SIZE = 200
LOG = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class GoodcangRequestError(ValueError):
    pass


def source_json(value):
    """Encode decoded JSON without rounding numeric literals through float."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("谷仓返回非有限数值")
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + source_json(v)
                              for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(source_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _invalid_constant(_value):
    raise ValueError("non-finite JSON constant")


def _temporary_transport(exc):
    current, seen = exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return False
        current = current.__cause__ or current.__context__
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


class GoodcangClient:
    def __init__(self, config=settings, *, transport=None):
        endpoint = config.goodcang_endpoint.rstrip("/")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("GOODCANG_ENDPOINT必须是无凭证、无查询参数的HTTPS地址")
        if not config.goodcang_app_token or not config.goodcang_app_key:
            raise ValueError("请配置Python服务的GOODCANG_APP_TOKEN和GOODCANG_APP_KEY")
        self.endpoint = endpoint
        self.retries = max(0, min(config.goodcang_max_retries, 6))
        self.interval = max(0, config.goodcang_min_request_interval_sec)
        self.next_request_at = 0.0
        self.http = httpx.Client(
            timeout=config.goodcang_request_timeout_sec,
            follow_redirects=False,
            headers={"app-token": config.goodcang_app_token, "app-key": config.goodcang_app_key},
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.http.close()

    def fetch_storage_page(self, date_from, date_to, page):
        body = {"dateFrom": date_from, "dateTo": date_to, "page": page, "pageSize": PAGE_SIZE}
        return self._request_page(PATH, body, page)

    def fetch_storage_detail_page(self, wis_code, page):
        if not isinstance(wis_code, str) or not wis_code.strip() or len(wis_code.strip()) > 32:
            raise ValueError("谷仓仓租明细请求单号必须为1至32位字符串")
        code = wis_code.strip()
        # This V1 endpoint uses different pagination keys from the summary endpoint.
        body = {"wis_code": code, "page_index": page, "page_size": DETAIL_PAGE_SIZE}
        bill_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
        return self._request_page(DETAIL_PATH, body, page, f" bill_hash={bill_hash}")

    def _request_page(self, path, body, page, context=""):
        for attempt in range(1, self.retries + 2):
            wait = self.next_request_at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.next_request_at = time.monotonic() + self.interval
            delay = min(30, 2 ** attempt)
            temporary = False
            try:
                with self.http.stream("POST", self.endpoint + path, json=body) as response:
                    status = response.status_code
                    if status != 200:
                        reason = f"HTTP {status}"
                        temporary = status in {429, 500, 502, 503, 504}
                        retry_after = response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = min(30, max(delay, int(retry_after)))
                    else:
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_RESPONSE_BYTES:
                                raise GoodcangRequestError(f"谷仓仓租响应超过安全大小；接口={path} page={page}{context}")
                            chunks.append(chunk)
                        result = json.loads(b"".join(chunks).decode("utf-8-sig"),
                                            parse_float=Decimal, parse_constant=_invalid_constant)
                        if not isinstance(result, dict):
                            raise GoodcangRequestError(f"谷仓仓租响应不是对象；接口={path} page={page}{context}")
                        return result
            except GoodcangRequestError:
                raise
            except (UnicodeError, ValueError, RecursionError):
                reason = "JSON响应结构或编码异常"
            except httpx.TransportError as exc:
                temporary = _temporary_transport(exc)
                reason = type(exc).__name__
            if not temporary or attempt > self.retries:
                raise GoodcangRequestError(
                    f"谷仓仓租接口失败；接口={path} page={page}{context} "
                    f"attempt={attempt}/{self.retries + 1} reason={reason}"
                ) from None
            LOG.warning("谷仓仓租有限重试 path=%s page=%s%s attempt=%s/%s reason=%s delay=%ss",
                        path, page, context, attempt, self.retries + 1, reason, delay)
            time.sleep(delay)
        raise AssertionError("unreachable")
