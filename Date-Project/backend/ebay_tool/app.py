"""
eBay 价格抓取工具 — FastAPI 子应用
==================================
从 Flask 版 (app_api_v3.py) 转换而来。

策略：可选类目锁定和 eBay 获取排序；类型核验只标记，不重排结果。

依赖：
  pip install requests openpyxl fastapi python-multipart
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import copy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests as _requests
import urllib3
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XlImage
from openpyxl.utils import get_column_letter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ═══════════════════════ 凭据（环境变量）═══════════════════════

CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "").strip()

# ═══════════════════════ v3 策略配置 ═══════════════════════

CATEGORY_MIN_SHARE = 0.40
RESULT_LIMIT = 100
VERIFY_ENABLED = True
VERIFY_TOP_N = 5
EBAY_SORTS = {
    "best_match": "", "price": "price", "-price": "-price",
    "newlyListed": "newlyListed", "endingSoonest": "endingSoonest",
    "distance": "distance",
}

# ═══════════════════════ SKU-OE 对应关系配置 ═══════════════════════

SKU_OE_FILE = str(Path(__file__).resolve().parent / "SKU主OE对照表.xlsx")
_sku_oe_map: dict[str, str] = {}
_middle_code_oe_map: dict[str, str] = {}
_custom_middle_codes: dict[str, str] = {}
_site_key_oe_map: dict[str, tuple[str, str, str]] = {}
_mapping_schema = "legacy"
_sku_oe_lock = threading.Lock()


def _split_site_key(value: str) -> tuple[str, str] | None:
    """A 列完整键是来源；不依赖 B/C 公式的 Excel 缓存值。"""
    match = re.fullmatch(r"([A-Z0-9]+)(DE|UK|US)", value.strip().upper())
    return (match.group(1), match.group(2).lower()) if match else None


def _extract_middle_code(sku: str) -> str:
    """从 SKU 中提取中间码：去掉第一个 '-' 前的前缀，如 HME-220292 → 220292"""
    if not sku:
        return ""
    idx = sku.find("-")
    if 0 < idx < len(sku) - 1:
        return sku[idx + 1:]
    return ""


def load_sku_oe_map() -> bool:
    """加载旧 SKU-OE 表或新的“中间码+站点”四列表。"""
    global _sku_oe_map, _middle_code_oe_map, _custom_middle_codes
    global _site_key_oe_map, _mapping_schema
    with _sku_oe_lock:
        try:
            if not os.path.exists(SKU_OE_FILE):
                _sku_oe_map = {}
                _middle_code_oe_map = {}
                _custom_middle_codes = {}
                _site_key_oe_map = {}
                _mapping_schema = "legacy"
                return False

            # 普通模式只保存实际存在的单元格；此文件的只读维度可能被格式扩到百万行。
            wb = load_workbook(SKU_OE_FILE, read_only=False, data_only=True)
            ws = wb.active
            new_map: dict[str, str] = {}
            mc_map: dict[str, str] = {}
            custom_mc: dict[str, str] = {}
            site_map: dict[str, tuple[str, str, str]] = {}

            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            is_site_key = bool(
                header_row and len(header_row) >= 4
                and "中间码" in str(header_row[0] or "")
                and "站点" in str(header_row[0] or "")
                and "OE" in str(header_row[3] or "").upper()
            )
            if is_site_key:
                for row in ws.iter_rows(min_row=2, max_col=4, values_only=True):
                    if not row[0]:
                        continue
                    key = str(row[0]).strip().upper()
                    parts = _split_site_key(key)
                    oe = str(row[3]).strip() if row[3] is not None else ""
                    if not parts:
                        continue
                    middle, site = parts
                    if key in site_map:
                        raise ValueError(f"映射键重复：{key}")
                    site_map[key] = (middle, site, oe)
                if not site_map:
                    raise ValueError("四列表没有有效的中间码+站点键")
                wb.close()
                _site_key_oe_map = site_map
                _sku_oe_map = {key: item[2] for key, item in site_map.items() if item[2]}
                _middle_code_oe_map = {}
                _custom_middle_codes = {}
                _mapping_schema = "site_key"
                return True

            has_mc_col = (
                header_row
                and len(header_row) > 2
                and header_row[2]
                and "中间码" in str(header_row[2])
            )

            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[0] and row[1]:
                    sku = str(row[0]).strip()
                    oe = str(row[1]).strip()
                    if sku and oe:
                        new_map[sku] = oe
                        auto_mc = _extract_middle_code(sku)
                        if has_mc_col and len(row) > 2 and row[2]:
                            mc = str(row[2]).strip()
                            if mc and mc.upper() != (auto_mc or "").upper():
                                custom_mc[sku] = mc
                        else:
                            mc = auto_mc
                        if mc:
                            mc_map[mc.upper()] = oe

            wb.close()
            _sku_oe_map = new_map
            _middle_code_oe_map = mc_map
            _custom_middle_codes = custom_mc
            _site_key_oe_map = {}
            _mapping_schema = "legacy"
            return True
        except Exception as e:
            print(f"加载 SKU-OE 对应表失败: {e}")
            return False


def save_sku_oe_map() -> bool:
    """保存 SKU-OE 对应关系到 Excel 文件（含中间码列）"""
    global _sku_oe_map
    with _sku_oe_lock:
        if _mapping_schema == "site_key":
            return False  # 不用旧三列写法覆盖用户的四列源文件。
        try:
            wb = Workbook()
            ws = wb.active
            ws.append(["SKU", "主OE", "中间码"])
            for sku, oe in sorted(_sku_oe_map.items()):
                mc = _custom_middle_codes.get(sku) or _extract_middle_code(sku)
                ws.append([sku, oe, mc])
            ws.column_dimensions["A"].width = 15
            ws.column_dimensions["B"].width = 25
            ws.column_dimensions["C"].width = 15
            wb.save(SKU_OE_FILE)
            wb.close()
            _reload_middle_code_map()
            return True
        except Exception as e:
            print(f"保存 SKU-OE 对应表失败: {e}")
            return False


def _reload_middle_code_map() -> None:
    """重建中间码映射。调用方需已持有 _sku_oe_lock"""
    global _middle_code_oe_map
    mc_map: dict[str, str] = {}
    for sku, oe in _sku_oe_map.items():
        mc = _custom_middle_codes.get(sku) or _extract_middle_code(sku)
        if mc:
            mc_map[mc.upper()] = oe
    _middle_code_oe_map = mc_map


def get_oe_by_sku(sku: str) -> str | None:
    """通过 SKU 或中间码查找 OE"""
    if not sku:
        return None
    key = sku.strip()
    if _mapping_schema == "site_key":
        return (_site_key_oe_map.get(key.upper()) or ("", "", ""))[2] or None
    oe = _sku_oe_map.get(key)
    if oe:
        return oe
    return _middle_code_oe_map.get(key.upper())


load_sku_oe_map()

# ── eBay 站点配置 ──
SITES: dict[str, dict] = {
    "de": {
        "domain": "ebay.de",
        "locale": "de-DE",
        "marketplace": "EBAY_DE",
        "currency": "EUR",
        "global_id": "EBAY-GERMANY",
    },
    "uk": {
        "domain": "ebay.co.uk",
        "locale": "en-GB",
        "marketplace": "EBAY_GB",
        "currency": "GBP",
        "global_id": "EBAY-GB",
    },
    "us": {
        "domain": "ebay.com",
        "locale": "en-US",
        "marketplace": "EBAY_US",
        "currency": "USD",
        "global_id": "EBAY-US",
    },
}

US_DELIVERY_POSTAL_CODES = {"08505", "92236"}
DEFAULT_US_DELIVERY_POSTAL_CODE = "08505"


def _site_delivery_location(site_key: str, us_postal_code: str) -> tuple[str, str]:
    if site_key == "us":
        return "US", us_postal_code
    if site_key == "de":
        return "DE", "42489"
    if site_key == "uk":
        return "GB", ""
    raise ValueError(f"不支持的 eBay 站点: {site_key}")

# ── OAuth2 Token 缓存 ──
_token_cache: dict = {"token": None, "expires": 0}
_token_lock = threading.Lock()

# ── API 端点 ──
OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/"


def get_access_token() -> str:
    """获取或刷新 App 级别的 OAuth2 Access Token"""
    with _token_lock:
        if _token_cache["token"] and time.time() < _token_cache["expires"]:
            return _token_cache["token"]

        resp = _requests.post(
            OAUTH_URL,
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
            verify=False,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"获取 eBay Token 失败 (HTTP {resp.status_code})：{resp.text}\n"
                f"请检查环境变量 EBAY_CLIENT_ID 和 EBAY_CLIENT_SECRET 是否正确。"
            )

        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires"] = time.time() + data.get("expires_in", 7200) - 60
        return _token_cache["token"]


def _api_get(
    url: str, params: dict, marketplace: str, retry_on_401: bool = True,
    delivery_country: str = "", delivery_postal_code: str = "",
) -> tuple[dict | None, str | None]:
    """带鉴权的 GET 请求，401 时自动刷新 token 重试一次"""
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace,
    }
    if delivery_country and delivery_postal_code:
        location = f"country={delivery_country},zip={delivery_postal_code}"
        headers["X-EBAY-C-ENDUSERCTX"] = (
            "contextualLocation=" + quote(location, safe="")
        )
    resp = _requests.get(
        url, params=params, headers=headers, timeout=30, verify=False
    )

    if resp.status_code == 200:
        return resp.json(), None

    if resp.status_code == 401 and retry_on_401:
        _token_cache["token"] = None
        token = get_access_token()
        headers["Authorization"] = f"Bearer {token}"
        resp = _requests.get(
            url, params=params, headers=headers, timeout=30, verify=False
        )
        if resp.status_code == 200:
            return resp.json(), None

    return None, (
        f"eBay API 返回错误 (HTTP {resp.status_code}): {resp.text[:300]}"
    )


def search_ebay(
    keyword: str,
    marketplace: str,
    limit: int = 100,
    offset: int = 0,
    sort: str = "",
    category_id: str = "",
    fixed_price_only: bool = False,
    fieldgroups: str = "",
    free_shipping: bool = False,
    delivery_country: str = "",
    delivery_postal_code: str = "",
    pickup_country: str = "",
    pickup_postal_code: str = "",
    pickup_radius: int | None = None,
    pickup_unit: str = "",
    price_min: str = "",
    price_max: str = "",
) -> tuple[dict | None, str | None]:
    """
    调用 eBay Browse API 搜索商品
    sort:             "" 默认最佳匹配，其余值由入口白名单校验
    category_id:      限定叶子类目（v3 类目锁定用）
    fixed_price_only: 只保留一口价（排除拍卖，v3 第二遍搜索用）
    fieldgroups:      传 "MATCHING_ITEMS,CATEGORY_REFINEMENTS" 可拿 refinement 类目分布
    free_shipping:    仅返回免运费商品
    """
    filters = ["conditions:{NEW}"]
    if fixed_price_only:
        filters.append("buyingOptions:{FIXED_PRICE}")
    if free_shipping:
        filters.append("maxDeliveryCost:0")
    if sort != "distance" and delivery_country:
        filters.append(f"deliveryCountry:{delivery_country}")
        if delivery_postal_code:
            filters.append(f"deliveryPostalCode:{delivery_postal_code}")
    if price_min or price_max:
        currency = next(cfg["currency"] for cfg in SITES.values() if cfg["marketplace"] == marketplace)
        price_range = f"{price_min}..{price_max}" if price_max else price_min
        filters.extend([f"price:[{price_range}]", f"priceCurrency:{currency}"])
    if sort == "distance":
        filters.extend([
            "deliveryOptions:{SELLER_ARRANGED_LOCAL_PICKUP}",
            f"pickupCountry:{pickup_country}",
            f"pickupPostalCode:{pickup_postal_code}",
            f"pickupRadius:{pickup_radius}",
            f"pickupRadiusUnit:{pickup_unit}",
        ])

    params: dict = {
        "q": keyword,
        "limit": min(limit, 200),
        "offset": offset,
        "filter": ",".join(filters),
    }
    if sort:
        params["sort"] = sort
    if category_id:
        params["category_ids"] = category_id
    if fieldgroups:
        params["fieldgroups"] = fieldgroups

    return _api_get(
        BROWSE_URL, params, marketplace,
        delivery_country=delivery_country,
        delivery_postal_code=delivery_postal_code,
    )


def get_item_product_type(item_id: str, marketplace: str) -> str:
    """
    调 getItem 接口，读取 localizedAspects 中的产品类型字段
    用于 v3 可选核验：确认最低价候选确实是整件而非零件
    """
    if not item_id:
        return ""
    data, error = _api_get(ITEM_URL + item_id, {}, marketplace)
    if error or not data:
        return ""
    for aspect in data.get("localizedAspects", []):
        name = (aspect.get("name") or "").strip().lower()
        if name in ("produktart", "product type", "type"):
            return (aspect.get("value") or "").strip()
    return ""


def _clean_item_url(url: str) -> str:
    """清理 eBay 商品链接，去掉追踪参数"""
    if not url:
        return ""
    idx = url.find("/itm/")
    if idx < 0:
        return url
    after = url[idx + 5:]
    m = re.search(r"[?_#]", after)
    return url[: idx + 5] + (after[: m.start()] if m else after)


def _upgrade_img(url: str) -> str:
    """将图片 URL 的尺寸升级到 s-l500"""
    return re.sub(r"s-l\d+", "s-l500", url) if url else url


def format_item(item: dict) -> dict:
    """将 Browse API 返回的单条 item 标准化"""
    title = item.get("title", "")
    price_info = item.get("price", {})
    price_value = float(price_info.get("value", 0))
    currency = price_info.get("currency", "EUR")
    price_str = f"{price_value:.2f} {currency}"

    condition = item.get("condition", "")
    condition_id = item.get("conditionId", "")

    images: list[str] = []
    seen_urls: set[str] = set()
    for src_list in [
        item.get("thumbnailImages", []),
        item.get("additionalImages", []),
    ]:
        for img in src_list:
            u = img.get("imageUrl", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                images.append(_upgrade_img(u))
    if not images:
        primary = item.get("image", {})
        if primary and primary.get("imageUrl"):
            images.append(_upgrade_img(primary["imageUrl"]))
    images = images[:5]

    item_web_url = _clean_item_url(item.get("itemWebUrl", ""))
    item_id = item.get("itemId", "")

    seller = item.get("seller", {})
    seller_username = seller.get("username", "")
    seller_feedback = seller.get("feedbackPercentage", "")

    buying_options = item.get("buyingOptions", [])
    shipping_options = item.get("shippingOptions", [])
    shipping_cost = ""
    if shipping_options:
        ship_price = shipping_options[0].get("shippingCost", {})
        if ship_price:
            ship_val = float(ship_price.get("value", 0))
            ship_curr = ship_price.get("currency", currency)
            shipping_cost = (
                f"{ship_val:.2f} {ship_curr}" if ship_val > 0 else "免运费"
            )

    # 从 estimatedAvailabilities 提取预计已售数量
    estimated_sold = None
    for avail in item.get("estimatedAvailabilities") or []:
        qty = avail.get("estimatedSoldQuantity")
        if qty is not None:
            try:
                parsed = max(int(qty), 0)
                estimated_sold = max(parsed, estimated_sold or 0)
            except (ValueError, TypeError):
                pass

    return {
        "title": title,
        "price": price_str,
        "pf": price_value,
        "currency": currency,
        "condition": condition,
        "conditionId": condition_id,
        "categoryId": item.get("categoryId", ""),
        "images": images,
        "link": item_web_url,
        "itemId": item_id,
        "seller": seller_username,
        "sellerFeedback": seller_feedback,
        "shipping": shipping_cost,
        "listedAt": item.get("itemCreationDate", ""),
        "endsAt": item.get("itemEndDate", ""),
        "buyingOptions": buying_options,
        "estimatedSold": estimated_sold,
    }


def parse_oe_list(text: str) -> list[str]:
    """解析用户输入的 OE 号列表"""
    lines: list[str] = []
    for line in text.replace(",", "\n").replace("，", "\n").split("\n"):
        oe = line.strip()
        if oe:
            lines.append(oe)
    seen: set[str] = set()
    result: list[str] = []
    for oe in lines:
        if oe.upper() not in seen:
            seen.add(oe.upper())
            result.append(oe)
    return result


def _pick_dominant_category(
    data: dict, items_raw: list[dict]
) -> tuple[str, str, float, list[dict]]:
    """
    从搜索响应中选出主导类目
    优先读 refinement.categoryDistributions（eBay 官方类目分布）；
    若 API 未返回 refinement 数据，则从 items 自身的 categoryId 投票统计。
    返回 (category_id, category_name, share, dist_top)
    dist_top 为类目分布前 5 名 [{id, name, count}]，用于前端诊断展示；
    类目不可信时 category_id 为 ""
    """
    refinement = data.get("refinement", {}) or {}
    dists = refinement.get("categoryDistributions", []) or []

    # ── 路径 A：API 返回了 refinement 数据 ──
    if dists:
        dist_top = [
            {
                "id": d.get("categoryId", ""),
                "name": d.get("categoryName", ""),
                "count": d.get("matchCount", 0),
            }
            for d in sorted(
                dists, key=lambda x: x.get("matchCount", 0), reverse=True
            )[:5]
        ]
        total = sum(d.get("matchCount", 0) for d in dists)
        top = max(dists, key=lambda d: d.get("matchCount", 0))
        top_count = top.get("matchCount", 0)
        share = (top_count / total) if total > 0 else 0.0
        if top.get("categoryId") and share >= CATEGORY_MIN_SHARE:
            return top["categoryId"], top.get("categoryName", ""), share, dist_top
        return "", "", share, dist_top

    # 部分响应没有 categoryDistributions，但有 dominantCategoryId
    dom_id = refinement.get("dominantCategoryId", "")
    if dom_id:
        return dom_id, "", 1.0, []

    # ── 路径 B：refinement 完全缺失，从 items 自身统计类目 ──
    cat_counter: Counter[str] = Counter()
    cat_name_map: dict[str, str] = {}
    for item in items_raw or []:
        cid = ""
        cname = ""
        cats = item.get("categories", []) or []
        if cats:
            leaf = cats[-1]
            cid = leaf.get("categoryId", "")
            cname = leaf.get("categoryName", "")
        if not cid:
            leaf_ids = item.get("leafCategoryIds", []) or []
            if leaf_ids:
                cid = leaf_ids[0]
        if cid:
            cat_counter[cid] += 1
            if cname and cid not in cat_name_map:
                cat_name_map[cid] = cname

    if not cat_counter:
        return "", "", 0.0, []

    dist_top = [
        {"id": cid, "name": cat_name_map.get(cid, ""), "count": cnt}
        for cid, cnt in cat_counter.most_common(5)
    ]

    top_cid, top_count = cat_counter.most_common(1)[0]
    total = sum(cat_counter.values())
    share = top_count / total if total > 0 else 0.0

    if share >= CATEGORY_MIN_SHARE:
        return top_cid, cat_name_map.get(top_cid, ""), share, dist_top
    return "", "", share, dist_top


def _verify_top_items(items: list[dict], marketplace: str) -> list[dict]:
    """
    可选核验当前 eBay 排名前 VERIFY_TOP_N 条；只标记疑似类型，不改变排名。
    """
    if not VERIFY_ENABLED or not items:
        return items

    check_n = min(VERIFY_TOP_N, len(items))
    head = items[:check_n]

    types: list[str] = []
    for it in head:
        ptype = get_item_product_type(it["itemId"], marketplace)
        it["productType"] = ptype
        types.append(ptype.lower() if ptype else "")

    known = [t for t in types if t]
    if len(known) < 2:
        return items

    modal_type = max(set(known), key=known.count)
    if known.count(modal_type) < 2:
        return items

    for it, t in zip(head, types):
        if t and t != modal_type:
            it["suspect"] = True
    return items


def _finalize_oe(
    items_raw: list[dict],
    oe: str,
    strategy: str,
    mp: str,
    cat_info: dict | None,
    verify: bool = False,
) -> tuple[list[dict], None, str, dict | None, list[float]]:
    """公共收尾：按 eBay 原始顺序格式化、核验前五条、限制返回数量。"""
    result = [format_item(it) for it in items_raw]
    for it in result:
        it["oe"] = oe
    all_prices = [it["pf"] for it in result[:RESULT_LIMIT]]
    if verify:
        result = _verify_top_items(result, mp)
    return result[:RESULT_LIMIT], None, strategy, cat_info, all_prices


def scrape_one_oe(
    oe: str,
    site_key: str,
    free_shipping: bool = False,
    search_strategy: str = "category_lock",
    ebay_sort: str | None = None,
    delivery_country: str = "",
    delivery_postal_code: str = "",
    pickup_country: str = "",
    pickup_postal_code: str = "",
    pickup_radius: int | None = None,
    pickup_unit: str = "",
    price_min: str = "",
    price_max: str = "",
    us_postal_code: str = DEFAULT_US_DELIVERY_POSTAL_CODE,
) -> tuple[list[dict], str | None, int, str, dict | None, list[float]]:
    """搜索单个 OE；展示顺序始终来自最终一次 Browse API 响应。"""
    cfg = SITES[site_key]
    mp = cfg["marketplace"]
    sort = (
        "price" if search_strategy == "category_lock" else ""
    ) if ebay_sort is None else EBAY_SORTS.get(ebay_sort, ebay_sort)
    if sort != "distance" and not delivery_country:
        delivery_country, delivery_postal_code = _site_delivery_location(
            site_key, us_postal_code
        )
    common = dict(
        limit=RESULT_LIMIT, free_shipping=free_shipping,
        delivery_country=delivery_country,
        delivery_postal_code=delivery_postal_code,
        pickup_country=pickup_country,
        pickup_postal_code=pickup_postal_code,
        pickup_radius=pickup_radius,
        pickup_unit=pickup_unit,
        price_min=price_min, price_max=price_max,
    )

    if search_strategy == "best_match":
        data, error = search_ebay(oe, mp, sort=sort, **common)
        if error:
            return [], error, 0, "error", None, []
        items_raw = (data or {}).get("itemSummaries", [])
        if not items_raw:
            return [], f"OE '{oe}' 在 {cfg['domain']} 上未找到结果", 0, "error", None, []
        sold_total = sum(item.get("soldQuantity", 0) or 0 for item in items_raw)
        items, _, _, _, all_prices = _finalize_oe(
            items_raw, oe, "best_match", mp, None
        )
        return items, None, sold_total, "best_match", None, all_prices

    # First pass identifies a dominant category with the same inventory filters.
    data1, error = search_ebay(
        oe, mp, sort=sort,
        fieldgroups="MATCHING_ITEMS,CATEGORY_REFINEMENTS",
        fixed_price_only=True,
        **common,
    )
    if error:
        return [], error, 0, "error", None, []
    items_raw1 = (data1 or {}).get("itemSummaries", [])
    if not items_raw1:
        return [], f"OE '{oe}' 在 {cfg['domain']} 上未找到结果", 0, "error", None, []
    cat_id, cat_name, share, dist_top = _pick_dominant_category(data1, items_raw1)
    cat_info = {
        "id": cat_id,
        "name": cat_name,
        "share": round(share, 3),
        "top": dist_top,
    }
    strategy = "category_locked" if cat_id else "category_fallback"
    data2 = None
    error2 = None
    if cat_id:
        data2, error2 = search_ebay(
            oe, mp, sort=sort, category_id=cat_id,
            fixed_price_only=True, **common,
        )
    if not cat_id or error2 or not (data2 or {}).get("itemSummaries"):
        strategy = "category_fallback"
        cat_info["fallbackReason"] = (
            "无法确定主要类目" if not cat_id else
            "类目查询失败" if error2 else "类目下无结果"
        )
        # Never present the probe sample as if it obeyed the selected sort.
        data2, error2 = search_ebay(
            oe, mp, sort=sort, fixed_price_only=True, **common,
        )
    if error2:
        return [], error2, 0, "error", cat_info, []
    selected = (data2 or {}).get("itemSummaries", [])
    if not selected:
        return [], f"OE '{oe}' 在 {cfg['domain']} 上未找到结果", 0, "error", cat_info, []
    sold_total = sum(item.get("soldQuantity", 0) or 0 for item in selected)
    items, _, _, _, all_prices = _finalize_oe(
        selected, oe, strategy, mp, cat_info, verify=True,
    )
    return items, None, sold_total, strategy, cat_info, all_prices


# ═══════════════════════ 批量搜索（异步任务） ═══════════════════════

tasks: dict[str, dict] = {}


def search_batch(
    oe_list: list[str],
    site_key: str,
    task_id: str,
    free_shipping: bool = False,
    search_strategy: str = "category_lock",
    ebay_sort: str | None = None,
    delivery_country: str = "",
    delivery_postal_code: str = "",
    pickup_country: str = "",
    pickup_postal_code: str = "",
    pickup_radius: int | None = None,
    pickup_unit: str = "",
    targets: list[dict[str, str]] | None = None,
    price_min: str = "",
    price_max: str = "",
    us_postal_code: str = DEFAULT_US_DELIVERY_POSTAL_CODE,
) -> None:
    """后台线程：3 并发搜索 OE 号"""
    work_items = targets if targets is not None else [
        {"inputKey": "", "site": site_key, "oe": oe,
         "groupKey": f"{site_key}:{oe}"} for oe in oe_list
    ]
    total = len(work_items)
    all_results: list[dict | None] = []
    completed = 0
    lock = threading.Lock()

    def do_one(target: dict[str, str]) -> dict:
        oe = target["oe"]
        site = target["site"]
        query_delivery = ("", "")
        if ebay_sort != "distance":
            query_delivery = (
                (delivery_country, delivery_postal_code)
                if delivery_country else _site_delivery_location(site, us_postal_code)
            )
        items, warning, sold, strategy, cat_info, all_prices = scrape_one_oe(
            oe, site, free_shipping=free_shipping, search_strategy=search_strategy,
            ebay_sort=ebay_sort, delivery_country=delivery_country,
            delivery_postal_code=delivery_postal_code,
            pickup_country=pickup_country, pickup_postal_code=pickup_postal_code,
            pickup_radius=pickup_radius, pickup_unit=pickup_unit,
            price_min=price_min, price_max=price_max,
            us_postal_code=us_postal_code,
        )
        for item in items:
            item["inputKey"] = target.get("inputKey", "")
            item["site"] = site.upper()
            item["groupKey"] = target["groupKey"]
        return {
            "oe": oe,
            "inputKey": target.get("inputKey", ""),
            "site": site.upper(),
            "groupKey": target["groupKey"],
            "count": len(items),
            "items": items,
            "warning": warning if not items else None,
            "soldTotal": sold,
            "strategy": strategy,
            "categoryInfo": cat_info,
            "allPrices": all_prices,
            "actualSort": (
                "price" if ebay_sort is None and search_strategy == "category_lock"
                else "best_match" if ebay_sort is None
                else ebay_sort
            ),
            "categoryFallback": strategy == "category_fallback",
            "fetchedCount": len(items),
            "queryPrice": {"min": price_min, "max": price_max, "currency": SITES[site]["currency"]},
            "queryDelivery": {"country": query_delivery[0], "postalCode": query_delivery[1]},
        }

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            future_map = {pool.submit(do_one, target): i for i, target in enumerate(work_items)}
            all_results = [None] * total

            for fut in as_completed(future_map):
                index = future_map[fut]
                target = work_items[index]
                result = fut.result()
                all_results[index] = result
                with lock:
                    completed += 1
                tasks[task_id] = {
                    "status": "running",
                    "progress": {
                        "current": completed,
                        "total": total,
                        "oe": f"{target.get('inputKey') or target['oe']} ({target['site'].upper()})",
                    },
                }

        tasks[task_id] = {
            "status": "done",
            "total_oe": total,
            "results": all_results,
        }

    except Exception as e:
        tasks[task_id] = {"status": "error", "msg": str(e)}


def cleanup_tasks() -> None:
    """清理已完成的旧任务（保留最近 20 条）"""
    terminal = [
        tid
        for tid, t in tasks.items()
        if t.get("status") in ("done", "error")
    ]
    if len(terminal) > 20:
        for tid in terminal[:-20]:
            del tasks[tid]


# ═══════════════════════ 路由 ═══════════════════════

router = APIRouter()


def _start_search_task(
    oe_list: list[str],
    site: str,
    free_shipping: bool,
    search_strategy: str,
    sku_mapping: dict | None = None,
    not_found_skus: list[str] | None = None,
    file_info: dict | None = None,
    *,
    ebay_sort: str | None = None,
    delivery_country: str = "",
    delivery_postal_code: str = "",
    pickup_country: str = "",
    pickup_postal_code: str = "",
    pickup_radius: int | None = None,
    pickup_unit: str = "",
    targets: list[dict[str, str]] | None = None,
    price_min: str = "",
    price_max: str = "",
    us_postal_code: str = DEFAULT_US_DELIVERY_POSTAL_CODE,
) -> dict:
    """公共逻辑：启动后台搜索任务并返回响应"""
    oe_list = list(dict.fromkeys(oe_list))
    if not oe_list and not targets:
        raise HTTPException(status_code=400, detail="没有可查询的中间码+站点映射")

    work_count = len(targets) if targets is not None else len(oe_list)

    task_id = str(int(time.time() * 1000))[-8:]
    tasks[task_id] = {
        "status": "running",
        "progress": {"current": 0, "total": work_count, "oe": "启动中..."},
    }

    t = threading.Thread(
        target=search_batch,
        args=(oe_list, site, task_id, free_shipping, search_strategy),
        kwargs={
            "ebay_sort": ebay_sort,
            "delivery_country": delivery_country,
            "delivery_postal_code": delivery_postal_code,
            "pickup_country": pickup_country,
            "pickup_postal_code": pickup_postal_code,
            "pickup_radius": pickup_radius,
            "pickup_unit": pickup_unit,
            "targets": targets,
            "price_min": price_min,
            "price_max": price_max,
            "us_postal_code": us_postal_code,
        },
    )
    t.daemon = True
    t.start()

    resp: dict = {
        "task_id": task_id,
        "oe_list": oe_list,
        "input_keys": [target["inputKey"] for target in targets] if targets is not None else [],
        "sku_mapping": sku_mapping or {},
        "not_found_skus": not_found_skus or [],
    }
    if file_info:
        resp["file_info"] = file_info
    return resp


def _resolve_oe_list(
    input_list: list[str], input_type: str
) -> tuple[list[str], dict[str, str], list[str]]:
    """根据输入类型解析 OE 列表，返回 (oe_list, sku_mapping, not_found_skus)"""
    oe_list: list[str] = []
    sku_mapping: dict[str, str] = {}
    not_found_skus: list[str] = []

    if input_type == "oe":
        oe_list = input_list
    elif input_type == "sku":
        with _sku_oe_lock:
            for item in input_list:
                oe = _sku_oe_map.get(item) or _middle_code_oe_map.get(
                    item.upper()
                )
                if oe:
                    oe_list.append(oe)
                    sku_mapping[item] = oe
                else:
                    not_found_skus.append(item)
    else:
        # auto：先查 SKU，再查中间码，都没有则当作 OE 直接搜
        with _sku_oe_lock:
            for item in input_list:
                oe = _sku_oe_map.get(item) or _middle_code_oe_map.get(
                    item.upper()
                )
                if oe:
                    oe_list.append(oe)
                    sku_mapping[item] = oe
                else:
                    oe_list.append(item)

    return oe_list, sku_mapping, not_found_skus


def _resolve_site_key_targets(
    input_list: list[str],
) -> tuple[list[dict[str, str]], dict[str, str], list[str]]:
    """按完整的中间码+站点键精确匹配，不跨站点借用 OE。"""
    targets: list[dict[str, str]] = []
    mapping: dict[str, str] = {}
    not_found: list[str] = []
    with _sku_oe_lock:
        if _mapping_schema != "site_key":
            raise HTTPException(status_code=400, detail="当前对照表不是“中间码+站点”四列格式，请刷新映射表")
        known_middle_codes = {entry[0] for entry in _site_key_oe_map.values()}
        for raw in input_list:
            key = raw.strip().upper()
            parts = _split_site_key(key)
            if not parts:
                not_found.append(f"{raw}（格式应为中间码+DE/UK/US）")
                continue
            entry = _site_key_oe_map.get(key)
            if entry is None:
                reason = "对应站点没有映射" if parts[0] in known_middle_codes else "中间码不存在"
                not_found.append(f"{raw}（{reason}）")
            elif not entry[2]:
                not_found.append(f"{raw}（对应中间码和站点的 OE 号为空）")
            else:
                middle, site, oe = entry
                targets.append({"inputKey": key, "middleCode": middle,
                                "site": site, "oe": oe, "groupKey": key})
                mapping[key] = oe
    return targets, mapping, not_found


def _parse_excel_keywords_from_bytes(
    content: bytes, filename: str, site_key_mode: bool = False,
) -> tuple[list[str], str, int, int, str]:
    """
    解析上传的 Excel 文件内容，提取 SKU / OE 列表。
    支持两种格式：
      一列表：A1 为 OE 相关表头，A2 起每行一个 OE。
      两列表：A1 为 SKU、B1 为 OE，数据从第 2 行开始。
    返回 (keywords, input_type, total_rows, skipped_rows, file_name)
    """
    wb = load_workbook(BytesIO(content), read_only=False, data_only=True)
    ws = wb.active
    if ws is None:
        wb.close()
        raise ValueError("Excel 文件没有工作表")

    rows = list(ws.iter_rows(min_row=1, values_only=True))
    wb.close()

    if not rows:
        raise ValueError("Excel 文件为空")

    header = rows[0]
    if not header:
        raise ValueError("Excel 文件表头为空")

    def normalize_header(val: object) -> str:
        return re.sub(r"[\s_]", "", str(val or "")).lower()

    col_a = normalize_header(header[0]) if len(header) > 0 and header[0] else ""
    col_b = normalize_header(header[1]) if len(header) > 1 and header[1] else ""

    if site_key_mode and col_a not in ("中间码+站点", "中间码站点", "sitekey"):
        raise ValueError("Excel A1 表头必须是“中间码+站点”")

    has_sku_col = col_a in ("sku", "skuid", "skuno") and not site_key_mode
    has_oe_col = col_b in ("oe", "oeno", "oenumber", "oenr", "partnumber", "partno")

    keywords: list[str] = []
    total_rows = 0
    skipped_rows = 0

    if has_sku_col and has_oe_col:
        for row in rows[1:]:
            total_rows += 1
            sku = str(row[0]).strip() if len(row) > 0 and row[0] else ""
            oe = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            if oe:
                keywords.append(oe)
            elif sku:
                keywords.append(sku)
            else:
                skipped_rows += 1
        input_type = "auto"
    else:
        for row in rows[1:]:
            total_rows += 1
            val = str(row[0]).strip() if len(row) > 0 and row[0] else ""
            for part in re.split(r"[\r\n,，;；]+", val):
                part = part.strip()
                if part:
                    keywords.append(part)
            if not val:
                skipped_rows += 1
        input_type = "site_key" if site_key_mode else "oe"

    # 去重保序
    seen: set[str] = set()
    unique_keywords: list[str] = []
    for kw in keywords:
        key_upper = kw.upper()
        if key_upper not in seen:
            seen.add(key_upper)
            unique_keywords.append(kw)

    return unique_keywords, input_type, total_rows, skipped_rows, filename


# ═══════════════════════ 搜索 API ═══════════════════════


def _validated_search_options(
    site: str, strategy: str, free_shipping: bool,
    ebay_sort: str | None, delivery_country: str, delivery_postal_code: str,
    pickup_country: str, pickup_postal_code: str,
    pickup_radius: str, pickup_unit: str,
    price_min: str = "", price_max: str = "",
    us_postal_code: str = DEFAULT_US_DELIVERY_POSTAL_CODE,
) -> dict:
    """Validate browser fields once for both text and Excel entry points."""
    bounds = []
    for label, value in (("最低价", price_min), ("最高价", price_max)):
        value = value.strip()
        if value and (len(value) > 32 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value)):
            raise HTTPException(status_code=400, detail=f"查询{label}必须是大于等于0的数字，最多两位小数")
        bounds.append(value)
    price_min, price_max = bounds
    if price_min and price_max and Decimal(price_min) > Decimal(price_max):
        raise HTTPException(status_code=400, detail="查询最低价不能大于最高价")
    selected_sort = ebay_sort.strip() if ebay_sort is not None else None
    if selected_sort is not None and selected_sort not in EBAY_SORTS:
        raise HTTPException(status_code=400, detail="不支持的 eBay 获取排序")
    country = delivery_country.strip().upper()
    postal = delivery_postal_code.strip()
    if postal and not country:
        raise HTTPException(status_code=400, detail="参考配送邮编需要同时填写国家")
    if country and (
        not re.fullmatch(r"[A-Z]{2}", country)
        or (postal and not re.fullmatch(r"[A-Za-z0-9 -]{3,12}", postal))
    ):
        raise HTTPException(status_code=400, detail="参考配送地点格式不正确")
    us_postal_code = us_postal_code.strip()
    if us_postal_code not in US_DELIVERY_POSTAL_CODES:
        raise HTTPException(status_code=400, detail="美国配送邮编仅支持 08505 或 92236")

    pickup = {
        "pickup_country": pickup_country.strip().upper(),
        "pickup_postal_code": pickup_postal_code.strip(),
        "pickup_radius": None,
        "pickup_unit": pickup_unit.strip(),
    }
    if selected_sort == "distance":
        if free_shipping:
            raise HTTPException(status_code=400, detail="最近自提不能同时选择仅免运费")
        if country:
            raise HTTPException(status_code=400, detail="最近自提不使用参考配送地点")
        if (
            not re.fullmatch(r"[A-Z]{2}", pickup["pickup_country"])
            or not re.fullmatch(r"[A-Za-z0-9 -]{3,12}", pickup["pickup_postal_code"])
            or not pickup_radius.strip().isdigit()
            or pickup["pickup_unit"] not in {"km", "mi"}
        ):
            raise HTTPException(status_code=400, detail="请填写完整有效的自提国家、邮编、半径和单位")
        radius = int(pickup_radius.strip())
        if not 1 <= radius <= 500:
            raise HTTPException(status_code=400, detail="自提半径必须为 1-500")
        pickup["pickup_radius"] = radius
    elif any((pickup_country, pickup_postal_code, pickup_radius, pickup_unit)):
        raise HTTPException(status_code=400, detail="自提地点仅用于最近自提排序")

    return {
        "ebay_sort": selected_sort,
        "delivery_country": country,
        "delivery_postal_code": postal,
        "price_min": price_min,
        "price_max": price_max,
        "us_postal_code": us_postal_code,
        **pickup,
    }


@router.post("/api/scrape")
async def api_scrape(
    nkw: str = Form(""),
    site: str = Form("de"),
    input_type: str = Form("auto"),
    free_shipping: str = Form("false"),
    search_strategy: str = Form("category_lock"),
    ebay_sort: str | None = Form(None),
    delivery_country: str = Form(""),
    delivery_postal_code: str = Form(""),
    pickup_country: str = Form(""),
    pickup_postal_code: str = Form(""),
    pickup_radius: str = Form(""),
    pickup_unit: str = Form(""),
    price_min: str = Form(""),
    price_max: str = Form(""),
    us_postal_code: str = Form(DEFAULT_US_DELIVERY_POSTAL_CODE),
):
    cleanup_tasks()

    raw_text = nkw.strip()
    fs = free_shipping.strip().lower() == "true"
    ss = search_strategy.strip()
    if ss not in ("best_match", "category_lock"):
        ss = "category_lock"

    key_mode = input_type.strip() == "site_key"
    if (key_mode and site != "auto") or (not key_mode and site not in SITES):
        raise HTTPException(status_code=400, detail="不支持的站点")
    options = _validated_search_options(
        site, ss, fs, ebay_sort, delivery_country, delivery_postal_code,
        pickup_country, pickup_postal_code, pickup_radius, pickup_unit,
        price_min, price_max, us_postal_code,
    )
    if not raw_text:
        raise HTTPException(status_code=400, detail="请输入至少一个产品编号")

    input_list = parse_oe_list(raw_text)
    if not input_list:
        raise HTTPException(status_code=400, detail="未能识别有效的产品编号")

    if key_mode:
        targets, mapping, not_found = _resolve_site_key_targets(input_list)
        if not targets:
            raise HTTPException(status_code=400, detail="没有可查询的映射：" + "、".join(not_found[:10]))
        return _start_search_task(
            [], site, fs, ss, mapping, not_found, targets=targets, **options
        )

    oe_list, sku_mapping, not_found_skus = _resolve_oe_list(
        input_list, input_type.strip()
    )
    return _start_search_task(
        oe_list, site, fs, ss, sku_mapping, not_found_skus, **options
    )


@router.post("/api/scrape-file")
async def api_scrape_file(
    site: str = Form("de"),
    input_type: str = Form(""),
    free_shipping: str = Form("false"),
    search_strategy: str = Form("category_lock"),
    ebay_sort: str | None = Form(None),
    delivery_country: str = Form(""),
    delivery_postal_code: str = Form(""),
    pickup_country: str = Form(""),
    pickup_postal_code: str = Form(""),
    pickup_radius: str = Form(""),
    pickup_unit: str = Form(""),
    price_min: str = Form(""),
    price_max: str = Form(""),
    us_postal_code: str = Form(DEFAULT_US_DELIVERY_POSTAL_CODE),
    file: UploadFile = File(...),
):
    """通过上传 Excel 文件批量查询"""
    cleanup_tasks()

    fs = free_shipping.strip().lower() == "true"
    ss = search_strategy.strip()
    if ss not in ("best_match", "category_lock"):
        ss = "category_lock"

    key_mode = input_type == "site_key"
    if (key_mode and site != "auto") or (not key_mode and site not in SITES):
        raise HTTPException(status_code=400, detail="不支持的站点")
    options = _validated_search_options(
        site, ss, fs, ebay_sort, delivery_country, delivery_postal_code,
        pickup_country, pickup_postal_code, pickup_radius, pickup_unit,
        price_min, price_max, us_postal_code,
    )

    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择要上传的 Excel 文件")

    fname_lower = file.filename.lower()
    if not (
        fname_lower.endswith(".xlsx")
        or fname_lower.endswith(".xlsm")
        or fname_lower.endswith(".xls")
    ):
        raise HTTPException(
            status_code=400, detail="仅支持 .xlsx、.xlsm、.xls 文件"
        )

    try:
        content = await file.read()
        keywords, input_type_val, total_rows, skipped_rows, file_name = (
            _parse_excel_keywords_from_bytes(content, file.filename, site_key_mode=key_mode)
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Excel 解析失败: {str(e)}"
        )

    if not keywords:
        raise HTTPException(
            status_code=400, detail="Excel 中未读取到有效的 SKU 或 OE 数据"
        )

    file_info = {
        "fileName": file_name,
        "totalRows": total_rows,
        "skippedRows": skipped_rows,
        "inputType": input_type_val,
    }
    if key_mode:
        targets, mapping, not_found = _resolve_site_key_targets(keywords)
        if not targets:
            raise HTTPException(status_code=400, detail="没有可查询的映射：" + "、".join(not_found[:10]))
        return _start_search_task(
            [], site, fs, ss, mapping, not_found, file_info,
            targets=targets, **options,
        )

    oe_list, sku_mapping, not_found_skus = _resolve_oe_list(
        keywords, input_type_val
    )
    return _start_search_task(
        oe_list, site, fs, ss, sku_mapping, not_found_skus, file_info,
        **options,
    )


@router.get("/api/status/{task_id}")
async def api_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")
    if task["status"] == "running":
        return {"status": "running", "progress": task.get("progress")}
    if task["status"] == "error":
        return {"status": "error", "msg": task["msg"]}
    return {
        "status": "done",
        "total_oe": task["total_oe"],
        "results": task["results"],
    }


@router.get("/api/check")
async def api_check():
    configured = bool(
        CLIENT_ID
        and CLIENT_SECRET
        and CLIENT_ID != "YOUR_APP_ID_HERE"
        and CLIENT_SECRET != "YOUR_CERT_ID_HERE"
    )
    return {"configured": configured}


# ═══════════════════════ SKU-OE 管理 API ═══════════════════════


@router.get("/api/sku/list")
async def api_sku_list():
    with _sku_oe_lock:
        if _mapping_schema == "site_key":
            items = [
                {"sku": key, "oe": oe, "middleCode": middle, "site": site.upper()}
                for key, (middle, site, oe) in sorted(_site_key_oe_map.items())
            ]
        else:
            items = [
                {
                    "sku": sku,
                    "oe": oe,
                    "middleCode": _custom_middle_codes.get(sku)
                    or _extract_middle_code(sku),
                }
                for sku, oe in sorted(_sku_oe_map.items())
            ]
    return {"items": items, "total": len(items), "readOnly": False,
            "siteKeyMode": _mapping_schema == "site_key"}


def _save_site_key_entry(original_key: str | None, key: str, oe: str) -> None:
    """保留四列表和现有公式；文件保存成功后才更新查询用的内存映射。"""
    global _site_key_oe_map, _sku_oe_map
    parts = _split_site_key(key)
    if not parts:
        raise HTTPException(status_code=400, detail="中间码+站点格式错误，应如 10144US、10144UK、10144DE")
    if not oe:
        raise HTTPException(status_code=400, detail="OE 号不能为空")
    if oe.startswith("="):
        raise HTTPException(status_code=400, detail="OE 号不能以 = 开头")
    with _sku_oe_lock:
        if _mapping_schema != "site_key":
            raise HTTPException(status_code=409, detail="当前不是中间码+站点四列表，请刷新映射表")
        wb = None
        temp_path = None
        try:
            source_stat = os.stat(SKU_OE_FILE)
            wb = load_workbook(SKU_OE_FILE)
            ws = wb.active
            headers = [ws.cell(1, col).value for col in range(1, 5)]
            if not ("中间码" in str(headers[0] or "") and "站点" in str(headers[0] or "")
                    and "OE" in str(headers[3] or "").upper()):
                raise HTTPException(status_code=409, detail="Excel 表头已变化，请先核对四列表")
            positions: dict[str, int] = {}
            for row in range(2, ws.max_row + 1):
                raw = ws.cell(row, 1).value
                if raw is None or not str(raw).strip():
                    continue
                existing = str(raw).strip().upper()
                if existing in positions:
                    raise HTTPException(status_code=409, detail=f"Excel 中存在重复映射键：{existing}")
                positions[existing] = row
            if original_key is None:
                if key in positions:
                    raise HTTPException(status_code=409, detail=f"中间码+站点 {key} 已存在，请使用编辑")
                row = ws.max_row + 1
                for col in range(1, 5):
                    ws.cell(row, col)._style = copy(ws.cell(row - 1, col)._style)
                ws.cell(row, 2, f"=LEFT(A{row},LEN(A{row})-2)")
                ws.cell(row, 3, f"=RIGHT(A{row},2)")
            else:
                row = positions.get(original_key)
                if row is None:
                    raise HTTPException(status_code=409, detail=f"原映射 {original_key} 不存在，请刷新后重试")
                if key != original_key and key in positions:
                    raise HTTPException(status_code=409, detail=f"中间码+站点 {key} 已存在")
            ws.cell(row, 1, key)
            ws.cell(row, 4, oe)
            updated: dict[str, tuple[str, str, str]] = {}
            for data_row in range(2, ws.max_row + 1):
                raw_key = ws.cell(data_row, 1).value
                if raw_key is None or not str(raw_key).strip():
                    continue
                normalized = str(raw_key).strip().upper()
                row_parts = _split_site_key(normalized)
                if row_parts:
                    raw_oe = ws.cell(data_row, 4).value
                    updated[normalized] = (row_parts[0], row_parts[1], str(raw_oe).strip() if raw_oe is not None else "")
            # 同目录临时文件 + 原子替换，避免保存失败时损坏源文件或污染内存。
            fd, temp_path = tempfile.mkstemp(prefix="sku-oe-", suffix=".xlsx", dir=str(Path(SKU_OE_FILE).parent))
            os.close(fd)
            wb.save(temp_path)
            wb.close()
            wb = None
            current_stat = os.stat(SKU_OE_FILE)
            if (current_stat.st_mtime_ns, current_stat.st_size) != (source_stat.st_mtime_ns, source_stat.st_size):
                raise HTTPException(status_code=409, detail="Excel 文件保存期间被其他程序修改，请刷新后重试")
            os.replace(temp_path, SKU_OE_FILE)
            temp_path = None
        except HTTPException:
            raise
        except (OSError, PermissionError) as exc:
            raise HTTPException(status_code=500, detail=f"保存 Excel 失败，文件可能正在被占用：{exc}") from exc
        finally:
            if wb is not None:
                wb.close()
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        _site_key_oe_map = updated
        _sku_oe_map = {item_key: item[2] for item_key, item in updated.items() if item[2]}


def _require_writable_legacy_map() -> None:
    if _mapping_schema == "site_key":
        raise HTTPException(
            status_code=409,
            detail="当前为“中间码+站点”四列表；删除和整表导入暂不支持，请使用新增或编辑",
        )


@router.post("/api/sku/add")
async def api_sku_add(request: Request):
    data = await request.json()
    if not data:
        raise HTTPException(status_code=400, detail="缺少数据")
    if _mapping_schema == "site_key":
        key = str(data.get("sku") or "").strip().upper()
        oe = str(data.get("oe") or "").strip()
        _save_site_key_entry(None, key, oe)
        return {"success": True, "sku": key, "oe": oe}

    sku = data.get("sku", "").strip()
    oe = data.get("oe", "").strip()
    middle_code = data.get("middleCode", "").strip()

    if not sku or not oe:
        raise HTTPException(status_code=400, detail="SKU 和 OE 都不能为空")

    with _sku_oe_lock:
        if sku in _sku_oe_map:
            raise HTTPException(
                status_code=400, detail=f"SKU '{sku}' 已存在"
            )
        _sku_oe_map[sku] = oe
        if middle_code:
            _custom_middle_codes[sku] = middle_code

    if save_sku_oe_map():
        return {"success": True, "sku": sku, "oe": oe, "middleCode": middle_code}
    else:
        with _sku_oe_lock:
            _sku_oe_map.pop(sku, None)
            _custom_middle_codes.pop(sku, None)
        raise HTTPException(status_code=500, detail="保存到 Excel 文件失败")


@router.post("/api/sku/update")
async def api_sku_update(request: Request):
    data = await request.json()
    if not data:
        raise HTTPException(status_code=400, detail="缺少数据")
    if _mapping_schema == "site_key":
        original = str(data.get("originalSku") or data.get("sku") or "").strip().upper()
        key = str(data.get("sku") or "").strip().upper()
        oe = str(data.get("oe") or "").strip()
        _save_site_key_entry(original, key, oe)
        return {"success": True, "sku": key, "oe": oe}

    sku = data.get("sku", "").strip()
    oe = data.get("oe", "").strip()
    middle_code = data.get("middleCode", "").strip()

    if not sku or not oe:
        raise HTTPException(status_code=400, detail="SKU 和 OE 都不能为空")

    with _sku_oe_lock:
        if sku not in _sku_oe_map:
            raise HTTPException(
                status_code=400, detail=f"SKU '{sku}' 不存在"
            )
        old_oe = _sku_oe_map[sku]
        old_mc = _custom_middle_codes.get(sku)
        _sku_oe_map[sku] = oe
        if middle_code:
            _custom_middle_codes[sku] = middle_code
        else:
            _custom_middle_codes.pop(sku, None)

    if save_sku_oe_map():
        return {"success": True, "sku": sku, "oe": oe, "middleCode": middle_code}
    else:
        with _sku_oe_lock:
            _sku_oe_map[sku] = old_oe
            if old_mc is not None:
                _custom_middle_codes[sku] = old_mc
            else:
                _custom_middle_codes.pop(sku, None)
        raise HTTPException(status_code=500, detail="保存到 Excel 文件失败")


@router.post("/api/sku/delete")
async def api_sku_delete(request: Request):
    _require_writable_legacy_map()
    data = await request.json()
    if not data:
        raise HTTPException(status_code=400, detail="缺少数据")

    sku = data.get("sku", "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="缺少 SKU")

    with _sku_oe_lock:
        if sku not in _sku_oe_map:
            raise HTTPException(
                status_code=400, detail=f"SKU '{sku}' 不存在"
            )
        old_oe = _sku_oe_map.pop(sku)

    if save_sku_oe_map():
        return {"success": True, "sku": sku}
    else:
        with _sku_oe_lock:
            _sku_oe_map[sku] = old_oe
        raise HTTPException(status_code=500, detail="保存到 Excel 文件失败")


@router.post("/api/sku/lookup")
async def api_sku_lookup(request: Request):
    data = await request.json()
    if not data or "skus" not in data:
        raise HTTPException(status_code=400, detail="缺少 SKU 列表")

    skus = data["skus"]
    results: list[dict] = []
    not_found: list[str] = []

    with _sku_oe_lock:
        for sku in skus:
            sku = sku.strip()
            if sku:
                if _mapping_schema == "site_key":
                    entry = _site_key_oe_map.get(sku.upper())
                    oe = entry[2] if entry else ""
                else:
                    oe = _sku_oe_map.get(sku) or _middle_code_oe_map.get(sku.upper())
                if oe:
                    result = {"sku": sku, "oe": oe}
                    if _mapping_schema == "site_key":
                        result["site"] = entry[1].upper()
                    results.append(result)
                else:
                    not_found.append(sku)

    return {
        "found": results,
        "not_found": not_found,
        "total": len(results),
    }


@router.post("/api/sku/refresh")
async def api_sku_refresh():
    if not load_sku_oe_map():
        raise HTTPException(status_code=500, detail="对照表重新加载失败，请检查文件、表头和重复键")
    return {"success": True, "total": len(_site_key_oe_map) if _mapping_schema == "site_key" else len(_sku_oe_map)}


@router.post("/api/sku/import")
async def api_sku_import(file: UploadFile = File(...)):
    """从 Excel 文件批量导入 SKU-OE 映射（覆盖式）"""
    global _sku_oe_map
    _require_writable_legacy_map()

    if not file.filename:
        raise HTTPException(
            status_code=400, detail="请选择要导入的 Excel 文件"
        )

    fname_lower = file.filename.lower()
    if not (
        fname_lower.endswith(".xlsx")
        or fname_lower.endswith(".xlsm")
        or fname_lower.endswith(".xls")
    ):
        raise HTTPException(
            status_code=400, detail="仅支持 .xlsx、.xlsm、.xls 文件"
        )

    try:
        content = await file.read()
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            wb.close()
            raise HTTPException(
                status_code=400, detail="Excel 文件没有工作表"
            )

        rows = list(ws.iter_rows(min_row=1, values_only=True))
        wb.close()

        if len(rows) < 2:
            raise HTTPException(
                status_code=400,
                detail="Excel 文件至少需要表头+1行数据",
            )

        header = rows[0]

        def norm(v: object) -> str:
            return re.sub(r"[\s_]", "", str(v or "")).lower()

        col_sku = col_oe = -1
        for i, h in enumerate(header):
            n = norm(h)
            if n in ("sku", "skuid", "skuno"):
                col_sku = i
            elif n in (
                "oe",
                "主oe",
                "主oeno",
                "oeno",
                "oenumber",
                "oenr",
                "partnumber",
                "partno",
            ):
                col_oe = i

        if col_sku < 0:
            col_sku = 0
        if col_oe < 0:
            col_oe = 1

        new_map: dict[str, str] = {}
        total_rows = 0
        skipped_rows = 0
        for row in rows[1:]:
            total_rows += 1
            sku = (
                str(row[col_sku]).strip()
                if len(row) > col_sku and row[col_sku]
                else ""
            )
            oe = (
                str(row[col_oe]).strip()
                if len(row) > col_oe and row[col_oe]
                else ""
            )
            if not sku or not oe:
                skipped_rows += 1
                continue
            new_map[sku] = oe

        if not new_map:
            raise HTTPException(
                status_code=400,
                detail="Excel 中未读取到有效的 SKU-OE 数据",
            )

        # 增量合并：没有的追加，有的覆盖
        with _sku_oe_lock:
            old_skus = set(_sku_oe_map.keys())
            new_skus = set(new_map.keys())
            created = len(new_skus - old_skus)
            updated = len(new_skus & old_skus)
            _sku_oe_map.update(new_map)

        save_sku_oe_map()

        return {
            "success": True,
            "totalRows": total_rows,
            "skippedRows": skipped_rows,
            "imported": len(new_map),
            "created": created,
            "updated": updated,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Excel 解析失败: {str(e)}"
        )


@router.post("/api/export")
async def api_export(request: Request, background_tasks: BackgroundTasks):
    """服务端生成带图片的 Excel 文件"""
    data = await request.json()
    if not data or "items" not in data:
        raise HTTPException(status_code=400, detail="缺少导出数据")

    items = data["items"]
    if not items:
        raise HTTPException(status_code=400, detail="没有可导出的商品")

    wb = Workbook()
    ws = wb.active
    ws.title = "eBay Results"

    headers = [
        "OE",
        "Price",
        "Title",
        "Seller",
        "Rate",
        "Shipping",
        "Listed At",
        "Ends At",
        "Link",
        "Images",
        "Input Key",
        "Site",
    ]
    col_widths = [16, 12, 50, 14, 8, 12, 23, 23, 40, 18, 18, 10]
    for c, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=c, value=h)
        font = copy(cell.font)
        font.bold = True
        cell.font = font
        ws.column_dimensions[get_column_letter(c)].width = w

    img_height = 80
    row_height_px = img_height + 10

    for i, item in enumerate(items, 2):
        ws.cell(row=i, column=1, value=item.get("oe", ""))
        ws.cell(row=i, column=2, value=item.get("price", ""))
        ws.cell(row=i, column=3, value=item.get("title", ""))
        ws.cell(row=i, column=4, value=item.get("seller", ""))
        fb = item.get("sellerFeedback", "")
        ws.cell(row=i, column=5, value=f"{fb}%" if fb else "")
        ws.cell(row=i, column=6, value=item.get("shipping", ""))
        ws.cell(row=i, column=7, value=item.get("listedAt", ""))
        ws.cell(row=i, column=8, value=item.get("endsAt", ""))
        ws.cell(row=i, column=11, value=item.get("inputKey", ""))
        ws.cell(row=i, column=12, value=item.get("site", ""))
        link = item.get("link", "")
        if link:
            cell = ws.cell(row=i, column=9, value=link)
            cell.hyperlink = link
            font = copy(cell.font)
            font.color = "0563C1"
            font.underline = "single"
            cell.font = font

        img_url = (item.get("images") or [None])[0]
        if img_url:
            try:
                resp = _requests.get(img_url, timeout=10, verify=False)
                if resp.status_code == 200:
                    img_data = BytesIO(resp.content)
                    xl_img = XlImage(img_data)
                    xl_img.height = img_height
                    xl_img.width = img_height
                    anchor = f"J{i}"
                    ws.add_image(xl_img, anchor)
            except Exception:
                pass

        ws.row_dimensions[i].height = row_height_px * 0.75

    tmp = tempfile.NamedTemporaryFile(
        suffix=".xlsx", delete=False, prefix="ebay_export_"
    )
    wb.save(tmp.name)
    tmp.close()
    tmp_path = tmp.name

    background_tasks.add_task(_safe_remove, tmp_path)

    return FileResponse(
        tmp_path,
        filename=f"ebay_export_{int(time.time())}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _safe_remove(path: str) -> None:
    """安全删除临时文件"""
    try:
        os.remove(path)
    except OSError:
        pass


# ── 独立运行入口（测试用）──
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    _test_app = FastAPI(title="eBay 价格查询工具（独立测试）")

    # 异常处理器：把 HTTPException 转为前端期望的 {"error": "..."} 格式
    @_test_app.exception_handler(HTTPException)
    async def _http_exception_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    _test_app.include_router(router, prefix="/ebay-tool-api")

    # 挂载前端静态文件
    _frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "ebay-tool"
    _test_app.mount("/ebay-tool", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")

    @_test_app.get("/")
    async def _redirect():
        return RedirectResponse(url="/ebay-tool/")

    print("=" * 50)
    print("  eBay 价格查询工具（测试模式）")
    print("  访问地址: http://localhost:8010")
    print("=" * 50)
    # 独立测试入口不经过 ERP 会话和内部 Token，只允许本机访问。
    uvicorn.run(_test_app, host="127.0.0.1", port=8010)
