from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config import settings


SITES = {
    "de": {"marketplace": "EBAY_DE", "currency": "EUR"},
    "uk": {"marketplace": "EBAY_GB", "currency": "GBP"},
    "us": {"marketplace": "EBAY_US", "currency": "USD"},
}

OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


@dataclass
class EbayToken:
    access_token: str
    expires_at: float


class EbayBrowseClient:
    def __init__(self) -> None:
        self.client_id = settings.ebay_client_id
        self.client_secret = settings.ebay_client_secret
        self.timeout = settings.ebay_request_timeout_sec
        self._token: EbayToken | None = None
        self._token_lock = Lock()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def search_items(self, keyword: str, site: str, limit: int) -> dict[str, Any]:
        if site not in SITES:
            raise ValueError("不支持的 eBay 站点")
        token = self._get_access_token()
        params = {
            "q": keyword,
            "limit": min(max(limit, 1), 200),
            "offset": 0,
            "filter": "conditions:{NEW}",
            "fieldgroups": "MATCHING_ITEMS",
        }
        url = f"{BROWSE_SEARCH_URL}?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": SITES[site]["marketplace"],
            "X-EBAY-C-ENDUSERCTX": "affiliateCampaignId=<ePNCampaignId>,affiliateReferenceId=<referenceId>",
        }
        return self._request_json(Request(url, headers=headers, method="GET"))

    def _get_access_token(self) -> str:
        if not self.is_configured():
            raise ValueError("eBay配置不完整，请设置 EBAY_CLIENT_ID、EBAY_CLIENT_SECRET")
        with self._token_lock:
            if self._token and time.time() < self._token.expires_at:
                return self._token.access_token
            token = self._fetch_access_token()
            self._token = token
            return token.access_token

    def _fetch_access_token(self) -> EbayToken:
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            }
        ).encode("utf-8")
        request = Request(
            OAUTH_URL,
            data=body,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        payload = self._request_json(request)
        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise ValueError("eBay token 响应缺少 access_token")
        expires_in = _int_value(payload.get("expires_in"), 7200)
        return EbayToken(access_token, time.time() + max(expires_in - 60, 60))

    def _request_json(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"eBay API 返回错误 (HTTP {exc.code}): {payload[:500]}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"eBay API 请求失败: {exc}") from exc


def format_item(item: dict[str, Any]) -> dict[str, Any]:
    price_info = item.get("price") or {}
    price_value = _float_value(price_info.get("value"))
    currency = price_info.get("currency") or ""
    images = _images(item)
    shipping = ""
    shipping_options = item.get("shippingOptions") or []
    if shipping_options:
        shipping_cost = (shipping_options[0] or {}).get("shippingCost") or {}
        if shipping_cost:
            ship_value = _float_value(shipping_cost.get("value"))
            ship_currency = shipping_cost.get("currency") or currency
            shipping = f"{ship_value:.2f} {ship_currency}" if ship_value > 0 else "免运费"
    seller = item.get("seller") or {}
    return {
        "title": item.get("title") or "",
        "price": f"{price_value:.2f} {currency}".strip(),
        "pf": price_value,
        "currency": currency,
        "condition": item.get("condition") or "",
        "conditionId": item.get("conditionId") or "",
        "images": images,
        "link": _clean_item_url(item.get("itemWebUrl") or ""),
        "itemId": item.get("itemId") or "",
        "seller": seller.get("username") or "",
        "sellerFeedback": seller.get("feedbackPercentage") or "",
        "shipping": shipping,
        "buyingOptions": item.get("buyingOptions") or [],
    }


def _images(item: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen = set()
    for group in (item.get("thumbnailImages") or [], item.get("additionalImages") or []):
        for image in group:
            url = _upgrade_image((image or {}).get("imageUrl") or "")
            if url and url not in seen:
                seen.add(url)
                result.append(url)
    primary = (item.get("image") or {}).get("imageUrl") or ""
    primary = _upgrade_image(primary)
    if primary and primary not in seen:
        result.append(primary)
    return result[:5]


def _clean_item_url(url: str) -> str:
    index = url.find("/itm/")
    if index < 0:
        return url
    item_part = url[index + 5 :]
    for marker in ("?", "#"):
        marker_index = item_part.find(marker)
        if marker_index >= 0:
            item_part = item_part[:marker_index]
    return url[: index + 5] + item_part


def _upgrade_image(url: str) -> str:
    import re

    return re.sub(r"s-l\d+", "s-l500", url) if url else url


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
