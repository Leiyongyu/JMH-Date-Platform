"""eBay Browse API：竞品链接 → SOP ListingData + 图片列表。"""
from __future__ import annotations

import html
import re
import threading
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from backend.image_sop.config import Settings

OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
ITEM_BY_LEGACY_URL = "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id"

SITES = {
    "de": {"domain": "ebay.de", "marketplace": "EBAY_DE", "currency": "EUR"},
    "uk": {"domain": "ebay.co.uk", "marketplace": "EBAY_GB", "currency": "GBP"},
    "us": {"domain": "ebay.com", "marketplace": "EBAY_US", "currency": "USD"},
}

DOMAIN_TO_SITE = {
    "www.ebay.com": "us",
    "ebay.com": "us",
    "m.ebay.com": "us",
    "www.ebay.de": "de",
    "ebay.de": "de",
    "m.ebay.de": "de",
    "www.ebay.co.uk": "uk",
    "ebay.co.uk": "uk",
    "m.ebay.co.uk": "uk",
}

_ITEM_ID_RE = re.compile(r"^\d{6,19}$")
_QUERY_ID_KEYS = ("item", "itm", "item_id", "legacy_item_id", "epid")

_NON_PRODUCT_PATH_HINTS: tuple[tuple[str, str], ...] = (
    (r"/ebaylive/", "这是 eBay Live 直播链接，不是商品页。请在商品详情页复制地址栏链接（含 /itm/ 和数字 ID）"),
    (r"/sch/", "这是 eBay 搜索页链接，不是单个商品。请打开具体商品页再复制链接"),
    (r"/b/", "这是 eBay 店铺/分类页链接，不是商品页"),
    (r"/str/", "这是 eBay 店铺链接，不是商品页"),
    (r"/usr/", "这是 eBay 用户主页链接，不是商品页"),
    (r"/c/", "这是 eBay 分类页链接，不是商品页"),
    (r"/mye/", "这是 eBay 账户相关链接，不是商品页"),
)

OE_ASPECT_KEYS = (
    "oe/oem part number",
    "oe number",
    "oem part number",
    "manufacturer part number",
    "mpn",
    "reference oe/oem number",
    "other part number",
    "interchange part number",
)

# 这些 Item Specifics 字段可能含车型/年份，不能当作 OE 来源
_OE_ASPECT_EXCLUDE_KEY_FRAGMENTS = (
    "year",
    "years",
    "compatible",
    "fitment",
    "application",
    "vehicle",
    "make",
    "model",
    "engine",
    "notes",
    "note",
    "warranty",
    "condition",
    "placement",
    "brand",
)

_STRONG_OE_ASPECT_KEYS = frozenset(OE_ASPECT_KEYS)

_OE_NOISE_VALUES = frozenset({
    "na", "n/a", "none", "unknown", "see description", "does not apply",
})

_SKIP_ASPECT_KEYS = frozenset({
    "brand",
    "marke",
    "marque",
    "marca",
})

_DESC_STOP_HEADERS = (
    "shipping",
    "returns",
    "return policy",
    "feedback",
    "customer service",
    "payment",
    "warranty",
    "contact us",
    "about us",
    "terms and conditions",
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return "\n".join(self._parts)


class EbayListingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None
        self._token_expires = 0.0
        self._token_lock = threading.Lock()

    def is_configured(self) -> bool:
        return bool(self.settings.ebay_client_id and self.settings.ebay_client_secret)

    def parse_listing_from_url(self, url: str, site: str | None = None) -> dict[str, Any]:
        if not self.is_configured():
            raise ValueError("eBay API 未配置，请在 .env 中设置 EBAY_CLIENT_ID 和 EBAY_CLIENT_SECRET")
        parsed = self._parse_ebay_listing_url(url, site_override=site)
        item = self._fetch_item_by_legacy_id(parsed["legacy_item_id"], parsed["marketplace"])
        listing = self._build_listing_data(item, parsed["clean_url"], parsed["legacy_item_id"])
        images = self._extract_images(item)
        aspects = self._extract_aspect_pairs(item)
        return {
            "success": True,
            "source_url": parsed["clean_url"],
            "site": parsed["site"],
            "listing": listing,
            "images": images,
            "image_count": len(images),
            "item_specifics": [{"name": name, "value": value} for name, value in aspects],
            "short_description": self._html_to_text(str(item.get("shortDescription") or "")),
            "long_description": self._html_to_text(str(item.get("description") or "")),
        }

    def _get_access_token(self) -> str:
        with self._token_lock:
            if self._token and time.time() < self._token_expires:
                return self._token
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    OAUTH_URL,
                    data={
                        "grant_type": "client_credentials",
                        "scope": "https://api.ebay.com/oauth/api_scope",
                    },
                    auth=(self.settings.ebay_client_id, self.settings.ebay_client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                raise RuntimeError(f"eBay Token 失败 HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 7200) - 60
            return self._token

    def _fetch_item_by_legacy_id(self, legacy_item_id: str, marketplace: str) -> dict[str, Any]:
        token = self._get_access_token()
        params = {"legacy_item_id": legacy_item_id, "fieldgroups": "PRODUCT"}
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
            "X-EBAY-C-ENDUSERCTX": "affiliateCampaignId=<ePNCampaignId>,affiliateReferenceId=<referenceId>",
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(ITEM_BY_LEGACY_URL, params=params, headers=headers)
            if resp.status_code == 401:
                self._token = None
                headers["Authorization"] = f"Bearer {self._get_access_token()}"
                resp = client.get(ITEM_BY_LEGACY_URL, params=params, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"get_item_by_legacy_id HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    @staticmethod
    def _normalize_input_url(url: str) -> str:
        raw = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", (url or "").strip())
        raw = raw.strip("\"'")
        if not raw:
            return raw
        if _ITEM_ID_RE.fullmatch(raw):
            return raw
        if not re.match(r"^https?://", raw, re.I):
            if re.match(r"^(?:www\.)?ebay\.(?:com|de|co\.uk)(?:/|$)", raw, re.I):
                raw = "https://" + raw
            elif re.match(r"^ebay\.(?:com|de|co\.uk)/", raw, re.I):
                raw = "https://www." + raw
        return raw

    @staticmethod
    def _detect_site(host: str, site_override: str | None = None) -> str | None:
        if site_override:
            return site_override
        host = (host or "").lower()
        if host in DOMAIN_TO_SITE:
            return DOMAIN_TO_SITE[host]
        for domain, site in DOMAIN_TO_SITE.items():
            if host.endswith("." + domain) or host == domain:
                return site
        return None

    @classmethod
    def _extract_legacy_item_id(cls, raw: str, parsed) -> str | None:
        if _ITEM_ID_RE.fullmatch(raw):
            return raw

        query = parse_qs(parsed.query or "", keep_blank_values=False)
        for key in _QUERY_ID_KEYS:
            for value in query.get(key, []):
                token = str(value).strip()
                if _ITEM_ID_RE.fullmatch(token):
                    return token

        path = parsed.path or ""
        text = f"{path}?{parsed.query or ''}"

        patterns = (
            r"/itm/(?:[^/?#]+/)*(\d{6,19})(?:[/?#]|$)",
            r"/itm/(\d{6,19})(?:[/?#]|$)",
            r"/itm/[^/?#]*?(\d{6,19})(?:[/?#]|$)",
            r"(?:^|[?&])(?:item|itm)=(\d{6,19})(?:&|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1)

        match = re.search(r"(?:itm[=/]|item=)(\d{6,19})", raw, re.I)
        if match:
            return match.group(1)

        return None

    @classmethod
    def _non_product_url_hint(cls, raw: str, parsed) -> str | None:
        path = (parsed.path or "").lower()
        full = raw.lower()
        for pattern, hint in _NON_PRODUCT_PATH_HINTS:
            if re.search(pattern, path, re.I) or re.search(pattern, full, re.I):
                return hint
        if "/itm/" not in path and "/itm/" not in full and not _ITEM_ID_RE.fullmatch(raw.strip()):
            if "ebay." in (parsed.netloc or "").lower():
                return (
                    "当前链接不像商品详情页。"
                    "请打开 eBay 商品页，复制地址栏中以 /itm/ 开头且带数字 ID 的链接，"
                    "或直接输入 item 数字 ID（如 167628163700）"
                )
        return None

    @classmethod
    def _parse_ebay_listing_url(cls, url: str, site_override: str | None = None) -> dict[str, str]:
        raw = cls._normalize_input_url(url)
        if not raw:
            raise ValueError("URL 不能为空")

        if _ITEM_ID_RE.fullmatch(raw):
            site = site_override or "us"
            legacy_item_id = raw
            clean_url = f"https://{SITES[site]['domain']}/itm/{legacy_item_id}"
            return {
                "site": site,
                "legacy_item_id": legacy_item_id,
                "clean_url": clean_url,
                "marketplace": SITES[site]["marketplace"],
            }

        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if not host and parsed.path:
            reparsed = urlparse("https://" + raw.lstrip("/"))
            host = (reparsed.netloc or "").lower()
            if host:
                parsed = reparsed
                raw = reparsed.geturl()

        site = cls._detect_site(host, site_override)
        if not site:
            raise ValueError(f"无法识别 eBay 站点域名: {host or '(empty)'}")

        legacy_item_id = cls._extract_legacy_item_id(raw, parsed)
        if not legacy_item_id:
            hint = cls._non_product_url_hint(raw, parsed)
            if hint:
                raise ValueError(hint)
            raise ValueError(
                "URL 中未找到 eBay item id。"
                "请粘贴商品详情页链接（如 https://www.ebay.com/itm/167628163700）"
                "或直接输入 item 数字 ID"
            )

        clean_url = f"https://{SITES[site]['domain']}/itm/{legacy_item_id}"
        return {
            "site": site,
            "legacy_item_id": legacy_item_id,
            "clean_url": clean_url,
            "marketplace": SITES[site]["marketplace"],
        }

    @staticmethod
    def _upgrade_img(url: str, size: str = "s-l1600") -> str:
        if not url:
            return ""
        return re.sub(r"s-l\d+", size, url)

    def _extract_images(self, item: dict[str, Any]) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        seen: set[str] = set()

        def add(url: str, role: str) -> None:
            full = self._upgrade_img(url)
            if not full or full in seen:
                return
            seen.add(full)
            images.append({"url": full, "role": role})

        primary = (item.get("image") or {}).get("imageUrl") or ""
        if primary:
            add(primary, "primary")
        for group_key in ("additionalImages", "thumbnailImages"):
            for img in item.get(group_key) or []:
                add((img or {}).get("imageUrl") or "", group_key)
        return images

    @staticmethod
    def _normalize_key(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    @classmethod
    def _should_skip_aspect(cls, name: str) -> bool:
        norm = cls._normalize_key(name)
        return norm in _SKIP_ASPECT_KEYS or norm.startswith("brand")

    def _extract_aspect_pairs(self, item: dict[str, Any]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for group in item.get("localizedAspects") or []:
            name = str(group.get("name") or "").strip()
            value = str(group.get("value") or "").strip()
            if name and value and not self._should_skip_aspect(name):
                pairs.append((name, value))
        for group in item.get("aspectGroups") or []:
            for aspect in group.get("aspects") or []:
                name = str(aspect.get("localizedName") or aspect.get("name") or "").strip()
                if self._should_skip_aspect(name):
                    continue
                for value in aspect.get("localizedValues") or aspect.get("values") or []:
                    val = str(value).strip()
                    if name and val:
                        pairs.append((name, val))
        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for pair in pairs:
            key = (self._normalize_key(pair[0]), self._normalize_key(pair[1]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(pair)
        return deduped

    def _extract_bullet_points(self, item: dict[str, Any]) -> list[str]:
        aspects = self._extract_aspect_pairs(item)
        bullets = [f"{name}: {value}" for name, value in aspects]

        long_desc = self._trim_seller_boilerplate(
            self._html_to_text(str(item.get("description") or ""))
        )
        for line in self._extract_section_bullets(long_desc):
            bullets.append(line)

        short_desc = self._html_to_text(str(item.get("shortDescription") or ""))
        if short_desc and not long_desc:
            bullets.extend(line.strip() for line in short_desc.splitlines() if line.strip())

        deduped: list[str] = []
        seen: set[str] = set()
        for bullet in bullets:
            if re.match(r"^brand\s*[:：]", bullet, re.I):
                continue
            key = self._normalize_key(bullet)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(bullet.strip())
        return deduped[:30]

    @staticmethod
    def _trim_seller_boilerplate(text: str) -> str:
        if not text.strip():
            return ""
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            header = re.sub(r"[:：]\s*$", "", stripped.lower())
            if header in _DESC_STOP_HEADERS:
                break
            if header.startswith("we do our best to ship"):
                break
            lines.append(stripped)
        cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip())
        return cleaned

    @staticmethod
    def _extract_section_bullets(text: str) -> list[str]:
        if not text.strip():
            return []
        bullets: list[str] = []

        function_match = re.search(
            r"Function\s*[:：]?\s*(.+?)(?=\n\s*(?:Features?|Specification|Fitment|Package|Note|Shipping)\b|\Z)",
            text,
            re.I | re.S,
        )
        if function_match:
            function_text = re.sub(r"\s+", " ", function_match.group(1)).strip(" ,;:-")
            if function_text:
                bullets.append(f"Function: {function_text}")

        features_match = re.search(
            r"Features?\s*[:：]?\s*\n(.+?)(?=\n\s*(?:Specification|Fitment|Package|Note|Shipping)\b|\Z)",
            text,
            re.I | re.S,
        )
        if features_match:
            for line in features_match.group(1).splitlines():
                cleaned = re.sub(r"^\d+[.)]\s*", "", line.strip())
                cleaned = cleaned.lstrip("-•* ").strip()
                if cleaned and len(cleaned) > 2:
                    bullets.append(cleaned)

        spec_match = re.search(
            r"Specification\s*[:：]?\s*\n(.+?)(?=\n\s*(?:Fitment|Package|Note|Shipping)\b|\Z)",
            text,
            re.I | re.S,
        )
        if spec_match:
            for line in spec_match.group(1).splitlines():
                cleaned = line.strip().lstrip("-•* ").strip()
                if cleaned:
                    bullets.append(cleaned)

        for section_name in ("Fitment", "Package Included", "Note"):
            section_match = re.search(
                rf"{section_name}\s*[:：]?\s*\n(.+?)(?=\n\s*(?:Fitment|Package Included|Note|Shipping|Returns|Feedback)\b|\Z)",
                text,
                re.I | re.S,
            )
            if section_match:
                block = re.sub(r"\s+", " ", section_match.group(1)).strip()
                if block:
                    bullets.append(f"{section_name}: {block}")

        return bullets

    def _build_full_description(
        self,
        item: dict[str, Any],
        aspects: list[tuple[str, str]],
    ) -> str:
        short_desc = self._html_to_text(str(item.get("shortDescription") or ""))
        long_desc = self._trim_seller_boilerplate(
            self._html_to_text(str(item.get("description") or ""))
        )

        parts: list[str] = []
        if long_desc:
            if aspects:
                parts.append("Item specifics:")
                for name, value in aspects[:30]:
                    parts.append(f"- {name}: {value}")
            parts.append(long_desc)
        elif short_desc:
            if aspects:
                parts.append("Item specifics:")
                for name, value in aspects[:30]:
                    parts.append(f"- {name}: {value}")
            parts.append(short_desc)
        else:
            if aspects:
                parts.append("Item specifics:")
                for name, value in aspects[:30]:
                    parts.append(f"- {name}: {value}")

        description = re.sub(r"\n{3,}", "\n\n", "\n\n".join(part for part in parts if part.strip()))
        description = re.sub(r"\ufffd+", ", ", description)
        description = re.sub(r",\s*,+", ", ", description)
        return description[:12000]

    @staticmethod
    def _is_year_token(token: str) -> bool:
        cleaned = token.strip()
        if re.fullmatch(r"\d{4}", cleaned):
            year = int(cleaned)
            return 1900 <= year <= 2039
        return False

    @classmethod
    def _aspect_is_oe_source(cls, name: str) -> bool:
        norm = cls._normalize_key(name)
        if norm in _STRONG_OE_ASPECT_KEYS:
            return True
        if any(fragment in norm for fragment in _OE_ASPECT_EXCLUDE_KEY_FRAGMENTS):
            return False
        if "part number" in norm or norm == "mpn":
            return any(
                marker in norm
                for marker in ("oe", "oem", "manufacturer", "interchange", "reference", "other")
            )
        return False

    @classmethod
    def _looks_like_oe_part_number(cls, token: str) -> bool:
        cleaned = token.strip().strip(".,;")
        if not cleaned or len(cleaned) < 4 or len(cleaned) > 32:
            return False
        lowered = cleaned.lower()
        if lowered in _OE_NOISE_VALUES:
            return False
        if re.fullmatch(r"\d{4}\s*-\s*\d{4}", cleaned):
            return False
        if cls._is_year_token(cleaned):
            return False
        if re.fullmatch(r"[A-Za-z]+", cleaned):
            return False
        if not re.search(r"\d", cleaned):
            return False
        if re.search(r"[A-Za-z]", cleaned):
            return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9\-./]*", cleaned, re.I))
        if re.fullmatch(r"\d+", cleaned):
            return len(cleaned) >= 5
        return bool(re.fullmatch(r"[A-Z0-9\-./]{4,32}", cleaned, re.I))

    def _extract_oe_numbers(self, item: dict[str, Any]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            for part in re.split(r"[,;/|]+", value):
                chunk = part.strip()
                if not chunk:
                    continue
                if re.search(r"[A-Za-z]", chunk):
                    tokens = [chunk]
                else:
                    tokens = [p.strip() for p in re.split(r"\s*-\s*", chunk) if p.strip()]
                for token in tokens:
                    if not self._looks_like_oe_part_number(token):
                        continue
                    key = token.upper()
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(token)

        for name, value in self._extract_aspect_pairs(item):
            if not self._aspect_is_oe_source(name):
                continue
            add(value)

        return found[:30]

    def _extract_keywords(self, item: dict[str, Any]) -> list[str]:
        keyword_aspects = {
            "type",
            "placement on vehicle",
            "fitment type",
            "fitment",
            "features",
            "colour",
            "color",
            "manufacturer part number",
        }
        keywords: list[str] = []
        for name, value in self._extract_aspect_pairs(item):
            if self._normalize_key(name) in keyword_aspects:
                keywords.append(value)
        title = str(item.get("title") or "").strip()
        if title:
            keywords.insert(0, title)
        deduped: list[str] = []
        seen: set[str] = set()
        for word in keywords:
            key = word.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(word)
        return deduped[:20]

    @staticmethod
    def _html_to_text(raw: str) -> str:
        text = html.unescape(raw or "")
        if not text.strip():
            return ""
        text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
        parser = _HTMLTextExtractor()
        parser.feed(text)
        parser.close()
        cleaned = parser.text()
        if cleaned.strip():
            return re.sub(r"\n{3,}", "\n\n", cleaned.strip())
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()

    def _build_listing_data(self, item: dict[str, Any], source_url: str, legacy_item_id: str) -> dict[str, Any]:
        title = str(item.get("title") or "").strip()
        aspects = self._extract_aspect_pairs(item)
        description = self._build_full_description(item, aspects)
        return {
            "sku": "",
            "asin": "",
            "asin_url": source_url,
            "title": title,
            "bullet_points": self._extract_bullet_points(item),
            "description": description,
            "keywords": self._extract_keywords(item),
            "oe_numbers": self._extract_oe_numbers(item),
            "listing_tags": [],
            "scrape_status": "ok",
            "scrape_reason": "",
            "scrape_action": "",
            "data_source": "ebay_browse_api",
            "source_updated_at": "",
        }

    def _build_item_meta(self, item: dict[str, Any], site: str) -> dict[str, Any]:
        price_info = item.get("price") or {}
        seller = item.get("seller") or {}
        return {
            "legacy_item_id": str(item.get("legacyItemId") or ""),
            "restful_item_id": str(item.get("itemId") or ""),
            "site": site,
            "price": price_info.get("value"),
            "currency": price_info.get("currency") or SITES[site]["currency"],
            "condition": item.get("condition") or "",
            "seller": seller.get("username") or "",
            "seller_feedback": seller.get("feedbackPercentage") or "",
            "item_web_url": item.get("itemWebUrl") or "",
            "buying_options": item.get("buyingOptions") or [],
        }
