from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

import httpx

from backend.image_sop.config import Settings
from backend.image_sop.models import ListingData
from backend.image_sop.services.lingxing_auth import LingxingAuthClient, LingxingAuthError

HTML_TAG_RE = re.compile(r"<[^>]+>")
OE_LABEL_PATTERN = re.compile(
    r"(?:OEM\s*(?:Part\s*(?:Number|No\.?|#)?|#|Number|No\.?)|"
    r"OE\s*(?:Part\s*(?:Number|No\.?|#)?|#|Number|No\.?)|"
    r"Part\s*(?:Number|No\.?|#)|"
    r"Replaces?|Replace\s+for)"
    r"[:：]?\s*"
    r"([A-Z0-9][A-Z0-9\-./]*(?:\s*/\s*[A-Z0-9][A-Z0-9\-./]*)*)",
    re.IGNORECASE,
)
NUMERIC_PART_PATTERN = re.compile(r"\b(\d{7,14})\b")
INVALID_OE_VALUES = {
    "style",
    "direct",
    "replacement",
    "new",
    "oem",
    "fit",
    "quality",
    "notice",
    "function",
    "compatibility",
    "compatible",
}
OE_ATTRIBUTE_KEYS = (
    "part_number",
    "model_number",
    "manufacturer_part_number",
    "item_model_number",
    "model_name",
)


class LingxingService:
    _shared_us_sids_cache: list[int] | None = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._auth_client: LingxingAuthClient | None = None

    async def list_amazon_stores(self) -> list[dict[str, Any]]:
        """返回全部亚马逊店铺列表（领星 seller/lists），供前端多人使用时选择。"""
        if self.settings.lingxing_use_mock:
            return [
                {
                    "sid": 1,
                    "name": "Mock-Store-US",
                    "country": "美国",
                    "region": "NA",
                },
                {
                    "sid": 2,
                    "name": "Mock-Store-EU",
                    "country": "德国",
                    "region": "EU",
                },
            ]

        try:
            result = await self._get_json(self.settings.lingxing_sellers_path, {})
        except LingxingAuthError as exc:
            raise ValueError(f"领星店铺列表获取失败: {exc}") from exc

        if result.get("code") not in (0, "0"):
            message = result.get("message") or result.get("msg") or "未知错误"
            raise ValueError(f"领星店铺列表返回异常: {message}")

        stores: list[dict[str, Any]] = []
        data = result.get("data") or []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                sid_value = int(item.get("sid", 0) or 0)
                if sid_value <= 0:
                    continue
                status = int(item.get("status", 1) or 1)
                if status not in (1,):
                    continue
                name = str(
                    self._pick_value(item, "name", "seller_name", "store_name") or ""
                ).strip()
                country = str(item.get("country", "")).strip()
                region = str(item.get("region", "")).strip()
                marketplace_id = str(item.get("marketplace_id", "")).strip()
                stores.append(
                    {
                        "sid": sid_value,
                        "name": name or f"店铺 {sid_value}",
                        "country": country,
                        "region": region,
                        "marketplace_id": marketplace_id,
                    }
                )

        stores.sort(
            key=lambda row: (
                str(row.get("region", "")).upper(),
                str(row.get("country", "")),
                str(row.get("name", "")).lower(),
            )
        )
        return stores

    async def get_listing_by_sku(self, sku: str, sid: int | None = None) -> ListingData:
        if self.settings.lingxing_use_mock:
            return self._mock_listing(sku)
        return await self._fetch_real_listing(sku, sid)

    async def query_listing_relation_tags(self, sku: str, sid: int | None = None) -> list[str]:
        if self.settings.lingxing_use_mock:
            return ["汽配热销", "高复购"]
        return await self._fetch_relation_tags(sku, sid)

    async def query_vc_listing_page(
        self,
        offset: int = 0,
        length: int = 20,
        vc_store_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if offset < 0:
            raise ValueError("offset 不能小于 0")
        if length <= 0 or length > 200:
            raise ValueError("length 必须在 1~200 之间")

        resolved_store_ids = self._resolve_vc_store_ids(vc_store_ids)
        if self.settings.lingxing_use_mock:
            return {
                "code": 0,
                "message": "success",
                "error_details": [],
                "request_id": "mock-vc-listing",
                "response_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "total": 1,
                "data": [
                    {
                        "vc_store_id": resolved_store_ids[0] if resolved_store_ids else "134225003201380860",
                        "asin": "B097MP26YP",
                        "msku": "HOLDER001",
                        "local_sku": "SKUZHCG",
                        "item_name": "Mock Listing Title",
                        "small_min_image_url": "https://example.com/mock.jpg",
                        "principal_list": [{"uid": "100003", "real_name": "jack"}],
                    }
                ],
            }

        url = f"{self.settings.lingxing_api_base.rstrip('/')}{self.settings.lingxing_vc_listing_page_path}"
        payload: dict[str, Any] = {"offset": offset, "length": length}
        if resolved_store_ids:
            payload["vc_store_ids"] = resolved_store_ids

        return await self._post_json(self.settings.lingxing_vc_listing_page_path, payload)

    async def query_amazon_listing(self, payload: dict[str, Any]) -> dict[str, Any]:
        sid = str(payload.get("sid", "")).strip()
        if not sid:
            raise ValueError("sid 不能为空，格式如 '1,16'")

        length = int(payload.get("length", self.settings.lingxing_amazon_listing_default_length))
        offset = int(payload.get("offset", 0))
        if length <= 0 or length > 1000:
            raise ValueError("length 必须在 1~1000 之间")
        if offset < 0:
            raise ValueError("offset 不能小于 0")

        request_payload: dict[str, Any] = {"sid": sid, "offset": offset, "length": length}
        optional_keys = [
            "is_pair",
            "is_delete",
            "pair_update_start_time",
            "pair_update_end_time",
            "listing_update_start_time",
            "listing_update_end_time",
            "search_field",
            "search_value",
            "exact_search",
            "store_type",
        ]
        for key in optional_keys:
            value = payload.get(key)
            if value not in (None, "", []):
                request_payload[key] = value

        if self.settings.lingxing_use_mock:
            return {
                "code": 0,
                "message": "success",
                "error_details": [],
                "request_id": "mock-amazon-listing",
                "response_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "total": 1,
                "data": [
                    {
                        "sid": int(sid.split(",")[0]),
                        "seller_sku": request_payload.get("search_value", ["HOLDER001"])[0],
                        "asin": "B0GWJ47NFS",
                        "item_name": "3D Printed T-Rex Action Figure",
                        "small_image_url": "https://example.com/mock-listing.jpg",
                        "global_tags": [{"tagName": "测试标签", "color": "#3BB84C"}],
                    }
                ],
            }

        return await self._post_json(self.settings.lingxing_amazon_listing_path, request_payload)

    async def query_amazon_product_search(
        self, store_id: int, skus: list[str]
    ) -> dict[str, Any]:
        if store_id <= 0:
            raise ValueError("store_id 必须是正整数")
        cleaned_skus = [str(v).strip() for v in skus if str(v).strip()]
        if not cleaned_skus:
            raise ValueError("skus 不能为空")
        if len(cleaned_skus) > 20:
            raise ValueError("skus 最多支持 20 个")

        if self.settings.lingxing_use_mock:
            sku = cleaned_skus[0]
            return {
                "code": 1,
                "msg": "成功",
                "data": [
                    {
                        "msku": sku,
                        "info": {
                            "summaries": [
                                {
                                    "asin": "B0DH2CQ1XV",
                                    "itemName": f"{sku} Replacement Pulley Sheave Kit",
                                }
                            ],
                            "attributes": {
                                "item_name": [{"value": f"{sku} Replacement Pulley Sheave Kit"}],
                                "bullet_point": [
                                    {"value": "Heavy-duty alloy structure for long service life."},
                                    {"value": "Direct-fit design, no special tools required."},
                                    {"value": "Stable performance in high-frequency lifting scenarios."},
                                ],
                                "generic_keyword": [{"value": "pulley sheave lift repair kit"}],
                                "product_description": [
                                    {"value": "<p>Engineered for garage lift maintenance tasks.</p>"}
                                ],
                            },
                        },
                    }
                ],
                "request_id": "mock-amazon-product-search",
            }

        payload = {"store_id": int(store_id), "skus": cleaned_skus}
        return await self._post_json(self.settings.lingxing_amazon_product_search_path, payload)

    async def batch_assign_listing_principal(
        self, sid_asin_list: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not sid_asin_list:
            raise ValueError("sid_asin_list 不能为空")
        if len(sid_asin_list) > 200:
            raise ValueError("sid_asin_list 最多支持 200 条")

        cleaned: list[dict[str, Any]] = []
        for index, item in enumerate(sid_asin_list):
            sid = int(item.get("sid", 0))
            asin = str(item.get("asin", "")).strip()
            principals = item.get("principal_name", [])
            if sid <= 0:
                raise ValueError(f"第{index + 1}条 sid 必须是正整数")
            if not asin:
                raise ValueError(f"第{index + 1}条 asin 不能为空")
            if principals is None:
                principals = []
            if not isinstance(principals, list):
                raise ValueError(f"第{index + 1}条 principal_name 必须是数组")
            cleaned.append(
                {
                    "sid": sid,
                    "asin": asin,
                    "principal_name": [str(v).strip() for v in principals if str(v).strip()],
                }
            )

        if self.settings.lingxing_use_mock:
            total = len(cleaned)
            return {
                "code": 0,
                "message": "success",
                "error_details": [],
                "data": {"total": total, "success": total, "error": 0},
                "request_id": "mock-request-id",
                "response_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }

        payload = {"sid_asin_list": cleaned}
        return await self._post_json(self.settings.lingxing_update_principal_path, payload)

    async def _fetch_real_listing(self, sku: str, sid: int | None = None) -> ListingData:
        if not self.settings.lingxing_api_base:
            raise ValueError("领星配置缺失，请设置 LINGXING_API_BASE")

        listing_item: dict[str, Any] = {}
        result_payload: dict[str, Any] = {"data": []}
        matched_sid = sid

        query_sid = await self._resolve_query_sid(sid)
        if not query_sid:
            raise ValueError("未找到美国站店铺，请在 .env 配置 LINGXING_US_SIDS 或检查领星店铺授权")

        amazon_result = await self.query_amazon_listing(
            {
                "sid": query_sid,
                "search_field": "seller_sku",
                "search_value": [sku],
                "exact_search": 1,
                "offset": 0,
                "length": 20,
            }
        )
        if amazon_result.get("code") in (0, "0"):
            listing_item = self._pick_listing_item(amazon_result, sku)
            result_payload = amazon_result
            if listing_item and matched_sid is None:
                matched_sid = self._extract_sid_from_item(listing_item)

        if not listing_item:
            result_payload = await self._fetch_listing_payload_by_sku(sku)
            listing_item = self._extract_first_record(result_payload)
        if not listing_item:
            listing_item = await self._find_listing_item_from_vc_pages(sku)
            result_payload = {"data": [listing_item]} if listing_item else {"data": []}

        if not listing_item:
            if sid is not None and sid > 0:
                raise ValueError(
                    f"在所选店铺（sid={sid}）未找到 SKU：{sku}，请确认 MSKU 与该店铺匹配"
                )
            raise ValueError(f"未找到 SKU：{sku}，请确认领星中已存在该 seller_sku")

        if matched_sid is None:
            matched_sid = self._extract_sid_from_item(listing_item)

        listing = await self._build_listing_data(sku, result_payload, matched_sid)
        relation_id = str(self._pick_value(listing_item, "msku", "seller_sku", "relation_id") or sku).strip()
        relation_tags = await self._fetch_relation_tags(relation_id, matched_sid)
        if relation_tags:
            listing.listing_tags = relation_tags
        source_global_tags = self._extract_global_tag_names(listing_item)
        if source_global_tags:
            listing.listing_tags = self._dedupe_list(listing.listing_tags + source_global_tags)
        if not listing.data_source:
            listing.data_source = "lingxing_api"
        return listing

    async def _fetch_listing_payload_by_sku(self, sku: str) -> dict[str, Any]:
        payload = {self.settings.lingxing_sku_param_name: sku}
        method = self.settings.lingxing_request_method.upper()
        path = self.settings.lingxing_sku_query_path

        if method == "GET":
            return await self._get_json(path, payload)
        if method == "POST":
            return await self._post_json(path, payload)
        raise ValueError(f"不支持的领星请求方法: {method}")

    async def _find_listing_item_from_vc_pages(self, sku: str) -> dict[str, Any]:
        length = max(1, min(200, int(self.settings.lingxing_vc_fallback_page_length)))
        max_pages = max(1, int(self.settings.lingxing_vc_fallback_max_pages))
        for page in range(max_pages):
            offset = page * length
            payload = await self.query_vc_listing_page(offset=offset, length=length)
            if payload.get("code") not in (0, "0"):
                continue
            data = payload.get("data") or []
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                candidates = [
                    str(self._pick_value(item, "local_sku", "msku", "seller_sku", "relation_id") or "").strip(),
                ]
                if any(v and v.lower() == sku.lower() for v in candidates):
                    return item
            total = int(payload.get("total", 0) or 0)
            if offset + length >= total:
                break
        return {}

    async def _build_listing_data(
        self,
        sku: str,
        listing_payload: dict[str, Any],
        sid: int | None = None,
        product_record: dict[str, Any] | None = None,
    ) -> ListingData:
        listing_item = self._extract_first_record(listing_payload)
        asin = self._extract_asin(listing_item)
        asin_url = self._normalize_us_asin_url("", asin)

        if product_record is None:
            product_record = await self._fetch_amazon_product_info(sku, sid)
        product_info: dict[str, Any] = {}
        if isinstance(product_record, dict) and product_record:
            raw_info = product_record.get("info")
            if isinstance(raw_info, dict):
                product_info = raw_info
        attributes = product_info.get("attributes") if isinstance(product_info.get("attributes"), dict) else {}
        parsed = self._parse_amazon_product_info(product_info if isinstance(product_info, dict) else {})

        if parsed.get("asin"):
            asin = parsed["asin"]
            asin_url = self._normalize_us_asin_url("", asin)

        title = str(
            parsed.get("title")
            or self._pick_from_sources([listing_item], "item_name", "title", "product_title", "listing_title", "name")
            or ""
        ).strip()
        bullet_points = parsed.get("bullet_points") or []
        description = str(parsed.get("description") or "").strip()
        keywords = parsed.get("keywords") or []

        corpus = " ".join([title, description, " ".join(bullet_points)])
        oe_numbers = self._extract_oe_numbers(corpus, attributes=attributes)

        listing = ListingData(
            sku=sku,
            asin=asin,
            asin_url=asin_url,
            title=title,
            bullet_points=[str(v).strip() for v in bullet_points if str(v).strip()],
            description=description,
            keywords=[str(v).strip() for v in keywords if str(v).strip()],
            oe_numbers=oe_numbers,
            scrape_status="skipped" if product_record else "failed",
            scrape_reason=(
                "已通过领星「查询已有商品信息」接口获取五点/描述/关键词"
                if product_record
                else "未从领星「查询已有商品信息」接口获取到 MSKU 详情"
            ),
            scrape_action="无需处理" if product_record else "请确认 store_id/sid 与 MSKU 是否正确",
            data_source="lingxing_product_search" if product_record else "lingxing_api",
            source_updated_at=str(
                self._pick_value(
                    listing_item,
                    "listing_update_time",
                    "listing_updated_at",
                    "update_time",
                    "updated_at",
                    "pair_update_time",
                )
                or ""
            ).strip(),
        )
        return listing

    async def compose_listing_from_amazon_records(
        self,
        sku: str,
        listing_item: dict[str, Any],
        sid: int | None = None,
        product_record: dict[str, Any] | None = None,
    ) -> ListingData:
        """由亚马逊 listing 行 + 商品详情记录组装 ListingData（供远程后台组合查询）。"""
        payload = {"data": [listing_item]}
        listing = await self._build_listing_data(
            sku,
            payload,
            sid=sid,
            product_record=product_record if product_record is not None else {},
        )
        relation_id = str(
            self._pick_value(listing_item, "msku", "seller_sku", "relation_id") or sku
        ).strip()
        relation_tags = await self._fetch_relation_tags(relation_id, sid)
        if relation_tags:
            listing.listing_tags = relation_tags
        source_global_tags = self._extract_global_tag_names(listing_item)
        if source_global_tags:
            listing.listing_tags = self._dedupe_list(listing.listing_tags + source_global_tags)
        if not listing.data_source:
            listing.data_source = "lingxing_api"
        return listing

    async def _fetch_amazon_product_info(self, sku: str, sid: int | None = None) -> dict[str, Any]:
        store_id = self._resolve_store_id(sid)
        if store_id <= 0:
            return {}

        try:
            result = await self.query_amazon_product_search(store_id, [sku])
        except (LingxingAuthError, ValueError):
            return {}

        if result.get("code") not in (1, "1"):
            return {}

        data = result.get("data") or []
        if not isinstance(data, list):
            return {}

        normalized = sku.strip().lower()
        for item in data:
            if not isinstance(item, dict):
                continue
            msku = str(item.get("msku", "")).strip().lower()
            if msku == normalized:
                return item
        return data[0] if data and isinstance(data[0], dict) else {}

    def _parse_amazon_product_info(self, info: dict[str, Any]) -> dict[str, Any]:
        attributes = info.get("attributes") if isinstance(info.get("attributes"), dict) else {}
        summaries = info.get("summaries") if isinstance(info.get("summaries"), list) else []

        title = self._extract_attribute_text(attributes, "item_name")
        asin = ""
        if summaries and isinstance(summaries[0], dict):
            summary = summaries[0]
            asin = str(summary.get("asin", "")).strip()
            if not title:
                title = str(summary.get("itemName", "")).strip()

        bullet_points = self._extract_attribute_list(attributes, "bullet_point")
        description = self._strip_html(self._extract_attribute_text(attributes, "product_description"))
        keywords = self._extract_keywords(attributes)

        return {
            "title": title,
            "asin": asin,
            "bullet_points": bullet_points,
            "description": description,
            "keywords": keywords,
        }

    def _extract_attribute_list(self, attributes: dict[str, Any], key: str) -> list[str]:
        entries = attributes.get(key)
        if not isinstance(entries, list):
            return []
        values: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("value", "")).strip()
            if text:
                values.append(text)
        return values

    def _extract_attribute_text(self, attributes: dict[str, Any], key: str) -> str:
        values = self._extract_attribute_list(attributes, key)
        return values[0] if values else ""

    def _extract_keywords(self, attributes: dict[str, Any]) -> list[str]:
        raw_values = self._extract_attribute_list(attributes, "generic_keyword")
        keywords: list[str] = []
        for value in raw_values:
            text = value.strip()
            if not text:
                continue
            if re.search(r"[\n,，;；|/]", text):
                parts = re.split(r"[\n,，;；|/]+", text)
            else:
                parts = [text]
            for part in parts:
                chunk = part.strip()
                if chunk and not self._is_operational_tag(chunk):
                    keywords.append(chunk)
        return self._dedupe_list(keywords)

    @staticmethod
    def _is_operational_tag(text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return True
        operational = {"新品", "热销", "清仓", "滞销", "重点", "new", "hot", "sale"}
        return lowered in operational or len(text.strip()) <= 2

    def _strip_html(self, text: str) -> str:
        cleaned = HTML_TAG_RE.sub(" ", unescape(text or ""))
        return re.sub(r"\s+", " ", cleaned).strip()

    def _extract_oe_numbers(self, text: str, attributes: dict[str, Any] | None = None) -> list[str]:
        found: list[str] = []
        if attributes:
            found.extend(self._extract_oe_from_attributes(attributes))
        if text:
            for match in OE_LABEL_PATTERN.finditer(text):
                found.extend(self._split_oe_chunk(match.group(1)))
            for match in NUMERIC_PART_PATTERN.finditer(text):
                found.append(match.group(1))
        return self._dedupe_list([value for value in found if self._is_valid_oe_number(value)])

    def _extract_oe_from_attributes(self, attributes: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in OE_ATTRIBUTE_KEYS:
            for text in self._extract_attribute_list(attributes, key):
                values.extend(self._split_oe_chunk(text))
        return values

    @staticmethod
    def _split_oe_chunk(raw: str) -> list[str]:
        parts: list[str] = []
        for chunk in re.split(r"\s*/\s*", raw or ""):
            for piece in re.split(r"[,，;；\s]+", chunk):
                text = piece.strip(" ,.;")
                if text:
                    parts.append(text)
        return parts

    @staticmethod
    def _is_valid_oe_number(value: str) -> bool:
        text = value.strip()
        if len(text) < 4:
            return False
        lowered = text.lower()
        if lowered in INVALID_OE_VALUES:
            return False
        if re.fullmatch(r"[a-z\-]+", lowered):
            return False
        if re.search(r"\d{5,}", text):
            return True
        if re.search(r"\d", text) and re.fullmatch(r"[A-Z0-9\-./]+", text, re.I):
            return True
        return False

    def _resolve_store_id(self, sid: int | None = None) -> int:
        if self.settings.lingxing_publish_store_id > 0:
            return int(self.settings.lingxing_publish_store_id)
        if sid is not None and sid > 0:
            return int(sid)
        if self.settings.lingxing_default_sid > 0:
            return int(self.settings.lingxing_default_sid)
        return 0

    async def _fetch_relation_tags(self, relation_id: str, sid: int | None = None) -> list[str]:
        resolved_sid = sid if sid is not None else self.settings.lingxing_default_sid
        if not resolved_sid:
            us_sids = await self._get_us_sids()
            resolved_sid = us_sids[0] if us_sids else None
        if not resolved_sid:
            return []

        payload = {
            "bind_detail": [
                {
                    self.settings.lingxing_sid_field: int(resolved_sid),
                    self.settings.lingxing_relation_id_field: relation_id,
                }
            ]
        }

        try:
            result = await self._post_json(self.settings.lingxing_relation_tag_path, payload)
        except LingxingAuthError:
            return []

        if result.get("code") not in (0, "0"):
            return []
        data = result.get("data") or []
        if not isinstance(data, list) or not data:
            return []
        first = data[0] if isinstance(data[0], dict) else {}
        tag_infos = first.get("tag_infos") or []
        names: list[str] = []
        for item in tag_infos:
            if not isinstance(item, dict):
                continue
            tag_name = str(item.get("tag_name", "")).strip()
            if tag_name:
                names.append(tag_name)
        return self._dedupe_list(names)

    async def _resolve_query_sid(self, sid: int | None) -> str:
        if sid is not None and sid > 0:
            return str(sid)
        us_sids = await self._get_us_sids()
        if us_sids:
            return ",".join(str(value) for value in us_sids)
        if self.settings.lingxing_default_sid:
            return str(self.settings.lingxing_default_sid)
        return ""

    async def _get_us_sids(self) -> list[int]:
        if LingxingService._shared_us_sids_cache is not None:
            return LingxingService._shared_us_sids_cache

        manual = self._parse_sid_list(self.settings.lingxing_us_sids)
        if manual:
            LingxingService._shared_us_sids_cache = manual
            return manual

        try:
            result = await self._get_json(self.settings.lingxing_sellers_path, {})
        except LingxingAuthError:
            LingxingService._shared_us_sids_cache = []
            return []

        if result.get("code") not in (0, "0"):
            LingxingService._shared_us_sids_cache = []
            return []

        sids: list[int] = []
        data = result.get("data") or []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if not self._is_us_store(item):
                    continue
                status = int(item.get("status", 1) or 1)
                if status not in (1,):
                    continue
                sid_value = int(item.get("sid", 0) or 0)
                if sid_value > 0:
                    sids.append(sid_value)

        LingxingService._shared_us_sids_cache = self._dedupe_ints(sids)
        return LingxingService._shared_us_sids_cache

    def _parse_sid_list(self, raw: str) -> list[int]:
        values: list[int] = []
        for part in raw.split(","):
            text = part.strip()
            if not text:
                continue
            try:
                sid_value = int(text)
            except ValueError:
                continue
            if sid_value > 0:
                values.append(sid_value)
        return self._dedupe_ints(values)

    def _dedupe_ints(self, values: list[int]) -> list[int]:
        seen: set[int] = set()
        output: list[int] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output

    def _is_us_store(self, item: dict[str, Any]) -> bool:
        marketplace_id = str(item.get("marketplace_id", "")).strip()
        if marketplace_id == "ATVPDKIKX0DER":
            return True

        country = str(item.get("country", "")).strip()
        region = str(item.get("region", "")).strip().upper()
        country_upper = country.upper()
        codes = {
            part.strip().upper()
            for part in self.settings.lingxing_us_country_codes.split(",")
            if part.strip()
        }
        if country_upper in codes or country in codes:
            return True
        if "美国" in country:
            return True
        if region == "NA" and ("美" in country or country_upper == "US"):
            return True
        return False

    def _pick_listing_item(self, payload: dict[str, Any], sku: str) -> dict[str, Any]:
        data = payload.get("data") or []
        if not isinstance(data, list):
            return self._extract_first_record(payload)

        normalized = sku.strip().lower()
        for item in data:
            if not isinstance(item, dict):
                continue
            seller_sku = str(self._pick_value(item, "seller_sku", "msku", "local_sku") or "").strip()
            if seller_sku.lower() == normalized:
                return item
        return self._extract_first_record(payload)

    def _extract_sid_from_item(self, item: dict[str, Any]) -> int | None:
        sid_value = item.get("sid")
        try:
            sid_int = int(sid_value)
        except (TypeError, ValueError):
            return None
        return sid_int if sid_int > 0 else None

    def _normalize_us_asin_url(self, asin_url: str, asin: str) -> str:
        if asin:
            return f"https://www.amazon.com/dp/{asin}"
        if "amazon.com" in asin_url.lower():
            return asin_url
        return asin_url

    def _resolve_vc_store_ids(self, vc_store_ids: list[str] | None) -> list[str]:
        if vc_store_ids:
            return [str(v).strip() for v in vc_store_ids if str(v).strip()]
        env_value = self.settings.lingxing_vc_default_store_ids.strip()
        if not env_value:
            return []
        return [part.strip() for part in env_value.split(",") if part.strip()]

    def _extract_first_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", payload)
        if isinstance(data, list) and data:
            return data[0] if isinstance(data[0], dict) else {}
        if isinstance(data, dict):
            for key in ("items", "list", "records", "rows"):
                value = data.get(key)
                if isinstance(value, list) and value:
                    return value[0] if isinstance(value[0], dict) else {}
            return data
        return {}

    def _extract_asin(self, item: dict[str, Any]) -> str:
        asin = str(
            self._pick_value(
                item,
                "asin",
                "amazon_asin",
                "parent_asin",
                "child_asin",
            )
            or ""
        ).strip()
        if asin:
            return asin
        asin_info = item.get("asin_info")
        if isinstance(asin_info, dict):
            return str(self._pick_value(asin_info, "asin", "amazon_asin") or "").strip()
        return ""

    def _extract_global_tag_names(self, item: dict[str, Any]) -> list[str]:
        raw_tags = item.get("global_tags")
        if not isinstance(raw_tags, list):
            return []
        names: list[str] = []
        for tag in raw_tags:
            if not isinstance(tag, dict):
                continue
            name = str(self._pick_value(tag, "tagName", "tag_name", "name") or "").strip()
            if name:
                names.append(name)
        return self._dedupe_list(names)

    def _pick_value(self, item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
        return ""

    def _pick_from_sources(self, sources: list[dict[str, Any]], *keys: str) -> Any:
        for source in sources:
            if not isinstance(source, dict):
                continue
            value = self._pick_value(source, *keys)
            if value not in (None, ""):
                return value
        return ""

    def _dedupe_list(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(text)
        return output

    def _build_auth_headers(self) -> dict[str, str]:
        mode = self.settings.lingxing_auth_mode.lower().strip()
        if mode in {"oauth", "appkey"}:
            return {"Content-Type": "application/json"}
        if mode == "bearer":
            if not self.settings.lingxing_api_token:
                raise ValueError("领星 Bearer 鉴权缺失，请设置 LINGXING_API_TOKEN")
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.lingxing_api_token}",
            }
        raise ValueError(f"不支持的领星鉴权模式: {self.settings.lingxing_auth_mode}")

    def _get_auth_client(self) -> LingxingAuthClient:
        if self._auth_client is None:
            self._auth_client = LingxingAuthClient(
                app_id=self.settings.lingxing_app_key,
                app_secret=self.settings.lingxing_app_secret,
                api_base=self.settings.lingxing_api_base,
            )
        return self._auth_client

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        mode = self.settings.lingxing_auth_mode.lower().strip()
        if mode in {"oauth", "appkey"}:
            return await self._get_auth_client().request("POST", path, payload)
        url = f"{self.settings.lingxing_api_base.rstrip('/')}{path}"
        headers = self._build_auth_headers()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        mode = self.settings.lingxing_auth_mode.lower().strip()
        if mode in {"oauth", "appkey"}:
            return await self._get_auth_client().request("GET", path, extra_params=params)
        url = f"{self.settings.lingxing_api_base.rstrip('/')}{path}"
        headers = self._build_auth_headers()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    def _mock_listing(self, sku: str) -> ListingData:
        return ListingData(
            sku=sku,
            asin="B0GWJ47NFS",
            asin_url="https://www.amazon.com/dp/B0GWJ47NFS",
            title=f"{sku} Lift Lower Pulley Sheave Kit Replacement",
            bullet_points=[
                "Heavy-duty alloy structure for long service life.",
                "Wear-resistant pulley groove for smooth operation.",
                "Direct-fit design, no special tools required.",
                "Stable performance in high-frequency lifting scenarios.",
                "Compatible with multiple rotary lift models.",
            ],
            description=(
                "This pulley sheave kit is engineered for garage lift maintenance tasks. "
                "It delivers stable operation, reduced noise, and dependable durability."
            ),
            keywords=["pulley sheave", "lift repair", "garage equipment", "replacement kit"],
            oe_numbers=[f"OE-{sku}", "41411", "FJ7116-1"],
            listing_tags=["汽配热销", "高复购"],
            scrape_status="skipped",
            scrape_reason="Mock 数据模式",
            scrape_action="无需处理",
            data_source="mock",
        )
