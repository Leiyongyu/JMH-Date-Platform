from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import socket
import statistics
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# 备用 User-Agent 池，用于重试时切换身份
_BACKUP_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

SUPPORTED_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif"}

BING_SEARCH_URL = "https://www.bing.com/images/search"
BAIDU_JSON_URL = "https://image.baidu.com/search/acjson"
DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/"
DUCKDUCKGO_IMG_API = "https://duckduckgo.com/i.js"
GOOGLE_IMG_SEARCH_URL = "https://www.google.com/search"
YANDEX_IMG_SEARCH_URL = "https://yandex.com/images/search"
BIGBIGWORK_SEARCH_URL = "https://www.bigbigwork.com/sr/images"

# DNS 预解析缓存
_dns_cache: dict[str, list[tuple[str, int]]] = {}
_dns_cache_lock = asyncio.Lock()

# 常见图库/水印站点（搜索引擎预览小图中常有水印）
_STOCK_WATERMARK_DOMAINS = {
    # 国际大图库（预览图/小图普遍带水印）
    "shutterstock.com", "gettyimages", "istockphoto.com", "istock.com",
    "123rf.com", "adobestock.com", "alamy.com", "depositphotos.com",
    "dreamstime.com", "bigstockphoto.com", "fotolia.com", "canstockphoto.com",
    "stock.adobe.com", "pond5.com", "crestock.com", "stockphoto.com",
    "vecteezy.com", "vecteezy.net", "vecteezy",
    "storyblocks.com", "envato.com", "photodune.net",
    "rawpixel.com", "freeimages.com", "picjumbo.com", "burst.shopify.com",
    "kaboompics.com", "stocksnap.io", "gratisography.com", "lifeofpix.com",
    "morguefile.com", "rgbstock.com", "stockvault.net", "deviantart.com",
    # 国内图库
    "visualchina.com", "vcg.com", "hellorf.com", "tukuchina.cn",
    "nipic.com", "photophoto.cn", "quanjing.com", "originoo.com",
    "veer.com", "huitu.com", "ssyer.com", "58pic.com", "588ku.com",
    "ibaotu.com", "maka.im", "chuangkit.com", "dianshang.com",
    # 低质量/预览图站点
    "pexels.com", "unsplash.com", "pixabay.com", "freepik.com",
    "vectorstock.com", "clipart.com", "flickr.com/photos",
    # 品牌水印/Logo 站点（预览图普遍带有厂商 Logo）
    "ylcnc.com", "ylcnc.net", "autopartsway.com", "carparts.com",
    "rockauto.com", "partsavatar.ca", "autozone.com",
    "oreillyauto.com", "advanceautoparts.com", "napaonline.com",
    "carid.com", "jcwhitney.com", "summitracing.com", "jegs.com",
    "speedwaymotors.com", "andysautosport.com", "realoem.com",
    "buyautoparts.com", "autohausaz.com", "fcpeuro.com",
    "eeuroparts.com", "pelicanparts.com", "turnermotorsport.com",
    "ecstuning.com", "urotuning.com", "bmp-tuning.com",
    "catalog.com", "parts-catalog.com", "oempartscatalog.com",
    "illustration", "label", "tag",  # URL 路径含这些关键词的通常带水印/标注
}

# 搜索词中排除的关键词（图纸、示意图、广告等非实拍内容）
_DIAGRAM_EXCLUDE_KEYWORDS = [
    "-diagram -drawing -blueprint -schematic -sketch -lineart",
    "-illustration -3d render -rendering -vector -cartoon",
    "-chart -graph -infographic -flowchart -cad",
]

# 电商产品图：作为参考图时非常有价值，不应过滤
# （仅保留名单，用于日志/来源标记，不用于拦截）
_ECOMMERCE_DOMAINS = {
    "amazon.com/images", "amazonaws.com", "ebay.com", "walmartimages.com",
    "homedepot.com", "aliexpress.com", "alibaba.com/product", "alicdn.com",
    "shopify.com", "walmart.com", "target.com",
}


# 常见无关场景域名/路径关键词（根据 query 类型动态使用）
_PWC_SCENE_BLOCK_KEYWORDS = {
    "beach", "dock", "marina", "pier", "trailer", "showroom", "sand", "sandy",
    "waterfront", "harbor", "harbour", "boat-show", "boatshow", "waterscooter",
    "scooter-rental", "rental", "tour", "jetski-rental", "waverunner-rental",
}

_AUTOMOTIVE_SCENE_BLOCK_KEYWORDS = {
    # 整车外观/展示类
    "exterior", "side-view", "sideview", "side_view", "car-profile", "car_profile",
    "full-car", "full_car", "fullcar", "carporn", "carwallpaper", "car-wallpaper",
    "showroom", "car-show", "carshow", "car_show", "dealership", "garage-shot",
    # 风景/驾驶/与产品无关
    "scenic", "roadtrip", "landscape", "sunset", "bridge", "mountain", "highway",
    # 新闻/测评配图，容易是整车图
    "review-photos", "first-drive", "press-photo", "pressphoto", "press-release",
}

_GENERIC_SCENE_BLOCK_KEYWORDS = {
    "wallpaper", "showroom", "car-show", "carshow", "gallery", "posters",
}

# 与汽车/汽配场景明显无关的 URL 关键词
_IRRELEVANT_URL_KEYWORDS = {
    "cat", "kitten", "kittens", "puppy", "dog", "pet", "pets", "animal",
    "fashion", "runway", "model-walk", "wedding", "dress", "gown", "beauty",
    "makeup", "cosmetic", "celebrity", "portrait", "woman-in-dress",
    "waterfall", "landscape", "sunset-beach", "nature-scenery", "mountain-view",
    "food", "recipe", "restaurant", "flower", "flowers", "wedding-dress",
    "swimsuit", "bikini", "lingerie", "modeling", "fashion-show",
}

_SCENE_TYPES = ("vehicle_exterior", "installation", "product_detail", "workshop")

_AUTOMOTIVE_QUERY_HINTS = (
    "car", "vehicle", "auto", "automotive", "engine", "fuel", "jeep", "truck",
    "suv", "mechanic", "garage", "part", "install", "wrangler", "honda", "ford",
    "chevy", "chevrolet", "bmw", "toyota", "workshop", "tank", "sensor", "pump",
)


# ── OCR 文字检测（pytesseract，可选依赖）──
_OCR_READER = None
_OCR_CHECKED = False


def _get_ocr_reader():
    """惰性加载 pytesseract。（无状态，只做调用封装）"""
    global _OCR_READER, _OCR_CHECKED
    if _OCR_CHECKED:
        return _OCR_READER
    _OCR_CHECKED = True
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _OCR_READER = pytesseract
    except Exception:
        pass
    return _OCR_READER


def _ocr_count_text_in_edges(img, w: int, h: int) -> int:
    """OCR 检测图片四角 + 底部边缘的文字数量。用于判断水印。"""
    reader = _get_ocr_reader()
    if reader is None:
        return 0
    try:
        edge_h = max(int(h * 0.15), 30)
        edge_w = max(int(w * 0.20), 30)
        total_text = 0
        for _name, box in [
            ("bottom", (0, h - edge_h, w, h)),
            ("left", (0, 0, edge_w, h)),
            ("right", (w - edge_w, 0, w, h)),
            ("top", (0, 0, w, edge_h)),
        ]:
            try:
                crop = img.crop(box)
                if crop.size[0] > 10 and crop.size[1] > 10:
                    data = reader.image_to_string(crop, lang="eng",
                        config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
                    chars = ''.join(c for c in data if c.isalnum())
                    total_text += len(chars)
            except Exception:
                pass
        return total_text
    except Exception:
        return 0


def _ocr_count_text_full(img, w: int, h: int) -> int:
    """OCR 检测全图的文字密度。文字过多 → 说明书/广告/图纸。"""
    reader = _get_ocr_reader()
    if reader is None:
        return 0
    try:
        scale = min(1.0, 800.0 / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        data = reader.image_to_string(img, lang="eng", config="--psm 6")
        chars = ''.join(c for c in data if c.isalnum())
        return len(chars)
    except Exception:
        return 0


# ── AI 查询提炼 ──

_AI_QUERY_REFINE_PROMPT = """You are a product keyword extractor for image search engines.
Given a raw search query that may contain SKU codes, part numbers, mixed Chinese/English text, and generic suffixes,
extract ONLY the actual product name and key attributes in natural English.
Remove all SKU codes, part number prefixes (e.g. JYKS-OTH-xxx), and generic suffixes like "product photo".

Context: this is for searching scene/usage/product images of an automotive/mechanical part on the web.
Include keywords that help find both installation/use context images AND product detail closeups.

Input raw query: {raw_query}

Reply with ONLY the refined English search keywords, no explanation, no JSON, no quotes.
Keep it under 25 words, natural, directly usable in an image search engine.
Examples:
  Input: "JYKS-OTH-230701-1254 product photo" → Output: ignition coil automotive part
  Input: "throttle body Honda Civic 1.5T component detail" → Output: throttle body Honda Civic engine part
  Input: "LZY-US-70015-0082 spare part" → Output: fuel injector automotive engine component"""


# ── AI 多角度搜索词生成 ──
# 让 AI 分析产品信息（标题、功能、适配车型、品质描述），
# 识别产品类型后生成 3 个不同角度的搜索词：
#   1. 场景/安装环境图（如"BMW 发动机舱点火线圈安装"）
#   2. 产品细节图（如"汽车点火线圈零件特写"）
#   3. 行业/加工场景图（如"汽车修理厂引擎维修车间"）

_AI_MULTI_QUERY_PROMPT = """You are a product image search strategist for an e-commerce SOP image generation system.

Analyze the product information below to understand what kind of product this is (automotive part, mechanical component, industrial tool, household item, etc.), then generate exactly 4 DIVERSE English search queries suitable for finding relevant images on free stock photo / web image search engines.

Each query MUST target a DIFFERENT visual angle:
1. POPULAR VEHICLE EXTERIOR — Search for recent, popular vehicle model photos that match the product's compatibility.
   Focus on whole-car exterior / 3/4 front view / studio car photo of the HOTTEST compatible models mentioned in the listing.
   Prefer current-generation or best-selling trims for the US market when compatibility is broad.
   (e.g. "2024 Jeep Wrangler YJ exterior studio photo", "popular Honda Civic sedan front three quarter view", "best selling Ford F150 truck side profile")

2. INSTALLATION/USAGE — The product being installed, mounted, or used in its real environment. Show HOW this product is actually applied.
   (e.g. "mechanic installing ignition coil in engine bay", "replacing brake pads on car wheel", "installing refrigerator water filter")

3. QUALITY DETAIL — Close-up macro shots that highlight material quality, craftsmanship, texture, or premium build. Focus on what makes this product look high-quality.
   (e.g. "ignition coil copper core closeup high quality detail", "ceramic brake pad surface texture macro", "stainless steel precision machined part detail")

4. MANUFACTURING/WORKSHOP — Factory, production line, workshop, or industrial scenes related to this type of product. Show where or how this kind of product is made or the industry environment.
   (e.g. "auto parts factory assembly line workers", "precision CNC machining automotive components", "industrial workshop manufacturing mechanical parts")

Product Information:
- Title: {title}
- Function: {function}
- Compatibility: {compatibility}
- Quality: {quality}

Rules:
- Each query MUST be natural English, under 20 words
- Remove all SKU codes and part numbers — search engines don't understand those
- Focus on visually SEARCHABLE concepts (what would actually return useful images)
- If info is incomplete, infer reasonable context from the available details
- Think: "What kind of product is this? What visual environment does it belong to?"
- Make the 4 queries TRULY DIFFERENT from each other — not just slight word variations
- The first query MUST be a popular compatible vehicle exterior photo query, NOT the replacement part itself

Reply with ONLY a JSON array of exactly 4 strings. No other text. No markdown. No explanation.
Example output format: ["item context query", "installation query", "quality detail query", "manufacturing query"]"""


_VEHICLE_BRAND_RE = re.compile(
    r"\b(?:"
    r"BMW|Audi|Mercedes[-\s]?Benz|Toyota|Honda|Ford|Chevrolet|Chevy|Nissan|"
    r"Volkswagen|VW|Lexus|Hyundai|Kia|Mazda|Subaru|Jeep|Dodge|Ram|GMC|Cadillac|"
    r"Volvo|Porsche|Mini|Buick|Chrysler|Acura|Infiniti|Lincoln|Mitsubishi|"
    r"Harley[-\s]?Davidson|Ducati|KTM|Polaris|Can[-\s]?Am"
    r")\b"
    r"(?:\s+(?:[A-Z][A-Za-z0-9\-]{1,10}|[0-9]{1,3}[A-Z]{1,2})\b){0,3}",
    re.I,
)

_PART_STOP_WORDS = frozenset({
    "for", "with", "the", "and", "new", "oem", "fit", "fits", "compatible",
    "replacement", "direct", "unit", "set", "kit", "pair", "brand", "quality",
})


def _extract_vehicles_from_text(text: str, max_vehicles: int = 2) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for match in _VEHICLE_BRAND_RE.finditer(text or ""):
        v = re.sub(r"\s+", " ", match.group(0).strip())
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(v)
        if len(results) >= max_vehicles:
            break
    return results


def _extract_part_phrase(title: str) -> str:
    tokens = re.findall(r"[A-Za-z]+", title or "")
    picked: list[str] = []
    for token in tokens:
        low = token.lower()
        if low in _PART_STOP_WORDS or len(token) < 3:
            continue
        if _VEHICLE_BRAND_RE.search(token):
            continue
        picked.append(low)
        if len(picked) >= 4:
            break
    return " ".join(picked) or "automotive replacement part"


def _extract_year_from_text(text: str) -> str:
    years = re.findall(r"\b(19[89]\d|20[0-3]\d)\b", text or "")
    return years[0] if years else ""


def build_deterministic_scene_queries(product_context: dict[str, str]) -> list[str]:
    """从产品标题/描述提取车型与零件词，生成 4 条可执行的英文图片搜索词。"""
    title = (product_context.get("title") or "").strip()
    func = (product_context.get("function") or "").strip()
    compat = (product_context.get("compatibility") or "").strip()
    combined = " ".join(x for x in (title, func, compat) if x and x not in ("-", "..."))

    vehicles = _extract_vehicles_from_text(combined)
    vehicle = vehicles[0] if vehicles else ""
    year = _extract_year_from_text(combined)
    part = _extract_part_phrase(title)

    vehicle_query = " ".join(x for x in (year, vehicle) if x).strip()
    if not vehicle_query:
        vehicle_query = "popular SUV pickup truck"

    return [
        f"{vehicle_query} exterior front three quarter studio photo",
        f"{vehicle or 'car'} {part} installation mechanic garage".strip(),
        f"{part} automotive close up product photo",
        "auto repair workshop mechanic tools bench garage",
    ]


def queries_look_automotive(queries: list[str]) -> bool:
    if len(queries) < 2:
        return False
    hits = 0
    for q in queries:
        ql = q.lower()
        if any(h in ql for h in _AUTOMOTIVE_QUERY_HINTS):
            hits += 1
    return hits >= 2


def merge_scene_queries(
    deterministic: list[str],
    ai_queries: list[str] | None,
) -> list[str]:
    """优先使用 AI 查询，但每条都必须像汽配/车型搜索；否则回退到确定性模板。"""
    if ai_queries and len(ai_queries) >= 4 and queries_look_automotive(ai_queries):
        merged: list[str] = []
        for i in range(4):
            q = (ai_queries[i] or "").strip()
            if q and any(h in q.lower() for h in _AUTOMOTIVE_QUERY_HINTS):
                merged.append(q)
            else:
                merged.append(deterministic[i])
        return merged
    return deterministic[:4]


async def generate_multi_angle_queries(
    product_context: dict[str, str],
    api_base: str,
    api_key: str,
    model: str,
    timeout: int = 10,
) -> list[str]:
    """使用 AI 分析产品信息，生成 4 个不同角度的图片搜索词。

    返回 ["物品/场景关联图", "安装/使用图", "品质细节图", "加工/行业场景图"]，
    或者返回空列表（AI 不可用 / 产品信息不足时）。
    """
    if not api_key or not api_base:
        return []

    import httpx as _httpx

    title = product_context.get("title", "")
    function = product_context.get("function", "")
    compatibility = product_context.get("compatibility", "")
    quality = product_context.get("quality", "")

    # 信息不足则跳过
    meaningful = [v for v in [title, function, compatibility, quality]
                  if v and str(v) != "-" and len(v) > 3]
    if not meaningful:
        logger.debug("产品上下文信息不足，跳过 AI 多角度查询生成")
        return []

    prompt = _AI_MULTI_QUERY_PROMPT.format(
        title=title or "N/A",
        function=function or "N/A",
        compatibility=compatibility or "N/A",
        quality=quality or "N/A",
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "You are a search query strategist. Reply with ONLY a JSON array of exactly 4 strings. No markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with _httpx.AsyncClient(timeout=_httpx.Timeout(timeout)) as client:
            resp = await client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

                import json as _json

                # 尝试解析 JSON 数组
                try:
                    queries = _json.loads(content)
                    if isinstance(queries, list) and len(queries) >= 1:
                        result = [q.strip() for q in queries[:4] if q and q.strip()]
                        if result:
                            logger.info(f"AI 多角度查询({len(result)}): {result}")
                            return result
                except _json.JSONDecodeError:
                    pass

                # 备用：提取引号中的字符串
                import re as _re
                matches = _re.findall(r'"([^"]*)"', content)
                if matches:
                    result = [m.strip() for m in matches[:4] if m.strip()]
                    if result:
                        return result

                # 最终兜底：按行分割
                lines = [l.strip(' "\'-0123456789.') for l in content.split('\n') if l.strip()]
                result = [l for l in lines[:4] if l and len(l) > 5]
                if result:
                    return result

    except Exception as exc:
        logger.debug(f"AI 多角度查询生成失败: {exc}")

    return []


async def refine_query_with_ai(
    query: str,
    source_type: str = "mix",
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    timeout: int = 15,
) -> str:
    """使用 AI 提炼搜索关键词：去掉 SKU 编码，提取真实产品名称。"""
    if not api_key or not api_base:
        return _strip_sku_patterns(query)

    import httpx as _httpx

    prompt = _AI_QUERY_REFINE_PROMPT.format(raw_query=query)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a product keyword extractor. Reply with only keywords."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 80,
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with _httpx.AsyncClient(timeout=_httpx.Timeout(timeout)) as client:
            resp = await client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content and len(content) > 2:
                    logger.debug(f"AI 提炼查询: '{query[:50]}' → '{content[:60]}'")
                    return content
    except Exception as exc:
        logger.debug(f"AI 查询提炼失败: {exc}")

    return _strip_sku_patterns(query)


def _strip_sku_patterns(query: str) -> str:
    """去除查询字符串中明显的 SKU/料号编码模式。"""
    import re as _re
    q = query.strip()
    sku_pattern = _re.compile(r'\b[A-Z]{2,6}[-_][A-Z]{2,4}[-_]\d{4,8}[-_]\d{3,6}\b')
    q = sku_pattern.sub('', q).strip()
    q = _re.sub(r'\b\d{4,6}[-_][A-Z0-9]{2,4}\b', '', q).strip()
    q = _re.sub(r'\s+', ' ', q).strip()
    return q if q else query



class WebImageSearchService:

    """通过 Baidu / Bing / Yandex / DuckDuckGo / Google / 大作 图片搜索获取场景图、车型图、物品图。

    不需要 API Key；主引擎失败时自动降级到备用引擎。
    包含重试、多策略防盗链、DNS 预解析等容错机制。

    支持的引擎: baidu, bing, yandex, duckduckgo, google, bigbigwork, auto（自动尝试全部）
    auto 模式会根据是否配置了代理智能选择顺序：
      - 无代理（国内服务器）：优先百度、Yandex、Bing
      - 有代理：优先 Bing、DuckDuckGo、Google
    大作 (bigbigwork): 聚合全球设计社区灵感图片，适合找高质量场景参考图/设计参考，
    汽车零件术语命中率可能较低，作为补充来源。
    """

    # 需要主动加 Referer 的防盗链域名（常见汽车零件/论坛站点）
    _REFERER_DOMAINS = (
        "assets.turnermotorsport.com", "assets.ecstuning.com",
        "tiperformance.com.au", "sunnycourtyard.com.my",
        "rackcdn.com", "eurosports.com.sg",
        "fcpstatic.com", "fcp-media.com",
        "pelicanparts.com", "bimmerpost.com", "bimmerfest.com",
        "e90post.com", "f30post.com", "f80post.com", "g20post.com",
        "bimmerforums.com", "e46fanatics.com", "m3post.com",
        "rmeuropean.com", "escart.co.uk", "cdn.shopify.com",
        "vgy.me", "imgur.com", "postimg.cc", "ibb.co",
    )

    def __init__(
        self,
        timeout: int = 8,
        user_agent: str = "",
        max_image_size_mb: int = 5,
        engine: str = "bing",
        proxy: str = "",
    ) -> None:
        self.timeout = timeout
        self.max_image_size = max_image_size_mb * 1024 * 1024
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.engine = engine.lower()
        self.proxy = proxy.strip() or None
        self.client: httpx.AsyncClient | None = None
        self._dns_resolved: set[str] = set()

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            connect_timeout = max(3, self.timeout // 2)
            limits = httpx.Limits(max_connections=12, max_keepalive_connections=6)
            timeout = httpx.Timeout(self.timeout, connect=connect_timeout, read=self.timeout)
            client_kwargs: dict[str, Any] = {
                "timeout": timeout,
                "follow_redirects": True,
                "limits": limits,
                "headers": {
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,image/jpeg,image/png,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
                },
            }
            if self.proxy:
                client_kwargs["proxy"] = self.proxy
            self.client = httpx.AsyncClient(**client_kwargs)
        return self.client

    async def _pre_resolve_dns(self, host: str) -> None:
        """预先解析 DNS，避免首次连接时的 DNS 超时。"""
        if host in self._dns_resolved:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, socket.getaddrinfo, host, 443)
            self._dns_resolved.add(host)
            logger.debug(f"DNS 预解析完成: {host}")
        except Exception:
            pass  # DNS 预解析失败不阻塞主流程

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def search_images(self, query: str, max_results: int = 3) -> list[str]:
        """返回找到的图片 URL 列表。主引擎失败自动降级。

        引擎优先级（按 _engine_order）：大作 → Google → DuckDuckGo → Bing → Yandex → Baidu
        任一引擎成功即返回，全部失败才返回空列表。
        搜索词自动追加排除关键词（图纸/示意图/3D渲染等），优先返回实拍照片。
        """
        if not query or not query.strip():
            return []

        # 搜索词预处理：追加排除关键词，过滤图纸/示意图/3D渲染等非实拍内容
        clean_query = self._clean_search_query(query)

        engines = self._engine_order()
        last_err: Exception | None = None
        logger.debug(f"开始图片搜索 '{clean_query[:40]}'，引擎顺序: {engines}")

        for eng in engines:
            try:
                if eng == "bing":
                    urls = await self._search_bing(clean_query, max_results)
                elif eng == "duckduckgo":
                    urls = await self._search_duckduckgo(clean_query, max_results)
                elif eng == "google":
                    urls = await self._search_google(clean_query, max_results)
                elif eng == "yandex":
                    urls = await self._search_yandex(clean_query, max_results)
                elif eng == "bigbigwork":
                    urls = await self._search_bigbigwork(clean_query, max_results)
                else:
                    urls = await self._search_baidu(clean_query, max_results)
                if urls:
                    src_tag = "电商" if self._is_ecommerce_domain(urls[0]) else "普通"
                    logger.info(f"{eng}({src_tag}) 图片搜索 '{clean_query[:40]}' 返回 {len(urls)} 张")
                    return urls
            except Exception as exc:
                last_err = exc
                logger.warning(f"{eng} 图片搜索失败 '{clean_query[:30]}': {exc}")

        if last_err:
            logger.warning(f"所有引擎均搜索失败: {last_err}")
        return []

    async def download_images(
        self,
        query: str,
        save_dir: Path,
        max_results: int = 3,
        prefix: str = "",
        fast_mode: bool = False,
        scene_type: str = "",
    ) -> dict[str, Path]:
        """下载图片并返回 {url: local_path}。
        自动过滤：①图库水印域名 ②下载后检测到的水印图 ③过小图片。

        fast_mode=True 时（预览场景）：
        - 减少候选数（3x 而非 5x）
        - 跳过 OCR/水印/示意图重型检测（仅做 URL 级和尺寸过滤）
        - 并行下载图片
        """
        save_dir.mkdir(parents=True, exist_ok=True)
        # fast_mode 减少搜索候选
        multiplier = 3 if fast_mode else 5
        fetch_count = max(max_results * multiplier, 5)
        urls = await self.search_images(query, fetch_count)

        if not urls:
            logger.warning(f"图片搜索无结果: '{query[:50]}'")

        # 第一步：URL 级别预过滤（图库域名、不包含图片后缀、无关场景等）
        clean_urls: list[str] = []
        for url in urls:
            if self._is_stock_domain(url):
                logger.debug(f"过滤图库域名: {url[:60]}")
                continue
            if not self._is_relevant_scene_url(url, query, scene_type=scene_type):
                continue
            clean_urls.append(url)

        # fast_mode: 并行下载 + 跳过重型检测
        if fast_mode:
            tasks = []
            for idx, url in enumerate(clean_urls[: max(max_results * 6, 8)]):
                tasks.append(self._download_with_retry(url, save_dir, prefix, idx + 1, max_retries=1, request_timeout=6.0))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            saved: dict[str, Path] = {}
            for url, result in zip(clean_urls[:len(tasks)], results):
                if isinstance(result, Exception):
                    continue
                if result is None:
                    continue
                # 轻量检测：仅尺寸和格式
                try:
                    sz = result.stat().st_size
                    if sz < 8 * 1024 or sz > self.max_image_size:
                        result.unlink(missing_ok=True)
                        continue
                    if scene_type and not self._passes_fast_image_check(result, scene_type):
                        result.unlink(missing_ok=True)
                        continue
                except Exception:
                    continue
                saved[url] = result
                if len(saved) >= max_results:
                    break
            if not saved:
                logger.warning(f"图片搜索+下载后无有效结果(fast): '{query[:50]}' (候选{len(clean_urls)}个)")
            return saved

        # 完整模式：串行下载 + 完整检测
        saved = {}
        idx = 0
        for url in clean_urls:
            if len(saved) >= max_results:
                break
            idx += 1
            local_path = await self._download_with_retry(url, save_dir, prefix, idx)
            if local_path:
                # 第二步：OCR 水印/广告检测（优先）
                if self._has_watermark_ocr(local_path):
                    logger.debug(f"OCR 检测到水印/广告，丢弃: {local_path.name}")
                    try:
                        local_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue
                # 第三步：图像特征水印检测
                if self._has_watermark(local_path):
                    logger.debug(f"检测到水印，丢弃: {local_path.name}")
                    try:
                        local_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue
                # 第四步：过滤线稿/示意图 + OCR 图纸检测
                if self._is_likely_diagram(local_path):
                    logger.debug(f"检测到示意图/线稿，丢弃: {local_path.name}")
                    try:
                        local_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue
                saved[url] = local_path

        if not saved:
            logger.warning(f"图片搜索+下载后无有效结果: '{query[:50]}' (候选{len(clean_urls)}个)")
        return saved

    # ------------------------------------------------------------------
    # Bing 图片搜索（无 API Key，HTML 解析）
    # ------------------------------------------------------------------

    # 需要过滤的域名（Bing UI 资源 / 小图标）
    _BING_BLOCK_HOSTS = {
        "bing.com/sa/", "bing.com/rp/", "bing.com/fd/",
    }

    async def _search_bing(self, query: str, max_results: int) -> list[str]:
        client = await self._get_client()
        params: dict[str, str | int] = {
            "q": query,
            "first": 1,
            "FORM": "HDRSC2",
        }
        resp = await client.get(BING_SEARCH_URL, params=params)
        resp.raise_for_status()
        text = resp.text

        murls: list[str] = []       # 原始图片 URL（优先）
        murl_seen: set[str] = set()
        turls: list[str] = []       # Bing CDN 缩略图 URL（防盗链降级兜底）

        def _add_murl(raw: str) -> None:
            url = self._clean_url(raw)
            if url and self._is_image_url(url) and url not in murl_seen:
                murl_seen.add(url)
                murls.append(url)

        def _add_turl(raw: str) -> None:
            url = self._clean_url(raw)
            if url and url not in murl_seen and url not in turls:
                turls.append(url)

        # ---- 提取 murl（原始图片） ----

        # 方式 1：标准 JSON "murl":"http..."（国际版 Bing）
        for match in re.finditer(r'"murl"\s*:\s*"(https?://[^"]+)"', text):
            _add_murl(match.group(1))
            if len(murls) >= max_results:
                break

        # 方式 2：HTML 编码 &quot;murl&quot;:&quot;http...&quot;（cn.bing.com）
        if len(murls) < max_results:
            for match in re.finditer(
                r'&quot;murl&quot;\s*:\s*&quot;(https?://[^&"]+)',
                text,
            ):
                _add_murl(match.group(1))
                if len(murls) >= max_results:
                    break

        # 方式 3：&quot;murl&quot;:&quot;URL&quot; 含图片后缀（更精准匹配 cn.bing.com）
        if len(murls) < max_results:
            for match in re.finditer(
                r'&quot;murl&quot;\s*:\s*&quot;(https?://[^&"]+\.(?:jpg|jpeg|png)[^&"]*)',
                text, re.IGNORECASE,
            ):
                _add_murl(match.group(1))
                if len(murls) >= max_results:
                    break

        # ---- 提取 turl（Bing CDN 缩略图，防盗链兜底） ----

        # 方式 T1：标准 JSON "turl":"http..."（国际版）
        for match in re.finditer(r'"turl"\s*:\s*"(https?://[^"]+)"', text):
            _add_turl(match.group(1))
            if len(turls) >= max_results * 2:
                break

        # 方式 T2：HTML 编码 &quot;turl&quot;:&quot;http...&quot;（cn.bing.com）
        if len(turls) < max_results * 2:
            for match in re.finditer(
                r'&quot;turl&quot;\s*:\s*&quot;(https?://[^&"]+)',
                text,
            ):
                _add_turl(match.group(1))
                if len(turls) >= max_results * 2:
                    break

        # 方式 T3：class="mimg" 的缩略图 src（cn.bing.com）
        if len(turls) < max_results * 2:
            for match in re.finditer(
                r'<img[^>]*class="[^"]*mimg[^"]*"[^>]*src="(https?://[^"]+)"',
                text, re.IGNORECASE,
            ):
                _add_turl(match.group(1))
                if len(turls) >= max_results * 2:
                    break

        # 方式 T4：通用 <img> 标签（终极兜底）
        if len(turls) < max_results:
            for match in re.finditer(
                r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png)[^"]*)"',
                text, re.IGNORECASE,
            ):
                _add_turl(match.group(1))
                if len(turls) >= max_results * 2:
                    break

        # 合并：原图优先，CDN 兜底
        result = murls[: max_results * 3] + turls[: max_results * 3]
        logger.debug(f"Bing 搜索 '{query[:30]}' → {len(murls)} orig + {len(turls)} cdn")
        return result[: max_results * 6]

    # ------------------------------------------------------------------
    # 百度图片搜索（acjson 接口，免费无 Key）
    # ------------------------------------------------------------------

    async def _search_baidu(self, query: str, max_results: int) -> list[str]:
        """通过百度图片 acjson 接口搜索图片。"""
        client = await self._get_client()

        # 预热：先访问百度首页，获取必要 cookie（BAIDUID 等），避免 acjson 返回空
        try:
            await client.get(
                "https://www.baidu.com/",
                headers={
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                },
                timeout=5,
            )
        except Exception as exc:
            logger.debug(f"百度首页预热失败（忽略）: {exc}")

        params: dict[str, str | int] = {
            "tn": "resultjson_com",
            "word": query,
            "pn": 0,
            "rn": min(max_results * 4, 60),
            "ie": "utf-8",
            "oe": "utf-8",
            "ipn": "rj",
            "ct": "201326592",
            "fp": "result",
        }
        resp = await client.get(
            BAIDU_JSON_URL,
            params=params,
            headers={
                "Referer": "https://image.baidu.com/search/index?tn=baiduimage",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp.raise_for_status()
        text = resp.text

        # 处理百度 JSONP / JSON 响应
        data = self._parse_baidu_json(text)
        if data is None:
            raise ValueError("百度 JSON 解析失败")

        items = data.get("data", []) or []

        urls: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # 优先取原图 URL，其次 middleURL、thumbURL
            url = item.get("objURL") or item.get("middleURL") or item.get("thumbURL") or item.get("hoverURL")
            if url and isinstance(url, str) and url.startswith("http"):
                url = self._clean_url(url)
                if url and url not in urls:
                    urls.append(url)
            if len(urls) >= max_results:
                break

        logger.debug(f"百度搜索 '{query[:30]}' → {len(urls)} URLs")
        return urls

    @staticmethod
    def _parse_baidu_json(text: str) -> dict | None:
        """安全解析百度返回的 JSON/JSONP，处理各种编码问题。"""
        if not text:
            return None

        # 去除 JSONP 包装
        json_text = text.strip()
        if not json_text.startswith("{"):
            json_text = re.sub(r"^[^(]*\(", "", json_text)
            json_text = re.sub(r"\)\s*$", "", json_text)

        # 尝试 1：标准解析
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # 尝试 2：替换常见的非法转义序列
        # 百度有时在 JSON 字符串中混入未转义的反斜杠
        try:
            cleaned_text = json_text
            # 修复形如 \\u 但实际数据中的非法转义
            # 先尝试将 \x 类非法转义替换
            cleaned_text = re.sub(
                r'\\(?!["\\/bfnrtu])', r"\\\\", cleaned_text
            )
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass

        # 尝试 3：逐行解析，跳过损坏的行
        try:
            return json.loads(json_text, strict=False)
        except json.JSONDecodeError:
            pass

        logger.debug(f"百度 JSON 解析全部失败, 原始长度={len(text)}")
        return None

    # ------------------------------------------------------------------
    # DuckDuckGo 图片搜索（免费，全球可用，与 Bing 结果互补）
    # ------------------------------------------------------------------

    async def _search_duckduckgo(self, query: str, max_results: int) -> list[str]:
        """通过 DuckDuckGo i.js API 搜索图片。"""
        client = await self._get_client()

        # Step 1: 获取 vqd token（访问搜索页，带 cookies）
        vqd = await self._get_duckduckgo_vqd(client, query)
        if not vqd:
            raise ValueError("无法获取 DuckDuckGo vqd token")

        # Step 2: 调用图片搜索 API
        params: dict[str, str | int] = {
            "q": query,
            "vqd": vqd,
            "o": "json",
            "p": "1",
            "s": "0",
            "f": ",,,,,",
            "l": "us-en",
        }
        resp = await client.get(
            DUCKDUCKGO_IMG_API,
            params=params,
            headers={
                "Referer": f"https://duckduckgo.com/?q={query}&ia=images&iax=images",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", []) or []
        urls: list[str] = []
        seen: set[str] = set()

        for item in results:
            if not isinstance(item, dict):
                continue
            img_url = item.get("image") or item.get("url") or item.get("thumbnail", "")
            if not img_url or not img_url.startswith("http"):
                continue
            img_url = self._clean_url(img_url)
            if not img_url:
                continue
            # 过滤 DuckDuckGo 自身资源
            if "duckduckgo.com" in img_url.lower():
                continue
            if img_url not in seen:
                seen.add(img_url)
                urls.append(img_url)
            if len(urls) >= max_results:
                break

        logger.debug(f"DuckDuckGo 搜索 '{query[:30]}' → {len(urls)} URLs")
        return urls

    async def _get_duckduckgo_vqd(self, client: httpx.AsyncClient, query: str = "test") -> str | None:
        """从 DuckDuckGo 搜索页提取 vqd 反爬令牌。"""
        try:
            # 先访问首页建立 cookie
            await client.get(
                DUCKDUCKGO_SEARCH_URL,
                params={"q": query, "ia": "images", "iax": "images"},
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://duckduckgo.com/",
                },
                timeout=10,
            )
            resp = await client.get(
                DUCKDUCKGO_SEARCH_URL,
                params={"q": query, "ia": "images", "iax": "images"},
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=10,
            )
            resp.raise_for_status()
            text = resp.text

            # 从 HTML/JS 中提取 vqd token，格式更宽松
            for pattern in [
                r'vqd\s*=\s*["\']([\w-]+)["\']',
                r'vqd=["\']([\w-]+)["\']',
                r'"vqd":"([\w-]+)"',
                r"'vqd':'([\w-]+)'",
                r'vqd=([\w-]+)&',
                r'vqd%3D([\w-]+)',
            ]:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        except Exception as exc:
            logger.debug(f"获取 DuckDuckGo vqd 失败: {exc}")

        return None

    # ------------------------------------------------------------------
    # Yandex 图片搜索（HTML 解析，无需 API Key）
    # ------------------------------------------------------------------

    async def _search_yandex(self, query: str, max_results: int) -> list[str]:
        """通过 Yandex 图片搜索 HTML 页面提取图片 URL。"""
        client = await self._get_client()

        params: dict[str, str] = {"text": query}
        resp = await client.get(
            YANDEX_IMG_SEARCH_URL,
            params=params,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://yandex.com/images/",
            },
        )
        resp.raise_for_status()
        text = resp.text

        urls: list[str] = []
        seen: set[str] = set()

        def _add(raw: str) -> None:
            url = self._clean_url(raw)
            if url and url not in seen and self._is_image_url(url):
                seen.add(url)
                urls.append(url)

        # Yandex 常见数据格式 1：serp-item 的 origin 原图 URL
        for match in re.finditer(
            r'"origUrl"\s*:\s*"(https?://[^"]+)"', text, re.IGNORECASE
        ):
            _add(match.group(1))
            if len(urls) >= max_results:
                return urls

        # 数据格式 2：data-bem 或 JSON 中的 url
        if len(urls) < max_results:
            for match in re.finditer(
                r'"url"\s*:\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                text, re.IGNORECASE,
            ):
                _add(match.group(1))
                if len(urls) >= max_results:
                    break

        # 数据格式 3：img 标签（缩略图/原图）
        if len(urls) < max_results:
            for match in re.finditer(
                r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                text, re.IGNORECASE,
            ):
                _add(match.group(1))
                if len(urls) >= max_results:
                    break

        # 兜底：所有可能的图片 URL
        if len(urls) < max_results:
            for match in re.finditer(
                r'(https?://[^"<>\s]+\.(?:jpg|jpeg|png|webp)[^"<>\s]*)',
                text, re.IGNORECASE,
            ):
                _add(match.group(1))
                if len(urls) >= max_results * 2:
                    break

        logger.debug(f"Yandex 搜索 '{query[:30]}' → {len(urls)} URLs")
        return urls[:max_results]

    # ------------------------------------------------------------------
    # Google 图片搜索（HTML 解析，无需 API Key）
    # ------------------------------------------------------------------

    async def _search_google(self, query: str, max_results: int) -> list[str]:
        """通过 Google 图片搜索 HTML 页面提取图片 URL。

        从页面中的 AF_initDataCallback 或内嵌 JSON 数据提取图片链接。
        注意：国内服务器可能需要代理才能访问 Google。
        """
        client = await self._get_client()

        params: dict[str, str] = {
            "tbm": "isch",
            "q": query,
            "safe": "active",
            "hl": "en",
        }
        resp = await client.get(
            GOOGLE_IMG_SEARCH_URL,
            params=params,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        resp.raise_for_status()
        text = resp.text

        urls: list[str] = []
        seen: set[str] = set()

        def _add(raw: str) -> None:
            url = self._clean_url(raw)
            if url and url not in seen and self._is_image_url(url):
                seen.add(url)
                urls.append(url)

        # 方式 1：从 AF_initDataCallback 提取（主要数据格式）
        # Google 将图片数据编码在 script 标签的 AF_initDataCallback 调用中
        for match in re.finditer(r'"ou"\s*:\s*"(https?://[^"]+)"', text):
            _add(match.group(1))
            if len(urls) >= max_results:
                break

        # 方式 2：标准 img 标签中的 data-src（缩略图→原图映射）
        if len(urls) < max_results:
            for match in re.finditer(
                r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                text, re.IGNORECASE,
            ):
                _add(match.group(1))
                if len(urls) >= max_results:
                    break

        # 方式 3：提取所有可能的图片 URL（含编码格式）
        if len(urls) < max_results:
            for match in re.finditer(
                r'(https?://[^"<>\s]+\.(?:jpg|jpeg|png|webp)[^"<>\s]*)',
                text, re.IGNORECASE,
            ):
                _add(match.group(1))
                if len(urls) >= max_results * 2:
                    break

        logger.debug(f"Google 搜索 '{query[:30]}' → {len(urls[:max_results])}/{len(urls)} URLs")
        return urls[: max_results * 3]

    # ------------------------------------------------------------------
    # 大作 (bigbigwork) 图片搜索 - HTML 解析，无 API Key
    # 聚合全球设计社区的灵感图片，中文搜索优先，适合找高质量场景图/产品设计参考
    # ------------------------------------------------------------------

    async def _search_bigbigwork(self, query: str, max_results: int) -> list[str]:
        """通过大作 sr/images 搜索页面提取图片 URL。

        大作是中文设计师灵感搜索引擎，聚合全球设计资源。搜索词会自动翻译为
        多语言进行检索，获取设计社区中的高质量参考图。

        注意：
        - 该站对英文搜索词会转为中文翻译后搜索，汽车零件术语可能命中率较低
        - 搜索结果需要 VIP 才能查看大图，但预览缩略图仍可获取
        - 若搜索结果被 VIP 墙拦截，返回空列表降级到其他引擎
        """
        client = await self._get_client()

        # 第一步：搜索页（带浏览器伪装）
        try:
            resp = await client.get(
                BIGBIGWORK_SEARCH_URL,
                params={"w": query},
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
                    "Referer": "https://www.bigbigwork.com/",
                    "Cache-Control": "no-cache",
                },
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.text
        except Exception as exc:
            logger.debug(f"大作搜索页请求失败 '{query[:30]}': {exc}")
            return []

        # 第二步：检测是否被 VIP 墙 / 无结果
        if "没找到相关的图片" in text or "居然没找到" in text:
            logger.debug(f"大作无搜索结果 '{query[:30]}'")
            return []
        if "开通VIP" in text[:2000] and "sr/images" not in text[:500]:
            logger.debug(f"大作搜索结果被 VIP 拦截 '{query[:30]}'")
            return []

        urls: list[str] = []
        seen: set[str] = set()

        def _add(raw: str) -> None:
            url = self._clean_url(raw)
            if url and url not in seen:
                # 过滤大作自身的 UI 资源
                url_lower = url.lower()
                if any(x in url_lower for x in ("/rp/", "/sa/", "favicon", "logo", "icon", "/static/")):
                    return
                seen.add(url)
                urls.append(url)

        # 方式 1：提取 data-src / data-original（懒加载主图）
        for match in re.finditer(
            r'data-(?:src|original)\s*=\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
            text, re.IGNORECASE,
        ):
            _add(match.group(1))
            if len(urls) >= max_results * 3:
                break

        # 方式 2：提取 src 属性中的图片 URL（非缩略图）
        if len(urls) < max_results:
            for match in re.finditer(
                r'<img[^>]+src\s*=\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                text, re.IGNORECASE,
            ):
                raw_url = match.group(1)
                # 跳过明显的缩略图/占位符（URL中包含 thumb、placeholder 等）
                url_lower = raw_url.lower()
                if any(x in url_lower for x in ("placeholder", "loading", "blank", "1x1", "pixel")):
                    continue
                _add(raw_url)
                if len(urls) >= max_results * 3:
                    break

        # 方式 3：提取 JSON 内嵌的图片 URL
        if len(urls) < max_results:
            for match in re.finditer(
                r'"(?:imgUrl|imageUrl|url|src)"\s*:\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                text, re.IGNORECASE,
            ):
                _add(match.group(1))
                if len(urls) >= max_results * 2:
                    break

        # 方式 4：兜底 - 所有可能的图片 URL
        if len(urls) < max_results:
            for match in re.finditer(
                r'(https?://[^"<>\s]+\.(?:jpg|jpeg|png|webp)[^"<>\s]*)',
                text, re.IGNORECASE,
            ):
                raw_url = match.group(1)
                url_lower = raw_url.lower()
                # 过滤静态资源/UI元素
                if any(x in url_lower for x in ("/fa/", "/ru/", "/sr/", "statics", "assets/js",
                                                  "logo", "icon", "avatar", "favicon", "banner")):
                    continue
                _add(raw_url)
                if len(urls) >= max_results * 3:
                    break

        logger.debug(f"大作搜索 '{query[:30]}' → {len(urls)} URLs")
        return urls[: max_results * 3]

    # ------------------------------------------------------------------
    # 下载 & 格式处理（带重试+多策略防盗链）
    # ------------------------------------------------------------------

    async def _download_with_retry(
        self,
        url: str,
        save_dir: Path,
        prefix: str,
        idx: int,
        max_retries: int = 3,
        request_timeout: float | None = None,
    ) -> Path | None:
        """带指数退避和多策略防盗链的图片下载。

        重试策略（按顺序）：
          1. 直接下载（无 Referer）
          2. Bing Referer 重试
          3. 同源 Referer 重试（模拟从该站点内链访问）
          4. 切换 UA + Bing Referer 重试
        """
        client = await self._get_client()

        # 预解析目标域名 DNS
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname
            if host:
                await self._pre_resolve_dns(host)
        except Exception:
            pass

        # 从 URL 提取同源 Referer
        source_referer = ""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            source_referer = f"{parsed.scheme}://{parsed.hostname}/"
        except Exception:
            pass

        last_error: Exception | None = None
        last_status: int | None = None

        for attempt in range(max_retries):
            headers: dict[str, str] = {}
            if attempt == 0:
                # 尝试 1：不加 Referer，直接下载
                pass
            elif attempt == 1:
                # 尝试 2：加 Bing Referer
                headers["Referer"] = "https://www.bing.com/"
            else:
                # 尝试 3：加同源 Referer + 备用 UA
                headers["Referer"] = source_referer or "https://www.bing.com/"
                headers["User-Agent"] = _BACKUP_USER_AGENTS[attempt % len(_BACKUP_USER_AGENTS)]

            try:
                get_kwargs: dict[str, Any] = {"headers": headers} if headers else {}
                if request_timeout is not None:
                    get_kwargs["timeout"] = request_timeout
                resp = await client.get(url, **get_kwargs)
                resp.raise_for_status()

                if not resp.content:
                    return None
                content_length = len(resp.content)
                if content_length > self.max_image_size:
                    logger.debug(f"图片超过大小限制: {url[:50]} ({content_length}B)")
                    return None
                if content_length < 2 * 1024:
                    logger.debug(f"图片过小 (<2KB)，丢弃: {url[:50]}")
                    return None

                ext = self._guess_ext(url, resp.headers.get("content-type", ""))
                filename = f"{prefix}web_ref_{idx}{ext}"
                path = save_dir / filename
                path.write_bytes(resp.content)
                jpg_path = self._ensure_jpg(path)
                if jpg_path is None:
                    logger.debug(f"图片格式不支持，跳过: {path.name}")
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return None
                if jpg_path != path:
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass

                if attempt > 0:
                    logger.debug(f"重试 {attempt} 成功: {url[:60]}")
                return jpg_path

            except httpx.HTTPStatusError as exc:
                last_status = exc.response.status_code
                last_error = exc
                # 403/404 大概率无解，但换 Referer 可能有效；429 需要等待
                if last_status == 429 and attempt < max_retries - 1:
                    wait = (2 ** attempt) * 1.5 + random.uniform(0, 1)
                    logger.debug(f"429 限流 {url[:50]}，等待 {wait:.1f}s 重试")
                    await asyncio.sleep(wait)
                    continue
                if last_status in (403, 401) and attempt < max_retries - 1:
                    logger.debug(f"{last_status} 防盗链 {url[:50]}，换策略重试")
                    continue
                if last_status in (404, 410):
                    break  # 资源不存在，无需重试
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 0.8 + random.uniform(0, 0.5)
                    logger.debug(f"网络异常 {url[:50]}，{wait:.1f}s 后重试: {exc}")
                    await asyncio.sleep(wait)
                    continue
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0 + random.uniform(0, 0.5))
                    continue
                break

        if last_error:
            logger.debug(f"下载失败(已重试{max_retries}次): {url[:60]} | {type(last_error).__name__}: {last_error}")
        return None

    @staticmethod
    def _guess_ext(url: str, content_type: str = "") -> str:
        url_path = url.split("?")[0].split("#")[0]
        ext = Path(url_path).suffix.lower()
        if ext in SUPPORTED_IMG_EXT:
            return ext
        # webp 不在支持列表，统一按 jpg 处理（后续会被 _ensure_jpg 转成 JPEG）
        ct = (content_type or "").lower()
        if "webp" in ct or ext == ".webp":
            return ".jpg"
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        if "png" in ct:
            return ".png"
        if "gif" in ct:
            return ".gif"
        return ".jpg"

    @staticmethod
    def _ensure_jpg(path: Path) -> Path | None:
        """将图片转换为 JPEG。如果转换失败（如缺少 webp 解码器），返回 None。"""
        try:
            from PIL import Image

            jpg_path = path.with_suffix(".jpg")
            # 无论扩展名是什么，都用 PIL 打开并重新保存为 JPEG，避免扩展名欺骗。
            with Image.open(path) as img:
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
                img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                img.save(jpg_path, "JPEG", quality=92)
            if jpg_path.exists() and jpg_path.stat().st_size > 0:
                # 删除原始文件（如果不同）
                if jpg_path != path:
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                return jpg_path
        except Exception as exc:
            logger.warning(f"PIL 转换图片失败 {path.name}: {exc}")
        # 兜底：删除原文件并返回 None
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


    def _is_image_url(self, url: str) -> bool:
        """过滤 Bing 自身的 UI 图标/像素追踪等非内容图片。"""
        if not url:
            return False
        url_lower = url.lower()
        # 检查是否来自 Bing UI 资源域名
        if any(host in url_lower for host in self._BING_BLOCK_HOSTS):
            return False
        return True

    @staticmethod
    def _clean_url(url: str) -> str | None:
        """清洗 URL：解码 HTML 实体、去除转义、验证格式。"""
        url = url.strip()
        url = url.replace("\\/", "/")
        # 解码常见 HTML 实体
        url = url.replace("&amp;", "&")
        url = url.replace("&quot;", "\"")
        url = url.replace("&#39;", "'")
        url = url.replace("&lt;", "<")
        url = url.replace("&gt;", ">")
        if not url.startswith("http"):
            return None
        if len(url) > 2048:
            return None
        return url

    # ------------------------------------------------------------------
    # 引擎选择
    # ------------------------------------------------------------------

    def _engine_order(self) -> list[str]:
        """返回引擎尝试顺序。国内服务器优先大作/百度。

        - 有代理时：Google → DuckDuckGo → Bing → Yandex → Baidu → 大作
        - 无代理时（国内服务器）：大作 → 百度 → Bing → Yandex → DuckDuckGo → Google
          避免 Google/DuckDuckGo 在无代理时超时 15s 浪费时间。
        """
        if self.proxy:
            return ["google", "duckduckgo", "bing", "yandex", "baidu", "bigbigwork"]
        # 国内无代理：优先百度/Bing 实拍图；大作放最后作补充（易返回设计/时尚类无关图）
        return ["baidu", "bing", "yandex", "duckduckgo", "google", "bigbigwork"]

    # ------------------------------------------------------------------
    # 水印 / 图库检测
    # ------------------------------------------------------------------

    def _clean_search_query(self, query: str) -> str:
        """清理搜索词：追加排除关键词，过滤图纸/示意图/3D渲染/水印广告等非实拍内容。

        搜索引擎大多支持 -keyword 语法排除，在词尾追加后显著提升实拍命中率。
        返回的 query 会保持可读性，不会重复追加。
        """
        q = query.strip()
        ql = q.lower()
        # 避免重复追加
        if any(x in ql for x in ("-diagram", "-blueprint", "-illustration", "-render")):
            return q
        # 追加排除关键词（取第一个排除组合，避免 query 过长）
        exclude_kw = random.choice(_DIAGRAM_EXCLUDE_KEYWORDS)
        return f"{q} {exclude_kw}"

    def _is_stock_domain(self, url: str) -> bool:
        """检查 URL 是否来自已知图库/水印站点。电商产品图允许作为参考图。"""
        url_lower = url.lower()
        for domain in _STOCK_WATERMARK_DOMAINS:
            if domain in url_lower:
                return True
        return False

    def _is_automotive_query(self, query: str, scene_type: str = "") -> bool:
        if scene_type in _SCENE_TYPES:
            return True
        ql = (query or "").lower()
        return any(h in ql for h in _AUTOMOTIVE_QUERY_HINTS)

    def _passes_fast_image_check(self, img_path: Path, scene_type: str) -> bool:
        try:
            from PIL import Image

            with Image.open(img_path) as img:
                w, h = img.size
                if w < 220 or h < 220:
                    return False
                if scene_type == "vehicle_exterior" and h > w * 1.25:
                    return False
        except Exception:
            return False
        return True

    def _url_has_irrelevant_keyword(self, url_lower: str, kw: str) -> bool:
        """短关键词用边界匹配，避免 cat 误伤 catalog 等。"""
        if len(kw) <= 4:
            return re.search(rf"(?:^|[/_\-.]){re.escape(kw)}(?:$|[/_\-.])", url_lower) is not None
        return kw in url_lower

    def _is_relevant_scene_url(self, url: str, query: str, scene_type: str = "") -> bool:
        """根据 query / scene_type 过滤明显无关的场景图 URL。"""
        q = query.lower()
        url_lower = url.lower()

        if self._is_automotive_query(query, scene_type):
            for kw in _IRRELEVANT_URL_KEYWORDS:
                if self._url_has_irrelevant_keyword(url_lower, kw):
                    logger.debug(f"过滤无关场景({kw}): {url[:60]}")
                    return False

        if scene_type == "vehicle_exterior":
            for kw in _GENERIC_SCENE_BLOCK_KEYWORDS:
                if kw in url_lower:
                    logger.debug(f"过滤 vehicle 无关场景({kw}): {url[:60]}")
                    return False
            return True

        # PWC / personal watercraft 相关查询：排除沙滩、码头、租赁、展厅
        if any(k in q for k in ("sea-doo", "seadoo", "waverunner", "wave runner", "jet ski", "pwc")):
            for kw in _PWC_SCENE_BLOCK_KEYWORDS:
                if kw in url_lower:
                    logger.debug(f"过滤 PWC 无关场景({kw}): {url[:60]}")
                    return False
            return True

        # 安装/细节/车间：排除整车外观、风景、评测新闻图等
        if scene_type in ("installation", "product_detail", "workshop") or any(
            k in q for k in ("engine bay", "engine compartment", "install", "mechanic", "workshop", "garage")
        ):
            for kw in _AUTOMOTIVE_SCENE_BLOCK_KEYWORDS:
                if kw in url_lower:
                    logger.debug(f"过滤 automotive 无关场景({kw}): {url[:60]}")
                    return False
            return True

        if any(k in q for k in ("engine bay", "engine compartment", "car", "automotive", "suv", "truck", "sedan")):
            for kw in _AUTOMOTIVE_SCENE_BLOCK_KEYWORDS:
                if kw in url_lower:
                    logger.debug(f"过滤 automotive 无关场景({kw}): {url[:60]}")
                    return False
            return True

        for kw in _GENERIC_SCENE_BLOCK_KEYWORDS:
            if kw in url_lower:
                logger.debug(f"过滤通用无关场景({kw}): {url[:60]}")
                return False
        return True


    def _is_ecommerce_domain(self, url: str) -> bool:
        """判断 URL 是否来自电商站点（仅用于日志/来源标记，不拦截）。"""
        url_lower = url.lower()
        return any(d in url_lower for d in _ECOMMERCE_DOMAINS)

    def _has_watermark(self, img_path: Path) -> bool:
        """检测图片是否可能含有水印（参考图阈值宽松）。

        参考图用于设计师构图参考，非最终输出，检测阈值比成品图宽松很多。
        仅过滤明显的：极小图（<80px）、极端变形（>7:1）、边缘文字水印、
        大面积重复纹理水印（如 Vecteezy 全屏平铺水印）。
        """
        try:
            from PIL import Image
        except ImportError:
            return False

        try:
            img = Image.open(img_path)
            w, h = img.size
        except Exception:
            return False

        # 规则 1：极小图片（<80px）大概率是图标/缩略图
        if w < 80 or h < 80:
            return True

        # 规则 2：宽高比极端异常（>7:1 通常是 UI 横幅而非水印图）
        ratio = max(w, h) / max(min(w, h), 1)
        if ratio > 7.0:
            return True

        # 规则 3：边缘/右下角文字水印检测
        try:
            if self._has_edge_text(img, w, h):
                return True
        except Exception:
            pass

        # 规则 4：灰度分块方差分析（阈值放宽，避免误杀有效参考图）
        try:
            gray = img.convert("L")
            pixels = list(gray.getdata())
            block_size = max(w, h) // 5
            if block_size < 15:
                return False
            block_stds: list[float] = []
            for y in range(0, h, block_size):
                for x in range(0, w, block_size):
                    block = []
                    for dy in range(min(block_size, h - y)):
                        row_start = (y + dy) * w + x
                        row_end = row_start + min(block_size, w - x)
                        block.extend(pixels[row_start:row_end])
                    if len(block) > 80:
                        block_stds.append(statistics.stdev(block) if len(set(block)) > 1 else 0.0)

            if block_stds:
                avg_std = sum(block_stds) / len(block_stds)
                max_std = max(block_stds)
                # 整体非常干净但局部纹理极高 → 明显水印覆盖
                if avg_std < 8 and max_std > 65:
                    return True
                # 局部纹理极端高 → 大型水印/logo
                if avg_std > 1 and max_std > avg_std * 5.0 and max_std > 70:
                    return True
        except Exception:
            pass

        # 规则 5：检测全图平铺型重复水印（如 Vecteezy）。
        # 思路：将图片分成 3×3 网格，计算每个网格与全图平均纹理的偏离。
        # 如果大量网格呈现相近的“中等纹理”（水印文字重复出现），则视为水印。
        try:
            gray = img.convert("L")
            pixels = list(gray.getdata())
            rows, cols = 4, 4
            cell_h, cell_w = max(h // rows, 1), max(w // cols, 1)
            cell_stds: list[float] = []
            for r in range(rows):
                for c in range(cols):
                    y0, x0 = r * cell_h, c * cell_w
                    y1, x1 = min(y0 + cell_h, h), min(x0 + cell_w, w)
                    block = []
                    for y in range(y0, y1):
                        row_start = y * w + x0
                        block.extend(pixels[row_start:row_start + (x1 - x0)])
                    if len(block) > 100:
                        cell_stds.append(statistics.stdev(block) if len(set(block)) > 1 else 0.0)
            if len(cell_stds) >= 12:
                avg_cell = sum(cell_stds) / len(cell_stds)
                min_cell = min(cell_stds)
                max_cell = max(cell_stds)
                # 平铺水印：各块纹理接近且整体处于中等水平，差异不大
                if 8 < avg_cell < 45 and (max_cell - min_cell) < avg_cell * 0.6:
                    return True
        except Exception:
            pass

        return False

    @staticmethod
    def _is_likely_diagram(img_path: Path) -> bool:
        """检测图片是否为线稿/示意图/技术图纸/蓝屏/纯色占位图。

        策略（分层递进）：
        1. 颜色极少的线稿/灰度图（< 30 色）→ 图纸
        2. 像素极端黑白两极分布，缺少中间调 → 线稿
        3. 大面积白底/灰底（> 70%）配合少量深色线条 → 工程图纸
        4. 白底占比 > 85% 且边缘像素密度极低 → 占位图/图标
        """
        try:
            from PIL import Image
            img = Image.open(img_path)
            w, h = img.size
            if w < 50 or h < 50:
                return False

            # ── 策略 1: 颜色极少 → 线稿/示意图 ──
            rgb_img = img.convert("RGB")
            colors = rgb_img.getcolors(maxcolors=256)
            if colors and len(colors) < 30:
                return True

            # ── 策略 2 & 3 & 4: 灰度分析 ──
            gray = img.convert("L")
            pixels = list(gray.getdata())
            if not pixels:
                return False
            total = len(pixels)

            # 2a: 黑白极端分布（> 90% 在极暗(<35) 或极亮(>220)，中间调 < 8%）
            dark = sum(1 for p in pixels if p < 35)
            light = sum(1 for p in pixels if p > 220)
            mid = total - dark - light
            if (dark + light) / total > 0.90 and mid / total < 0.08:
                return True

            # 2b: 灰度图像素种类极少
            unique_gray = len(set(pixels))
            if unique_gray < 60:
                return True

            # 3: 白底+深色线条 → 工程图纸特征
            white_px = sum(1 for p in pixels if p > 245)
            white_ratio = white_px / total
            dark_px = sum(1 for p in pixels if p < 60)
            dark_ratio = dark_px / total
            # 大面积白底 (> 70%) + 少量深色线条 (< 20%) + 几乎无中间调
            mid_color = sum(1 for p in pixels if 100 < p < 200)
            mid_ratio = mid_color / total
            if white_ratio > 0.70 and dark_ratio < 0.20 and mid_ratio < 0.15:
                return True

            # 4: 极简占位图/图标 → 白底 > 85% 且深色像素密度低
            if white_ratio > 0.85 and dark_ratio < 0.08:
                return True

            # ── 策略 5: 边缘直线密度检测 ──
            # 图纸类有大量水平/垂直线条，通过分析像素行/列的方差来识别
            try:
                # 每隔 4px 采样一行，计算行内像素方差
                line_variances: list[float] = []
                for y in range(0, h, 4):
                    row = pixels[y * w:(y + 1) * w]
                    if len(row) > 10:
                        line_variances.append(
                            statistics.stdev(row) if len(set(row)) > 1 else 0.0
                        )
                if line_variances:
                    # 大量低方差行（均匀背景）+ 少量极高方差行（线条）
                    low_var = sum(1 for v in line_variances if v < 10)
                    high_var = sum(1 for v in line_variances if v > 80)
                    # 大部分是均匀背景，但有明显的线条存在
                    if low_var > len(line_variances) * 0.6 and high_var < len(line_variances) * 0.12:
                        return True
            except Exception:
                pass

            # ── 策略 6: OCR 文字密度检测 ──
            # 图中含大量结构文字 → 说明书/工程图纸/示意图
            try:
                full_text = _ocr_count_text_full(img, w, h)
                if full_text > 25:
                    return True
                # 白底+较多文字 → 工程图纸
                if white_ratio > 0.6 and full_text > 10:
                    return True
            except Exception:
                pass

        except Exception:
            pass
        return False

    @staticmethod
    def _has_edge_text(img, img_w: int, img_h: int) -> bool:
        """检测图片底边/右下角是否有疑似水印文字的纹理。

        水印文字的特征：位于图片边缘区域（底部 20% 或右侧 30%）、
        区域内的像素亮度标准差显著高于该区域周围的背景。
        新增 OCR 辅助检测：如果 tesseract 可用，直接识别边缘区域文字。
        """
        try:
            gray = img.convert("L")
            pixels = list(gray.getdata())

            # ── OCR 水印检测（优先）──
            text_count = _ocr_count_text_in_edges(img, img_w, img_h)
            if text_count > 3:
                return True

            # 底部 25% 区域
            bottom_start = int(img_h * 0.75)
            bottom_strip = []
            for y in range(bottom_start, img_h):
                row_start = y * img_w
                bottom_strip.extend(pixels[row_start:row_start + img_w])

            if len(bottom_strip) > 400:
                b_std = statistics.stdev(bottom_strip) if len(set(bottom_strip)) > 1 else 0.0
                # 底部总体干净但标准差偏高 → 可能有文字
                if b_std > 50:
                    return True

            # 右下角 20%×25% 区域（最常见的水印位置）
            corner_x = int(img_w * 0.75)
            corner_y = int(img_h * 0.75)
            corner_block = []
            for y in range(corner_y, img_h):
                row_start = y * img_w + corner_x
                corner_block.extend(pixels[row_start:row_start + (img_w - corner_x)])

            if len(corner_block) > 200:
                # 右下角 vs 左下角的纹理对比：如果右下显著高于左下，大概率是水印文字
                left_corner = []
                for y in range(corner_y, img_h):
                    row_start = y * img_w
                    left_corner.extend(pixels[row_start:row_start + (img_w - corner_x)])

                if len(left_corner) > 200:
                    right_std = statistics.stdev(corner_block) if len(set(corner_block)) > 1 else 0.0
                    left_std = statistics.stdev(left_corner) if len(set(left_corner)) > 1 else 0.0
                    # 右下角纹理显著高于左下角 → 水印文字（放宽阈值）
                    if right_std > 40 and right_std > left_std * 1.5:
                        return True

            return False
        except Exception:
            return False

    @staticmethod
    def _has_watermark_ocr(img_path: Path) -> bool:
        """OCR 文字检测：边缘/角落有文字 → 水印图；整图大量文字 → 说明书/广告。"""
        try:
            from PIL import Image
            img = Image.open(img_path)
            w, h = img.size
            if w < 80 or h < 80:
                return False
            # 检测边缘文字数 + 全图文字密度
            edge_count = _ocr_count_text_in_edges(img, w, h)
            full_count = _ocr_count_text_full(img, w, h)
            # 边缘有文字 → 水印
            if edge_count > 3:
                return True
            # 全图文字密集（> 30 字符）→ 说明书/广告/图纸
            if full_count > 30:
                return True
            return False
        except Exception:
            return False

    async def close(self) -> None:
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None
