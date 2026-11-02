"""数据助手的 eBay 实时只读取数（移植自 eBay 客服 AI Agent 的 data_assistant，改用本项目的店铺凭证）。

- 店铺与 refresh token 来自 EBAY_SELLER_ACCOUNTS_FILE（与商品同步同一份 Excel），不读取其他项目的凭证；
- REST 只发 GET，Trading 只允许 GetUser（取注册站点）；没有任何写操作；
- 每个店铺一个 access token（不带 scope 参数刷新 = 授权时同意的全部范围），过期前 120 秒重新获取；
  某类接口不在授权范围内时 eBay 返回 403，转成 EbayReadError(kind="NO_SCOPE")，报表里注明该店铺未授权；
- 不记录、不返回任何令牌，错误信息只保留 eBay 错误码和简短说明；
- 同一店铺、同一查询 10 分钟内重复提问直接用缓存，减少 eBay 调用额度消耗。
"""
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from backend.ebay_api.credentials import EbayApiError, EbayCredentials

LOG = logging.getLogger(__name__)
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
API_BASE = "https://api.ebay.com"
APIZ_BASE = "https://apiz.ebay.com"
TRADING_URL = "https://api.ebay.com/ws/api.dll"
TRADING_NS = "{urn:ebay:apis:eBLBaseComponents}"
CACHE_SECONDS = 600
STORE_LIST_SECONDS = 600
SITE_SECONDS = 24 * 3600
# GetUser 返回的注册站点 → REST 接口的 marketplace（香港等没有独立站点的按 eBay 默认 EBAY_US 处理）
SITE_MARKETPLACE = {"US": "EBAY_US", "UK": "EBAY_GB", "Germany": "EBAY_DE", "Australia": "EBAY_AU",
                    "France": "EBAY_FR", "Italy": "EBAY_IT", "Spain": "EBAY_ES", "Canada": "EBAY_CA",
                    "Austria": "EBAY_AT", "eBayMotors": "EBAY_US"}

KIND_TEXT = {
    "NO_SCOPE": "店铺授权里没有这类数据的权限（需重新授权）",
    "TOKEN_INVALID": "店铺秘钥失效",
    "SIGNATURE": "eBay 要求该店铺调用此接口时带数字签名（欧盟/英国卖家），暂不支持",
    "DENIED": "eBay 拒绝访问",
    "RATE_LIMIT": "eBay 限流或调用额度已用完，请稍后再试",
    "NOT_FOUND": "接口返回 404",
    "NETWORK": "连接 eBay 失败",
}


class EbayReadError(RuntimeError):
    def __init__(self, message: str, kind: str = "ERROR", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status

    @property
    def reason(self) -> str:
        return KIND_TEXT.get(self.kind, str(self)[:120])


@dataclass(frozen=True)
class StoreTarget:
    key: str  # browserId，Excel 内唯一
    name: str
    login: str
    credentials: EbayCredentials = field(repr=False, compare=False)


# ---------------------------------------------------------------- 店铺列表

_stores_lock = threading.Lock()
_stores_cache: tuple[float, list[StoreTarget]] | None = None


def store_targets(loader: Callable[[], dict] | None = None) -> list[StoreTarget]:
    global _stores_cache
    with _stores_lock:
        if _stores_cache and _stores_cache[0] > time.monotonic():
            return _stores_cache[1]
        if loader is None:
            from backend.ebay_api.workbook_accounts import read_workbook_accounts
            loader = read_workbook_accounts
        accounts = loader()["accounts"]
        stores = [StoreTarget(a["browser_id"], a["shop_name"], a.get("source_login") or "", a["_credentials"])
                  for a in accounts]
        _stores_cache = (time.monotonic() + STORE_LIST_SECONDS, stores)
        return stores


def pick_stores(stores: list[StoreTarget], keyword: str | None) -> list[StoreTarget]:
    """按店铺名称或账号包含匹配（不区分大小写）；不填返回全部。"""
    text = (keyword or "").strip().casefold()
    if not text:
        return stores
    return [s for s in stores if text in s.name.casefold() or text in s.login.casefold()]


# ---------------------------------------------------------------- 令牌与只读请求

_token_lock = threading.Lock()
_tokens: dict[str, tuple[str, float]] = {}
_sites: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()
_cache: dict[tuple, tuple[float, Any]] = {}


def clear_caches() -> None:
    global _stores_cache
    with _token_lock, _cache_lock, _stores_lock:
        _tokens.clear()
        _sites.clear()
        _cache.clear()
        _stores_cache = None


def cached(key: tuple, loader: Callable[[], Any], ttl: int = CACHE_SECONDS) -> Any:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (now + ttl, value)
        if len(_cache) > 2000:
            for stale in [k for k, (expires, _) in _cache.items() if expires <= now]:
                _cache.pop(stale, None)
    return value


class StoreReader:
    """一个店铺的只读调用；线程安全由「每个线程各建一个实例」保证，令牌缓存是进程级共享的。"""

    def __init__(self, store: StoreTarget, *, session: requests.Session | None = None, sleep=time.sleep):
        self.store = store
        self.session = session or requests.Session()
        self._sleep = sleep
        self.calls = 0

    # -------------------------------------------------- 底层请求

    def _send(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(3):
            try:
                self.calls += 1
                return self.session.request(method, url, timeout=(10, 60), allow_redirects=False, verify=True,
                                            **kwargs)
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError):
                # eBay 偶发 TLS 断连 / 超时：只重试原请求
                if attempt == 2:
                    raise EbayReadError("连接 eBay 失败（已重试 3 次）", "NETWORK") from None
                self._sleep(2 * (attempt + 1))
            except requests.RequestException:
                raise EbayReadError("eBay 请求失败", "NETWORK") from None
        raise EbayReadError("连接 eBay 失败", "NETWORK")

    def token(self, *, refresh: bool = False) -> str:
        key = self.store.key
        with _token_lock:
            hit = _tokens.get(key)
            if hit and not refresh and hit[1] > time.monotonic():
                return hit[0]
        cred = self.store.credentials
        resp = self._send("POST", TOKEN_URL, auth=(cred.client_id, cred.client_secret),
                          data={"grant_type": "refresh_token", "refresh_token": cred.refresh_token})
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code != 200 or not body.get("access_token"):
            error = str(body.get("error") or resp.status_code)
            kind = "TOKEN_INVALID" if error in ("invalid_grant", "invalid_client") else "ERROR"
            raise EbayReadError(f"店铺令牌刷新失败：{error}", kind, resp.status_code)
        expires = int(body.get("expires_in") or 0)
        with _token_lock:
            _tokens[key] = (body["access_token"], time.monotonic() + max(60, expires - 120))
        return body["access_token"]

    def get(self, path: str, params: dict | None = None, *, host: str = "api", marketplace: str | None = None,
            iaf: bool = False, retry_429: bool = True) -> dict:
        """只读 GET，返回 JSON。host="apiz" 用于 Finances 和付款纠纷；iaf=True 用于 Post-Order。"""
        url = (APIZ_BASE if host == "apiz" else API_BASE) + path
        params = {k: v for k, v in (params or {}).items() if v is not None}
        refreshed = False
        for attempt in range(4):
            headers = {"Authorization": f"{'IAF' if iaf else 'Bearer'} {self.token()}",
                       "Accept": "application/json", "Accept-Language": "en-US"}
            if marketplace:
                headers["X-EBAY-C-MARKETPLACE-ID"] = marketplace
            resp = self._send("GET", url, params=params, headers=headers)
            if resp.status_code == 200:
                return resp.json() if resp.content else {}
            if resp.status_code == 204:
                return {}
            if resp.status_code == 401 and not refreshed:
                self.token(refresh=True)
                refreshed = True
                continue
            if ((resp.status_code == 429 and retry_429) or resp.status_code >= 500) and attempt < 3:
                retry_after = resp.headers.get("Retry-After")
                self._sleep(min(20, int(retry_after)) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue
            raise read_error(path, resp)
        raise EbayReadError("eBay 接口重试次数用尽")

    def registration_marketplace(self) -> str:
        """店铺注册站点对应的 marketplace（Trading GetUser，每店每天最多查一次）。"""
        key = self.store.key
        hit = _sites.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
        resp = self._send("POST", TRADING_URL, data=(
            b'<?xml version="1.0" encoding="utf-8"?><GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
            b"</GetUserRequest>"), headers={
            "X-EBAY-API-CALL-NAME": "GetUser", "X-EBAY-API-IAF-TOKEN": self.token(),
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1193", "X-EBAY-API-SITEID": "0", "Content-Type": "text/xml"})
        site = ""
        try:
            if len(resp.content) < 2_000_000 and b"<!DOCTYPE" not in resp.content.upper():
                root = ET.fromstring(resp.content)
                site = (root.findtext(f"{TRADING_NS}User/{TRADING_NS}Site") or "").strip()
        except ET.ParseError:
            site = ""
        marketplace = SITE_MARKETPLACE.get(site, "EBAY_US")
        _sites[key] = (marketplace, time.monotonic() + SITE_SECONDS)
        return marketplace


def read_error(path: str, resp: requests.Response) -> EbayReadError:
    try:
        errors = resp.json().get("errors") or []
    except ValueError:
        errors = []
    ids = {int(e.get("errorId") or 0) for e in errors if str(e.get("errorId") or "").isdigit()}
    text = "；".join(f"{e.get('errorId')} {(e.get('message') or '')[:80]}".strip() for e in errors)[:200]
    message = f"{path} 返回 HTTP {resp.status_code}" + (f"：{text}" if text else "")
    joined = text.casefold()
    if any(215000 <= i < 216000 for i in ids) or "signature" in joined:
        return EbayReadError(message, "SIGNATURE", resp.status_code)
    if resp.status_code == 403 and ("insufficient" in joined or "scope" in joined or 1100 in ids):
        return EbayReadError(message, "NO_SCOPE", resp.status_code)
    kind = {401: "TOKEN_INVALID", 403: "DENIED", 404: "NOT_FOUND", 429: "RATE_LIMIT"}.get(resp.status_code, "ERROR")
    return EbayReadError(message, kind, resp.status_code)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def amount(node: dict | None) -> float:
    try:
        return float((node or {}).get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


def currency(node: dict | None) -> str | None:
    return (node or {}).get("currency")


__all__ = ["EbayApiError", "EbayReadError", "StoreReader", "StoreTarget", "amount", "cached", "clear_caches",
           "currency", "iso", "pick_stores", "store_targets"]
