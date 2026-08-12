from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from backend.image_sop.config import Settings
from backend.image_sop.models import CopyBlock, ImageRequirement, ListingData, ProductAnalysis

logger = logging.getLogger(__name__)

_AI_SEMAPHORES: dict[tuple[int, str, int], asyncio.Semaphore] = {}


def _ai_semaphore(kind: str, limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = (id(loop), kind, max(1, limit))
    semaphore = _AI_SEMAPHORES.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(key[2])
        _AI_SEMAPHORES[key] = semaphore
    return semaphore


IMAGE_THEMES = [
    ("主图", "纯白背景主图，仅展示产品本体，禁止任何文字、徽章或促销元素。"),
    ("核心功能", "突出产品核心功能与用户收益，采用强视觉层级与对比构图。"),
    ("安装指南", "分步骤展示安装流程，标注工具、注意事项与关键节点。"),
    ("适配与OE号", "结合车型/应用场景，突出 OE 号与兼容性信息。"),
    ("品质细节", "材质、结构、工艺特写，强调耐用性与做工。"),
    ("巡检与故障症状", "展示如何检查产品异常及常见损坏/失效症状。"),
    ("维护与延长寿命", "日常使用和保养建议，帮助延长产品使用寿命。"),
]

PREMIUM_IMAGE_THEMES = [
    ("车型适配+OE", "VEHICLE FITMENT & OE NUMBERS：展示适配车型年份+OE号信息，兼容性列表。"),
    ("产品特点", "PRODUCT FEATURES：从listing数据中提炼的产品核心卖点与关键特性。"),
    ("产品介绍", "PRODUCT INTRODUCTION：AI根据产品信息分析提炼的4点产品介绍。"),
    ("产品耐用性/可靠性", "PRODUCT DURABILITY & RELIABILITY：材质工艺与测试数据，质量认证与耐用性。"),
    ("使用与安装方法", "USAGE & INSTALLATION：产品的正确使用方式和安装步骤说明。"),
    ("品牌保障", "BRAND TRUST：品牌承诺(WHY CHOOSE US) + 维护保养/延长使用寿命。"),
]

COMPAT_PATTERNS = (
    r"compatible\s+with",
    r"compatibility",
    r"fits?\s+for",
    r"fit\s+for",
    r"application",
    r"for\s+[A-Za-z0-9][A-Za-z0-9\s\-./]{2,}",
)
QUALITY_PATTERNS = (
    r"reliable",
    r"quality",
    r"durable",
    r"brand\s+new",
    r"direct[- ]fit",
    r"tested",
    r"premium",
    r"oem",
    r"heavy[- ]duty",
    r"precision",
)

# 特定品类：图片需求构思须强调的重点展示部位
CATEGORY_DISPLAY_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "headlight", "tail light", "taillight", "fog light", "turn signal",
            "marker light", "drl", "daytime running", "bulb", " lamp", "light assembly",
            "大灯", "尾灯", "雾灯", "转向灯", "灯类",
        ),
        "灯类：须重点展示插头针数/连接器针脚数量，针脚排列清晰可辨。",
    ),
    (
        (
            "window regulator", "power window regulator", "glass regulator",
            "玻璃升降", "升降器",
        ),
        "玻璃升降器：须重点展示是否带马达，明确标注「带马达」或「不带马达」。",
    ),
    (
        (
            "starter motor", "wiper motor", "blower motor", "fan motor",
            "actuator motor", "stepper motor", "servo motor",
            "马达", "电机", "motor assembly", "actuator",
        ),
        "电机类：须重点展示是否带马达，明确标注「带马达」或「不带马达」。",
    ),
    (
        (
            "mass air flow", "maf sensor", "air flow meter", "airflow sensor",
            "空气流量", "流量计",
        ),
        "空气流量计：须重点展示插头针数/连接器针脚数量。",
    ),
    (
        (
            "tailgate strut", "lift support", "gas strut", "trunk strut",
            "power liftgate", "尾门撑杆", "撑杆",
        ),
        "尾门撑杆：须标注左右侧（Left/Right 或 Driver/Passenger Side）。",
    ),
    (
        (
            "door handle", "exterior handle", "interior handle", "门把手",
        ),
        "门把手：须标注左右侧（Left/Right 或 Driver/Passenger Side）。",
    ),
    (
        (
            "nox sensor", "nitrogen oxide", "氮氧", "nox ",
        ),
        "氮氧传感器：须重点展示插头针数/连接器针脚数量。",
    ),
    (
        (
            "egr valve", "exhaust gas recirculation", "废气再循环", " egr ",
        ),
        "废气再循环阀：须重点展示插头针数/连接器针脚数量。",
    ),
]

# ── Amazon 合规禁用词 ──
# A. 涉及移除/消除/删除/妨碍/规避/更改原装设置 → 禁止
# B. 涉及排放/废气/气体/液体/燃油 → 谨慎(尽量不出现)
# C. 所有品类通用禁用词
_AMAZON_COMPLIANCE_BANNED = frozenset({
    # A. 修改/移除/规避类（汽配重点）
    "delete", "deleted", "deleting", "deletion",
    "remove", "removed", "removing", "removal",
    "bypass", "bypassed", "bypassing",
    "interfere", "interferes", "interfering",
    "circumvent", "circumvents", "circumventing",
    "override", "overrides", "overriding",
    "eliminate", "eliminates", "eliminating", "elimination",
    "disable", "disabled", "disabling",
    "modify", "modified", "modifying", "modification",
    "alter", "altered", "altering", "alteration",
    "tamper", "tampered", "tampering",
    "defeat", "defeated", "defeating",
    "change", "changed", "changing",
    # B. 排放/气体/燃油类（美国空气法）
    "emission", "emissions",
    "exhaust",
    "fuel",
    # C. 所有品类通用禁用词
    "100%", "disinfect", "sterilization", "sterilize",
    "bacteria", "fungus", "fungi",
    "laser",
    "eco-friendly", "eco friendly",
    "insect repellent", "insect-repellent",
    "anti-mites", "anti mites", "antimites",
    "repel insects",
    "non-toxic", "non toxic", "nontoxic",
    "all natural", "all-natural",
    "environment friendly", "environment-friendly",
    "chemical",
    "best", "number 1", "#1", "number one",
    # D. Amazon A+ / 社区准则常见禁用词（保证/承诺类）
    "assurance", "assurances",
    "guarantee", "guaranteed", "guarantees",
    "warranty", "warranties",
})

# 排放/气体相关的"软禁用"模式 — 如果文案中出现则发出警告，但不会自动过滤
# 因为某些品类（如排气歧管、燃油泵）的核心关键词绕不开这些词
_AMAZON_COMPLIANCE_EMISSION_SOFT = frozenset({
    "emission", "emissions", "exhaust", "fuel", "gas", "gasoline",
    "diesel", "vapor", "vapour", "fume", "fumes", "EGR", "DPF", "CAT",
    "catalytic converter", "O2 sensor", "oxygen sensor",
})

# ── eBay 合规禁用词（图片文案 / listing 政策，非 Amazon 汽配规则）──
_EBAY_COMPLIANCE_BANNED = frozenset({
    # 绝对化 / 排名 / 价格宣称
    "best", "best seller", "best selling", "number 1", "#1", "number one", "no. 1", "no 1",
    "lowest price", "cheapest", "unbeatable", "miracle",
    "100%",
    "guaranteed", "guarantee", "guarantees",
    "risk free", "risk-free",
    "top rated seller", "top-rated seller", "#1 seller",
    # 健康 / 环保 / 杀菌类
    "disinfect", "disinfection", "sterilization", "sterilize",
    "bacteria", "bacterial", "fungus", "fungal", "fungi",
    "laser",
    "eco-friendly", "eco friendly",
    "insect repellent", "insect-repellent",
    "anti-mites", "anti mites", "anti-mite", "anti mite",
    "repel insects",
    "non-toxic", "non toxic", "nontoxic",
    "all natural", "all-natural",
    "environment friendly", "environment-friendly", "environmentally friendly",
    "chemical",
    "fda approved", "100% safe",
    "cure",
    # 配送 / 平台误导
    "free shipping",
    "ebay guaranteed", "authenticity guarantee",
    # 仿品 / 误导性真品宣称
    "counterfeit", "knockoff", "replica",
})


def _compliance_platform_key(listing: "ListingData | None") -> str:
    if listing and "ebay" in (listing.data_source or "").lower():
        return "ebay"
    return "amazon"


def _compliance_banned_set(platform: str) -> frozenset[str]:
    return _EBAY_COMPLIANCE_BANNED if platform == "ebay" else _AMAZON_COMPLIANCE_BANNED


def _compliance_banned_words_prompt(platform: str, *, limit: int = 24) -> str:
    words = sorted(_compliance_banned_set(platform), key=len)
    if len(words) <= limit:
        return ", ".join(words)
    return ", ".join(words[:limit]) + ", etc."


def _build_compliance_system_prompt(is_ebay: bool) -> str:
    if is_ebay:
        banned = _compliance_banned_words_prompt("ebay")
        return (
            "*** CRITICAL EBAY LISTING COMPLIANCE RULES (VIOLATIONS = LISTING REMOVAL) ***\n"
            "1. DO NOT use absolute/superlative or comparative price claims "
            "(best, #1, lowest price, cheapest, 100%, guaranteed, top-rated seller, etc.).\n"
            "2. DO NOT use unsubstantiated health, safety, or eco claims "
            "(disinfect, sterilization, bacteria, eco-friendly, non-toxic, FDA approved, etc.).\n"
            "3. DO NOT use counterfeit/authenticity misuse "
            "(counterfeit, replica, knockoff, unauthorized authenticity guarantee).\n"
            "4. DO NOT mention free shipping, off-eBay contact, or eBay platform guarantee programs "
            "in on-image product copy.\n"
            "5. This is eBay, NOT Amazon. Standard install/replace language is OK. "
            "Do NOT apply Amazon-only automotive bans on remove/delete/bypass/emission/exhaust/fuel "
            "unless the source listing already avoids those terms.\n"
            f"6. NEVER use eBay-banned words in any output: {banned}.\n"
            "7. Never use absolute/superlative marketing claims.\n"
        )
    banned = _compliance_banned_words_prompt("amazon")
    return (
        "*** CRITICAL AMAZON COMPLIANCE RULES (VIOLATIONS = LISTING REMOVAL) ***\n"
        "1. DO NOT use any language about removing, deleting, eliminating, bypassing, "
        "circumventing, disabling, overriding, tampering with, defeating, modifying, or altering "
        "factory/original vehicle equipment, settings, systems, or software. "
        "This product is a direct replacement part — describe it as a replacement/swap/substitute, "
        "never as a modification or delete device.\n"
        "2. DO NOT use emission, exhaust, gas, fuel, vapor, or fume-related language unless the product "
        "itself IS an emission/exhaust/fuel component AND the listing already uses those terms. "
        "If unavoidable, use minimal neutral language.\n"
        f"3. NEVER use Amazon-banned words in any output: {banned}.\n"
        "4. Never use absolute/superlative claims (best, #1, guaranteed, 100%, assurance, warranty, etc.).\n"
    )


def _build_compliance_user_prompt(is_ebay: bool) -> str:
    if is_ebay:
        return (
            "*** EBAY COMPLIANCE RULES — YOUR OUTPUT WILL BE REJECTED IF VIOLATED ***\n"
            "A. ABSOLUTE / SUPERLATIVE / PRICING CLAIMS — ABSOLUTELY FORBIDDEN:\n"
            "  eBay prohibits best, #1, number 1, lowest price, cheapest, 100%, guaranteed, "
            "risk-free, top-rated seller, miracle, cure, etc.\n"
            "B. HEALTH / ECO / UNSUBSTANTIATED CLAIMS — FORBIDDEN:\n"
            "  disinfect, sterilization, bacteria, fungus, eco-friendly, non-toxic, all natural, "
            "FDA approved, laser, chemical, insect repellent, anti-mites, repel insects, etc.\n"
            "C. MISLEADING AUTHENTICITY / COUNTERFEIT LANGUAGE — FORBIDDEN:\n"
            "  counterfeit, replica, knockoff, unauthorized authenticity guarantee.\n"
            "D. POLICY / OFF-PLATFORM — FORBIDDEN in on-image product copy:\n"
            "  free shipping, eBay guaranteed, WhatsApp/WeChat/email for off-platform contact.\n"
            "E. PLATFORM NOTE — this is eBay image SOP, NOT Amazon:\n"
            "  Standard replacement-part language (remove old part, replace, install, exhaust/fuel specs "
            "from listing) is allowed when present in the source listing.\n"
            "  Do NOT apply Amazon US Clean Air Act / CARB-style bans unless the listing already avoids those words.\n\n"
        )
    return (
        "*** AMAZON COMPLIANCE RULES — YOUR OUTPUT WILL BE REJECTED IF VIOLATED ***\n"
        "A. REMOVAL / MODIFICATION / TAMPERING — ABSOLUTELY FORBIDDEN:\n"
        "  Amazon prohibits any description that suggests removing, deleting, eliminating, bypassing,\n"
        "  circumventing, disabling, overriding, modifying, or altering factory vehicle equipment,\n"
        "  settings, systems, emissions devices, or software. This product is a STANDARD REPLACEMENT\n"
        "  part — it replaces a worn/failed OE part, it does NOT modify, delete, or bypass anything.\n"
        "  • INSTALLATION section: describe as bolt-on replacement / direct swap / plug-and-play\n"
        "    replacement. Use words like 'replace', 'swap', 'install', 'mount', 'fit'. NEVER say\n"
        "    'remove the old one' — say 'replace the worn part' or 'swap out the original'.\n"
        "  • COMPATIBILITY section: ONLY list vehicle makes/models/years the part fits. Never imply\n"
        "    the part changes the vehicle's behavior or defeats any system.\n"
        "  • BANNED words (hard filter): delete, remove, removal, bypass, interfere, circumvent,\n"
        "    override, eliminate, disable, modify, alter, tamper, defeat, change.\n"
        "B. EMISSION / EXHAUST / FUEL / GAS — RESTRICTED (US Clean Air Act):\n"
        "  Some US states (e.g. California CARB) strictly regulate emission-related claims.\n"
        "  • AVOID mentioning: emission, exhaust gas, fuel economy change, vapor, fumes, EGR, DPF,\n"
        "    catalytic converter performance, O2 sensor behavior, or any change to emissions output.\n"
        "  • If the product IS an exhaust manifold, fuel pump, or emission sensor AND the listing\n"
        "    already uses these terms, you may use minimal neutral language. Otherwise, omit entirely.\n"
        "  • Check competitor listings: if other sellers avoid these words, you must also avoid them.\n"
        "C. ALL CATEGORY BANNED WORDS — NEVER USE (OR YOUR OUTPUT WILL BE REJECTED):\n"
        "  These words trigger automatic Amazon listing suppression:\n"
        "  100%, disinfect, sterilization, bacteria, fungus, laser, eco-friendly, insect repellent,\n"
        "  anti-mites, repel insects, non-toxic, all natural, environment friendly, chemical.\n"
        "  • CRITICAL — '100%' IS THE MOST COMMON VIOLATION. Instead use:\n"
        "    - 'All-new components' or 'Brand-new components' (NOT '100% new')\n"
        "    - 'Rigorously tested' or 'Fully tested' (NOT '100% tested')\n"
        "    - 'Complete' or 'Full' (NOT '100% satisfaction/coverage')\n"
        "D. NO ABSOLUTE / SUPERLATIVE CLAIMS:\n"
        "  best, number 1, #1, guaranteed, perfect, 100% satisfaction, top-rated, assurance, warranty, etc.\n"
        "E. INSTALLATION LANGUAGE — DO NOT mention modifying or altering anything:\n"
        "  • Use: 'Direct bolt-on replacement', 'Plug-and-play fitment', 'Straightforward installation'\n"
        "  • NEVER use: 'no modifications needed', 'easy to modify', 'simply delete the old', etc.\n\n"
    )


class AiService:
    _CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._fitment_oe_translation_cache: dict[str, tuple[str, str]] = {}
        self._current_fitment_oe_copy: str | None = None
        self._current_fitment_compat: str = ""
        self._current_fitment_oe: str = ""

    async def _post_ai_json(
        self,
        label: str,
        body: dict[str, Any],
        *,
        timeout: int,
        premium: bool = False,
    ) -> dict[str, Any]:
        """限流调用 AI，并记录排队、首包、总耗时与重试次数。"""
        limit = (
            self.settings.ai_premium_max_concurrent
            if premium
            else self.settings.ai_standard_max_concurrent
        )
        semaphore = _ai_semaphore("premium" if premium else "standard", limit)
        total_semaphore = _ai_semaphore(
            "total",
            self.settings.ai_total_max_concurrent,
        )
        queued_at = time.perf_counter()
        async with total_semaphore, semaphore:
            started_at = time.perf_counter()
            queue_ms = (started_at - queued_at) * 1000
            retries = max(0, int(self.settings.ai_request_retries))
            url = f"{self.settings.active_ai_api_base}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.settings.active_ai_api_key}",
                "Content-Type": "application/json",
            }
            for attempt in range(retries + 1):
                request_started = time.perf_counter()
                first_byte_ms = 0.0
                try:
                    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                        async with client.stream(
                            "POST",
                            url,
                            headers=headers,
                            json=body,
                        ) as response:
                            first_byte_ms = (time.perf_counter() - request_started) * 1000
                            response.raise_for_status()
                            raw = await response.aread()
                    total_ms = (time.perf_counter() - request_started) * 1000
                    result = json.loads(raw)
                    logger.info(
                        "[AI-TIMING] label=%s queue_ms=%.0f first_byte_ms=%.0f "
                        "total_ms=%.0f retries=%d",
                        label,
                        queue_ms,
                        first_byte_ms,
                        total_ms,
                        attempt,
                    )
                    return result
                except (httpx.HTTPError, json.JSONDecodeError) as exc:
                    retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                        exc.response.status_code == 429
                        or exc.response.status_code >= 500
                    )
                    if attempt >= retries or not retryable:
                        total_ms = (time.perf_counter() - request_started) * 1000
                        logger.warning(
                            "[AI-TIMING] label=%s failed queue_ms=%.0f "
                            "first_byte_ms=%.0f total_ms=%.0f retries=%d error=%s",
                            label,
                            queue_ms,
                            first_byte_ms,
                            total_ms,
                            attempt,
                            exc,
                        )
                        raise
                    wait_seconds = min(4.0, 0.75 * (2 ** attempt))
                    logger.warning(
                        "[AI-RETRY] label=%s attempt=%d wait=%.2fs error=%s",
                        label,
                        attempt + 1,
                        wait_seconds,
                        exc,
                    )
                    await asyncio.sleep(wait_seconds)
        raise RuntimeError("AI 请求未返回结果")

    async def generate_copy_and_requirements(
        self,
        listing: ListingData,
        main_image: str,
        detail_reference_urls: list[str] | None = None,
        scene_reference_urls: list[str] | None = None,
        image_count: int | None = None,
        has_operator_references: bool = False,
        sku: str = "",
        main_image_path: Path | None = None,
        product_info: dict[str, Any] | None = None,
        scene_link_sources: list[bool] | None = None,
        # 保留旧参数兼容
        reference_images: list[str] | None = None,
    ) -> tuple[ProductAnalysis, CopyBlock, list[ImageRequirement], dict[str, Path]]:
        count = image_count or self.settings.sop_image_count
        # 兼容旧调用：如果只有 reference_images，拆分为 detail + scene
        if reference_images and not detail_reference_urls and not scene_reference_urls:
            detail_reference_urls = list(reference_images)
            scene_reference_urls = []
        detail_refs = detail_reference_urls or []
        scene_refs = scene_reference_urls or []
        link_flags = scene_link_sources or []
        sku_val = sku or listing.sku

        raw_compat = self._resolve_listing_compatibility_text(listing)
        raw_oe = self._resolve_listing_oe_text(listing)
        needs_translation = self._text_needs_english_translation(raw_compat, raw_oe)
        compat, oe, fitment_oe_copy = await self._resolve_translated_fitment_oe(listing)
        self._current_fitment_oe_copy = fitment_oe_copy
        self._current_fitment_compat = compat
        self._current_fitment_oe = oe
        if needs_translation:
            logger.info(
                "[FITMENT-OE] sku=%s listing fitment/OE translated to English",
                sku_val,
            )

        if self.settings.active_ai_api_key:
            try:
                payload = await self._call_ai_model(
                    listing, main_image, detail_refs, scene_refs, count, has_operator_references,
                    product_info=product_info,
                    scene_link_sources=link_flags,
                )
                generated_product_info = self._normalize_product_info(
                    payload.get("product_profile"),
                    listing,
                )
                if not product_info:
                    product_info = generated_product_info
                elif generated_product_info.get("product_name"):
                    product_info = generated_product_info
                analysis, copy, requirements = self._parse_payload(
                    payload, listing, main_image, detail_refs, scene_refs, count
                )
                self._enrich_analysis_with_product_info(analysis, product_info or {})
                self._apply_fitment_oe_to_analysis(analysis)
                self._apply_canonical_fitment_oe_cards(
                    requirements, listing, analysis, product_info, is_premium=False
                )
                # ── 合规检查：扫全量文案，记录违禁词 ──
                self._scan_compliance(analysis, copy, requirements, sku_val, listing)
                # ── 合规清洗：自动替换违禁词为安全表达 ──
                AiService.sanitize_compliance_output(analysis, copy, requirements, listing)
                self._finalize_listing_keywords(listing, copy)
                extra_files = await self._finalize_image_references(
                    requirements,
                    listing,
                    analysis,
                    main_image,
                    detail_refs,
                    scene_refs,
                    has_operator_references,
                    sku_val,
                    main_image_path,
                    scene_link_sources=link_flags,
                )
                return analysis, copy, requirements, extra_files
            except Exception:
                import traceback as _tb
                logger.warning(
                    f"AI 生成失败(降级本地模板) SKU={sku_val}:\n{_tb.format_exc()}"
                )
        analysis, copy, requirements = self._fallback_generate(listing, main_image, detail_refs, scene_refs, count)
        self._apply_fitment_oe_to_analysis(analysis)
        self._apply_canonical_fitment_oe_cards(
            requirements, listing, analysis, None, is_premium=False
        )
        # 降级路径也做合规清洗
        AiService.sanitize_compliance_output(analysis, copy, requirements, listing)
        self._finalize_listing_keywords(listing, copy)
        try:
            extra_files = await self._finalize_image_references(
                requirements,
                listing,
                analysis,
                main_image,
                detail_refs,
                scene_refs,
                has_operator_references,
                sku_val,
                main_image_path,
                scene_link_sources=link_flags,
            )
        except Exception:
            import traceback as _tb
            logger.warning(
                f"参考图处理失败(降级模式, 不影响主流程) SKU={sku_val}:\n"
                f"{_tb.format_exc()}"
            )
            extra_files = {}
        return analysis, copy, requirements, extra_files

    async def generate_premium_copy_and_requirements(
        self,
        listing: ListingData,
        main_image: str,
        detail_reference_urls: list[str] | None = None,
        scene_reference_urls: list[str] | None = None,
        has_operator_references: bool = False,
        sku: str = "",
        main_image_path: Path | None = None,
        # 普通模式的原始文案，用于保持核心信息一致
        standard_copy: CopyBlock | None = None,
        standard_analysis: ProductAnalysis | None = None,
        product_info: dict[str, Any] | None = None,
        scene_link_sources: list[bool] | None = None,
    ) -> tuple[ProductAnalysis, CopyBlock, list[ImageRequirement], dict[str, Path]]:
        """生成高级A+图SOP：文案顺序先车型/OE再产品特点，核心信息与普通模式保持一致。"""
        count = self.settings.sop_premium_image_count
        detail_refs = detail_reference_urls or []
        scene_refs = scene_reference_urls or []
        link_flags = scene_link_sources or []
        sku_val = sku or listing.sku

        compat, oe, fitment_oe_copy = await self._resolve_translated_fitment_oe(listing)
        self._current_fitment_oe_copy = fitment_oe_copy
        self._current_fitment_compat = compat
        self._current_fitment_oe = oe

        if self.settings.active_ai_api_key:
            try:
                if not product_info:
                    product_info = await self._analyze_product_deeply(listing, sku_val)
                    logger.info(
                        f"高级A+ 产品深度分析完成 SKU={sku_val}: "
                        f"name='{product_info.get('product_name','')[:60]}', "
                        f"category='{product_info.get('product_category','')}'"
                    )
                else:
                    logger.info(f"高级A+ 复用标准模式产品分析 SKU={sku_val}")

                payload = await self._call_ai_model_premium(
                    listing, main_image, detail_refs, scene_refs, count,
                    has_operator_references, product_info=product_info,
                    standard_copy=standard_copy, standard_analysis=standard_analysis,
                    scene_link_sources=link_flags,
                )
                analysis, copy, requirements = self._parse_payload(
                    payload, listing, main_image, detail_refs, scene_refs, count,
                    is_premium=True,
                )
                # 强制高级A+ 6个维度顺序：Card1=车型适配+OE
                requirements = self._normalize_premium_requirements(
                    requirements,
                    listing,
                    analysis,
                    standard_analysis=standard_analysis,
                    product_info=product_info,
                    fitment_oe_copy=fitment_oe_copy,
                )
                self._apply_fitment_oe_to_analysis(analysis)
                if standard_analysis:
                    self._apply_fitment_oe_to_analysis(standard_analysis)
                self._scan_compliance(analysis, copy, requirements, sku_val, listing)
                AiService.sanitize_compliance_output(analysis, copy, requirements, listing)
                self._enrich_analysis_with_product_info(analysis, product_info)
                self._finalize_listing_keywords(listing, copy)
                extra_files = await self._finalize_image_references(
                    requirements, listing, analysis, main_image,
                    detail_refs, scene_refs, has_operator_references,
                    sku_val, main_image_path, is_premium=True,
                    scene_link_sources=link_flags,
                )
                return analysis, copy, requirements, extra_files
            except Exception:
                import traceback as _tb
                logger.warning(
                    f"高级A+ AI 生成失败(降级本地模板) SKU={sku_val}:\n{_tb.format_exc()}"
                )
        analysis, copy, requirements = self._fallback_premium_generate(
            listing, main_image, detail_refs, scene_refs, count,
            standard_copy=standard_copy, standard_analysis=standard_analysis,
        )
        self._apply_fitment_oe_to_analysis(analysis)
        AiService.sanitize_compliance_output(analysis, copy, requirements, listing)
        self._finalize_listing_keywords(listing, copy)
        try:
            extra_files = await self._finalize_image_references(
                requirements, listing, analysis, main_image,
                detail_refs, scene_refs, has_operator_references,
                sku_val, main_image_path,
                scene_link_sources=link_flags,
            )
        except Exception:
            import traceback as _tb
            logger.warning(
                f"高级A+ 参考图处理失败(降级模式) SKU={sku_val}:\n{_tb.format_exc()}"
            )
            extra_files = {}
        return analysis, copy, requirements, extra_files

    async def _call_ai_model_premium(
        self,
        listing: ListingData,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        image_count: int,
        has_operator_references: bool = False,
        product_info: dict[str, Any] | None = None,
        standard_copy: CopyBlock | None = None,
        standard_analysis: ProductAnalysis | None = None,
        scene_link_sources: list[bool] | None = None,
    ) -> dict[str, Any]:
        """调用AI模型生成高级A+图的文案和图片需求。"""
        listing_context = self._build_listing_context(listing, product_info)
        detail_text = ", ".join(detail_references) if detail_references else "无"
        scene_text = ", ".join(scene_references) if scene_references else "无"
        has_refs = has_operator_references and (detail_references or scene_references)
        detail_count = len(detail_references) if detail_references else 0
        scene_count = len(scene_references) if scene_references else 0
        link_flags = scene_link_sources or []
        link_scene_count = sum(1 for flag in link_flags if flag)
        category_hints = self.match_category_display_hints(listing, product_info)
        compliance_platform = (
            "eBay" if self._is_ebay_listing(listing) else "亚马逊"
        )
        is_ebay = compliance_platform == "eBay"

        # 普通模式的文案作为参考
        standard_context = ""
        if standard_copy:
            standard_context += (
                f"\n=== STANDARD MODE COPY (普通模式已生成的文案，高级A+需保持核心信息一致) ===\n"
                f"Headline: {standard_copy.headline}\n"
                f"Subheadline: {standard_copy.subheadline}\n"
                f"Body: {standard_copy.body[:500]}\n"
            )
        if standard_analysis:
            standard_context += (
                f"Function: {standard_analysis.function[:300]}\n"
                f"Compatibility: {standard_analysis.compatibility[:300]}\n"
                f"Quality: {standard_analysis.quality[:300]}\n"
            )

        product_analysis_context = ""
        if product_info and product_info.get("product_name"):
            features_text = "\n".join(
                f"  {idx}. {feat}"
                for idx, feat in enumerate(product_info.get("core_features", []), 1)
            )
            vehicles = product_info.get("compatible_vehicles", [])
            vehicles_text = (
                "\n".join(f"  {idx}. {v}" for idx, v in enumerate(vehicles, 1))
                if vehicles
                else "  (none in listing — do NOT use for fitment/OE card copy)"
            )
            product_analysis_context = (
                "\n=== PRE-ANALYZED PRODUCT PROFILE ===\n"
                f"Product Name: {product_info.get('product_name', '')}\n"
                f"Category: {product_info.get('product_category', '')}\n"
                f"Core Features:\n{features_text}\n"
                f"Visual Appearance: {product_info.get('visual_appearance', '')}\n"
                f"Install Location: {product_info.get('install_location', '')}\n"
                f"Listing-only vehicle mentions (NOT for fitment card — card uses listing verbatim):\n{vehicles_text}\n"
            )

        reference_mode_note = (
            f"运营已提供素材图：\n"
            f"  - 细节图/产品特写 {detail_count} 张\n"
            f"  - 场景物品图/使用环境图 {scene_count} 张\n"
            "系统会自动为每张需求图分配一张细节图和一张场景图（循环复用），"
            "你只需为每张需求图输出正确的 reference_source。"
            if has_refs
            else "运营未提供参考图。design_request 只写构图/背景/文案排版方案。"
        )
        if link_scene_count > 0:
            reference_mode_note += (
                f"\n链接场景图规则：运营已通过链接/eBay 获取 {link_scene_count} 张场景物品图。"
                "分配了链接场景参考图的需求，design_request 须要求依次参考该链接图制作构图相近的内容，"
                f"且文案须符合{compliance_platform}合规，禁止出现违禁词。"
            )
        if category_hints:
            reference_mode_note += (
                "\n品类展示重点（须在 design_request 中体现）：\n"
                + "\n".join(f"- {hint}" for hint in category_hints)
            )

        strategist_role = (
            "You are a senior eBay US automotive aftermarket listing strategist "
            if is_ebay
            else "You are a senior Amazon US automotive aftermarket listing strategist "
        )
        system_prompt = (
            f"{strategist_role}"
            "specializing in Premium A+ Content design. "
            "Your job is to create Premium A+ versions (6 image cards), each covering ONE DISTINCT "
            "product information aspect. These 6 cards MUST cover 6 CLEARLY DIFFERENT aspects:\n"
            "  1. 车型适配+OE (Vehicle Fitment & OE Numbers)\n"
            "  2. 产品特点 (Product Features — key selling points from listing data)\n"
            "  3. 产品介绍 (Product Introduction — AI-distilled product intro)\n"
            "  4. 产品耐用性/可靠性 (Product Durability & Reliability — materials, craftsmanship, testing data)\n"
            "  5. 使用与安装方法 (Usage & Installation — how to use and install the product)\n"
            "  6. 品牌保障 (Brand Trust — Brand Promise + Maintenance / Care tips)\n"
            "*** CRITICAL: Each card MUST cover a SUBSTANTIALLY DIFFERENT aspect. DO NOT repeat content across cards. ***\n"
            "*** VEHICLE FITMENT RULE ***\n"
            "For Card #1 (车型适配+OE): copy listing vehicle fitment and OE numbers VERBATIM only. "
            "Do NOT rewrite, truncate, or append AI-inferred models. Card #1 copy_text will be overwritten "
            "server-side to match standard mode exactly from listing product info.\n"
            "*** CRITICAL COPY STYLE RULE ***\n"
            "DO NOT write long marketing paragraphs. DISTILL the listing data and product analysis into "
            "short, factual bullet points. Each bullet should be 5-15 English words. Each card should have "
            "6-10 bullet items. The total on-image copy per card must be 80-250 English characters.\n"
            "*** CRITICAL COPY ORDER RULE — VIOLATIONS WILL BE REJECTED ***\n"
            "For Card #1 (车型适配+OE): VEHICLE FITMENT + OE NUMBERS copied VERBATIM from listing only.\n"
            "  - Use the same fitment/OE content as standard mode 适配与OE号 card.\n"
            "  - Do NOT add models or OE numbers not present in listing product info.\n"
            "  - REJECTED: Card #1 starting with 'PRODUCT FEATURES' or listing selling points.\n"
            "For Card #2 (产品特点): key selling points, material/performance highlights from listing bullets.\n"
            "For Card #3 (产品介绍): product introduction — describing what the product IS/DOES.\n"
            "For Card #4 (产品耐用性/可靠性): materials, craftsmanship, testing certifications, durability data — NO installation instructions here.\n"
            "For Card #5 (使用与安装方法): step-by-step usage and installation guide — ONLY install/usage steps, NO durability/materials content.\n"
            "For Card #6 (品牌保障): Brand Promise + Maintenance / Care tips for extending product lifespan.\n"
            f"{_build_compliance_system_prompt(is_ebay)}"
            "Output strict JSON only, no markdown."
        )

        themes_desc = "\n".join(
            f"  {i+1}. {t[0]} — {t[1]}"
            for i, t in enumerate(PREMIUM_IMAGE_THEMES[:image_count])
        )

        user_prompt = (
            "Based on the listing data, pre-analyzed product profile, and standard mode copy, "
            "produce a Premium A+ image SOP package with 6 DISTINCT product information aspects.\n\n"
            "Return JSON:\n"
            "{\n"
            '  "product_analysis": { same structure as standard mode },\n'
            '  "copy": { same structure as standard mode },\n'
            '  "image_requirements": [\n'
            "    {\n"
            '      "index": 1,\n'
            '      "theme": "车型适配+OE",\n'
            f'      "size": "{self.settings.sop_premium_image_size}",\n'
            '      "reference_source": "composite",\n'
            '      "copy_text": "Product Name + OE Number\\nVEHICLE FITMENT\\n• (fitment)\\nOE NUMBER\\n• (oe numbers)",\n'
            '      "design_request": "中文设计需求：构图+文案排版方案"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Premium A+ Theme Guide (6 DISTINCT ASPECTS):\n"
            f"{themes_desc}\n\n"
            "copy_text rules (CRITICAL — each card covers ONE distinct aspect, NO content overlap):\n"
            "- DO NOT write long paragraphs. DISTILL facts into short bullets (5-15 words each).\n"
            "- Structure: ALL-CAPS headline + 6-10 bullet lines starting with •.\n"
            "- Target: 80-250 English characters per card. EXCEPTION: Card #1 uses listing fitment/OE verbatim and may exceed limit.\n"
            "- Vehicle fitment and OE numbers: listing VERBATIM only — no truncation, no AI supplements.\n\n"
            "- Image #1 (车型适配+OE): ONLY listing fitment + listing OE numbers (identical to standard 适配与OE号 card).\n"
            "    COMPATIBLE WITH / VEHICLE FITMENT\n"
            "    (verbatim listing fitment text)\n"
            "    OE NUMBERS / REPLACEMENT PART NUMBERS\n"
            "    (verbatim listing OE numbers)\n\n"
            "- Image #2 (产品特点): Key product features / selling points distilled from listing data.\n"
            "    PRODUCT FEATURES\n"
            "    • 3-4 bullets from product core features and key specifications\n"
            "    • 3-4 bullets on material, construction, and performance highlights\n"
            "    • 1-2 bullets on quality standards or testing\n\n"
            "- Image #3 (产品介绍): Product introduction — describing what the product IS and DOES.\n"
            "    PRODUCT INTRODUCTION\n"
            "    • 1 bullet: what the product IS (type, category, core identity)\n"
            "    • 1 bullet: what it DOES (primary function and purpose)\n"
            "    • 1 bullet: key differentiator or standout feature\n"
            "    • 1 bullet: compatibility scope or target application summary\n\n"
            "- Image #4 (产品耐用性/可靠性): Materials, craftsmanship, testing data, quality certifications.\n"
            "    PRODUCT DURABILITY & RELIABILITY\n"
            "    • 1-2 bullets on materials and construction quality\n"
            "    • 1-2 bullets on testing standards and certifications\n"
            "    • 1-2 bullets on wear resistance / longevity data\n"
            "    • 1-2 bullets on quality control and batch consistency\n\n"
            "- Image #5 (使用与安装方法): Step-by-step usage and installation guide.\n"
            "    USAGE & INSTALLATION\n"
            "    • 2-3 bullets on pre-installation preparation\n"
            "    • 2-3 bullets on step-by-step installation procedure\n"
            "    • 1-2 bullets on post-installation checks\n"
            "    • 1 bullet on safe usage and operating tips\n"
            "    CRITICAL: Only install/usage content here. NO durability, NO materials, NO features.\n\n"
            "- Image #6 (品牌保障): Brand trust — Brand Promise + Maintenance / Care.\n"
            "    WHY CHOOSE US\n"
            "    • 3-4 bullets on brand promise / quality commitment / customer support\n"
            "    CARE & MAINTENANCE\n"
            "    • 3-4 bullets on maintenance practices / care tips to extend product lifespan\n\n"
            "- ALL copy must stay CONSISTENT with the standard mode copy in core facts. "
            "Rephrase and reorder the same product information; DO NOT invent new product specs or OE numbers.\n"
            "- Each card MUST cover a SUBSTANTIALLY DIFFERENT aspect. NO repeating the same information across cards.\n"
            "- Keep line breaks (\\n) for visual separation between sections.\n"
            "- Use professional automotive aftermarket English tone throughout.\n\n"
            "design_request rules:\n"
            "- Analyze EACH card's copy_text before writing layout — every card MUST use a DIFFERENT composition and copy layout style.\n"
            "- Match layout to actual copy content: only mention OE/part-number placement when copy_text contains OE/OEM/part numbers.\n"
            "- Vary styles across cards: left/right split, top/bottom split, multi-column bullets, numbered steps, icon rows, centered headline + surrounding bullets, etc.\n"
            "- Write 1-2 short Chinese lines only. ONLY describe composition (构图) and copy layout (文案排版).\n"
            "- Do NOT reuse the same layout template across cards.\n\n"
            "reference_source rules: for premium A+, all 6 cards (including Card 1) use 'composite', 'detail', or 'scene' based on the theme. Card 1 (vehicle fitment) typically uses 'scene' or 'composite'. 'main' is NOT used in premium A+ mode because the white-background main image is a separate hero image.\n"
            f"System auto-cycles {detail_count} detail images + {scene_count} scene images across all cards.\n\n"
            f"*** {compliance_platform.upper()} COMPLIANCE — same rules as standard mode ***\n"
            f"{_build_compliance_user_prompt(is_ebay)}"
            f"- Image count: exactly {image_count}\n"
            f"- Images #2-#6: MUST include fitment/OE before features.\n"
            f"Main image: {main_image}\n"
            f"Detail images: {detail_text}\n"
            f"Scene images: {scene_text}\n"
            f"{product_analysis_context}"
            f"{standard_context}"
            f"{listing_context}"
        )

        body = {
            "model": self.settings.active_ai_model,
            "temperature": 0.45,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        result = await self._post_ai_json(
            "premium_sop",
            body,
            timeout=120,
            premium=True,
        )

        content = result["choices"][0]["message"]["content"]
        return json.loads(content)

    def _fallback_premium_generate(
        self,
        listing: ListingData,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        image_count: int,
        standard_copy: CopyBlock | None = None,
        standard_analysis: ProductAnalysis | None = None,
    ) -> tuple[ProductAnalysis, CopyBlock, list[ImageRequirement]]:
        """高级A+ 降级生成：复用普通模式的文案模板但按高级A+格式重组。"""
        analysis = self._fallback_analysis(listing)
        # 优先使用普通模式的文案
        if standard_copy and standard_copy.headline:
            headline = standard_copy.headline
            subheadline = standard_copy.subheadline
            body = standard_copy.body
        else:
            headline = listing.title[:100] if listing.title else f"{listing.sku} Premium Replacement Part"
            subheadline = "Premium quality, precision-engineered for reliable performance"
            body = f"{analysis.function} {analysis.quality}"[:900]
        copy = CopyBlock(
            headline=headline,
            subheadline=subheadline,
            body=body,
            keywords=self._fallback_keywords(listing),
        )

        oe = " / ".join(listing.oe_numbers) if listing.oe_numbers else ""
        compat = standard_analysis.compatibility if standard_analysis else analysis.compatibility
        quality = standard_analysis.quality if standard_analysis else analysis.quality
        function = standard_analysis.function if standard_analysis else analysis.function

        requirements: list[ImageRequirement] = []
        _detail_idx = [0]
        _scene_idx = [0]
        detail_pool = detail_references or []
        scene_pool = scene_references or []

        for idx in range(1, image_count + 1):
            theme, brief = PREMIUM_IMAGE_THEMES[min(idx - 1, len(PREMIUM_IMAGE_THEMES) - 1)]

            detail_img = detail_pool[_detail_idx[0] % len(detail_pool)] if detail_pool else ""
            scene_img = scene_pool[_scene_idx[0] % len(scene_pool)] if scene_pool else ""
            _detail_idx[0] += 1
            _scene_idx[0] += 1

            ref_images = []
            if detail_img:
                ref_images.append(detail_img)
            if scene_img:
                ref_images.append(scene_img)
            ref_primary = ref_images[0] if ref_images else ""

            reference_source = "composite" if (detail_img and scene_img) else ("detail" if detail_img else ("scene" if scene_img else "none"))

            copy_text = self._build_premium_fallback_copy(
                theme, listing, analysis, compat, quality, function, oe
            )
            design_request = self._build_premium_design_request(theme, idx, copy_text)

            requirements.append(
                ImageRequirement(
                    index=idx,
                    theme=theme,
                    size=self.settings.sop_premium_image_size,
                    copy_text=copy_text,
                    design_request=design_request,
                    reference_image=ref_primary,
                    reference_images=ref_images,
                    detail_image=detail_img,
                    scene_image=scene_img,
                    reference_source=reference_source,
                    reference_search_query="",
                )
            )
        source = standard_analysis or analysis
        info = getattr(source, "_product_info", None) or {}
        self._apply_canonical_fitment_oe_cards(
            requirements, listing, source, info, is_premium=True
        )
        return analysis, copy, requirements

    @staticmethod
    def _build_premium_card1_title(listing: ListingData, max_length: int = 80) -> str:
        """构建高级A+ Card1 标题：仅保留产品名称 + OE号。

        规则（按你提供的 SOP 图片）：
        - 去掉 Compatible with / Fits / Replace / Replacement 等适配/替换信息；
        - 优先组合：产品名称 + OE号；
        - 标题字符受限（默认 80），超长时先删减 OE号；
        - OE号过多或仍超长时，只保留产品名称。
        """
        raw_title = (listing.title or listing.sku or "").strip()
        if not raw_title:
            return ""

        # 1. 截断适配信息
        product_name = raw_title
        for pattern in COMPAT_PATTERNS:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                product_name = product_name[:match.start()].strip()
                break

        # 2. 截断 replace / replacement 信息
        replace_match = re.search(r"\b(replace|replacement)\b", product_name, re.IGNORECASE)
        if replace_match:
            product_name = product_name[:replace_match.start()].strip()

        # 3. 清理尾部常见冗余词，并规范化空格
        product_name = re.sub(
            r"\s+(?:for|fits|fit|oe|oe#|oe number|part number|replace|replacement)\s*$",
            "",
            product_name,
            flags=re.IGNORECASE,
        ).strip()
        product_name = re.sub(r"\s+", " ", product_name).strip()

        if not product_name:
            product_name = listing.sku or ""

        # 4. 过滤掉已经在产品名中出现的 OE号，避免重复
        oe_numbers = [oe for oe in (listing.oe_numbers or []) if oe.lower() not in product_name.lower()]

        def _make_title(oe_count: int | None) -> str:
            if oe_count and oe_numbers:
                oe_part = " / ".join(oe_numbers[:oe_count])
                return f"{product_name} {oe_part}".strip()
            return product_name

        # 5. 按优先级尝试：全部OE号 -> 前2个 -> 前1个 -> 仅产品名
        counts = [len(oe_numbers), 2, 1] if len(oe_numbers) > 1 else [1]
        for count in counts:
            candidate = _make_title(count)
            if len(candidate) <= max_length:
                return candidate

        # 6. 只保留产品名称
        if len(product_name) <= max_length:
            return product_name
        return product_name[:max_length].rstrip()

    @staticmethod
    def _is_fitment_oe_theme(theme: str, *, is_premium: bool = False) -> bool:
        text = (theme or "").strip()
        if not text:
            return False
        if is_premium:
            return "车型适配" in text or "OE" in text.upper()
        return "适配" in text or "OE" in text.upper()

    @classmethod
    def _text_needs_english_translation(cls, *parts: str) -> bool:
        return any(cls._CJK_RE.search(part or "") for part in parts)

    async def _translate_listing_fitment_oe(self, compat: str, oe: str) -> tuple[str, str]:
        """将 listing 适配/OE 译为英文，保留全部车型与 OE 号，不增删。"""
        cache_key = f"{compat}\0{oe}"
        cached = self._fitment_oe_translation_cache.get(cache_key)
        if cached is not None:
            return cached

        if not self.settings.active_ai_api_key:
            logger.warning("Listing 适配/OE 含非英文但 AI 未配置，保留原文")
            result = (compat, oe)
            self._fitment_oe_translation_cache[cache_key] = result
            return result

        prompt = (
            "Translate the automotive listing fitment and OE numbers below into professional English "
            "for Amazon US image copy.\n\n"
            "STRICT RULES:\n"
            "- Translate vehicle models, years, engine notes to English\n"
            "- Keep EVERY OE/part number EXACTLY unchanged (digits, letters, separators, order)\n"
            "- Do NOT add, remove, merge, or summarize any fitment line or OE number\n"
            "- Preserve line breaks in compatibility text\n\n"
            f"COMPATIBILITY (raw):\n{compat or '(empty)'}\n\n"
            f"OE NUMBERS (raw):\n{oe or '(empty)'}\n\n"
            'Reply JSON only: {"compatibility":"...","oe_numbers":"..."}'
        )
        body = {
            "model": self.settings.active_ai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an automotive listing translator. "
                        "Output valid JSON with keys compatibility and oe_numbers."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            result = await self._post_ai_json(
                "fitment_oe_translate",
                body,
                timeout=max(30, self.settings.ai_request_timeout),
            )
            content = result["choices"][0]["message"]["content"]
            data = json.loads(content)
            translated_compat = str(data.get("compatibility", "")).strip() or compat
            translated_oe = str(data.get("oe_numbers", "")).strip() or oe
            if self._text_needs_english_translation(translated_compat, translated_oe):
                logger.warning("Fitment/OE 翻译结果仍含中文，保留原文")
                translated_compat, translated_oe = compat, oe
            else:
                logger.info(
                    "[FITMENT-OE] translated compat=%d->%d oe=%d->%d chars",
                    len(compat),
                    len(translated_compat),
                    len(oe),
                    len(translated_oe),
                )
            output = (translated_compat, translated_oe)
        except Exception:
            logger.warning("Listing 适配/OE 翻译失败，保留原文", exc_info=True)
            output = (compat, oe)

        self._fitment_oe_translation_cache[cache_key] = output
        return output

    async def _resolve_translated_fitment_oe(
        self,
        listing: ListingData,
    ) -> tuple[str, str, str]:
        compat = self._resolve_listing_compatibility_text(listing)
        oe = self._resolve_listing_oe_text(listing)
        if self._text_needs_english_translation(compat, oe):
            compat, oe = await self._translate_listing_fitment_oe(compat, oe)
        copy_text = self._format_fitment_oe_copy(compat, oe)
        return compat, oe, copy_text

    def _apply_fitment_oe_to_analysis(self, analysis: ProductAnalysis) -> None:
        if self._current_fitment_compat:
            analysis.compatibility = self._current_fitment_compat
        if self._current_fitment_oe:
            analysis.oe_numbers = self._current_fitment_oe

    def _format_fitment_oe_copy(self, compat: str, oe_body: str) -> str:
        parts: list[str] = []
        parts.append("COMPATIBLE WITH / VEHICLE FITMENT")
        if compat.strip():
            parts.append(compat.strip())
        if oe_body:
            parts.extend(["", "OE NUMBERS / REPLACEMENT PART NUMBERS", oe_body])
        return "\n".join(parts)

    @staticmethod
    def _extract_fitment_clause(text: str) -> str:
        """从 title/描述中提取 Fit for / Compatible with 车型片段。"""
        raw = (text or "").strip()
        if not raw:
            return ""
        patterns = (
            r"(?:fit(?:s)?\s+for|compatible\s+with|application[s]?\s+(?:for|to))\s+"
            r"(.+?)(?:,\s*(?:replace|replaces|oe\b|oem\b|part\s+number|interchange)\b|$)",
            r"(?:fit(?:s)?\s+for|compatible\s+with)\s+(.+)",
        )
        for pattern in patterns:
            match = re.search(pattern, raw, re.IGNORECASE)
            if not match:
                continue
            clause = match.group(1).strip(" ,.;")
            if len(clause) >= 6 and re.search(r"[A-Za-z]", clause):
                return clause
        return ""

    @staticmethod
    def _is_ebay_listing(listing: ListingData) -> bool:
        return "ebay" in (listing.data_source or "").lower()

    @staticmethod
    def _build_ebay_hero_design_request(has_scene: bool = True) -> str:
        if has_scene:
            return (
                "1. 构图：一张主图与第一张场景物品图组合排版，"
                "主图占画面约80%为视觉主体，场景图作辅助；"
                "无文字，不做文案排版。"
            )
        return (
            "1. 构图：主图占画面约80%居中展示（暂无场景物品图）；"
            "无文字，不做文案排版。"
        )

    def _append_ebay_hero_reference_requirement(
        self,
        design_request: str,
        scene_image: str,
        scene_link_sources: list[bool] | None,
    ) -> str:
        """eBay 首图：补充链接场景参考图构图要求。"""
        if not scene_image:
            return design_request
        flags = scene_link_sources or []
        ordinal = 1
        if flags:
            if not flags[0]:
                return design_request
            ordinal = self._link_scene_ordinal(0, flags) or 1
        extra = (
            f"参考图要求：依次参考链接获取的场景图第 {ordinal} 张"
            f"（当前分配的场景参考图），制作一张内容构图相近的图片"
            f"（场景、产品位置、拍摄角度尽量一致）。"
        )
        base = (design_request or "").strip()
        if not base:
            return f"1. {extra}"
        numbered = re.findall(r"^(\d+)\.", base, flags=re.MULTILINE)
        next_no = max(int(n) for n in numbered) + 1 if numbered else 2
        return f"{base}\n{next_no}. {extra}"

    def _ebay_hero_allocation(
        self,
        main_image: str,
        scene_pool: list[str],
        scene_idx: list[int],
    ) -> dict[str, Any]:
        """eBay 标准 SOP 第 1 张：主图 + 场景池第一张场景物品图。"""
        scene_img = scene_pool[0] if scene_pool else ""
        if scene_img:
            scene_idx[0] = max(scene_idx[0], 1)
        ref_images = [main_image]
        if scene_img:
            ref_images.append(scene_img)
        return {
            "theme": "主图+场景",
            "detail_img": "",
            "scene_img": scene_img,
            "ref_images": ref_images,
            "ref_primary": main_image,
            "reference_source": "main_scene" if scene_img else "main",
            "copy_text": "Main image composite (no text)",
            "design_request": self._build_ebay_hero_design_request(has_scene=bool(scene_img)),
        }

    @staticmethod
    def _strip_design_request_number_prefix(line: str) -> str:
        """去掉重复的 '1. 1. 1.' 编号前缀。"""
        cleaned = re.sub(r"\s+", " ", (line or "").strip())
        while True:
            match = re.match(r"^(?:\d+\.\s*)+(.*)$", cleaned)
            if not match or not match.group(1):
                break
            rest = match.group(1).strip()
            if rest == cleaned:
                break
            cleaned = rest
        return cleaned

    def _resolve_listing_compatibility_text(self, listing: ListingData) -> str:
        """从领星 listing 提取车型适配（title/五点/描述），不做 AI 补充。"""
        hints = self._extract_listing_hints(listing)
        lines = [text.strip() for text in hints.get("compatibility", []) if str(text).strip()]

        for source in [listing.title, listing.description, *listing.bullet_points]:
            clause = self._extract_fitment_clause(source or "")
            if clause:
                lines.append(clause)

        # 若仅有整段 title，尽量只保留车型段
        normalized: list[str] = []
        for line in lines:
            if listing.title and line.strip() == listing.title.strip():
                clause = self._extract_fitment_clause(listing.title)
                normalized.append(clause or line)
            else:
                normalized.append(line)

        deduped = self._dedupe_texts(normalized)
        if deduped:
            return "\n".join(deduped)

        # 兜底：title 中含年款范围
        title = (listing.title or "").strip()
        if title and re.search(r"\d{4}\s*[-–]\s*\d{4}", title):
            clause = self._extract_fitment_clause(title)
            return clause or title
        return ""

    def _resolve_listing_oe_text(self, listing: ListingData) -> str:
        """仅从领星 listing 原文提取 OE 号，不做改写、截断或补充。"""
        if listing.oe_numbers:
            return ", ".join(str(x).strip() for x in listing.oe_numbers if str(x).strip())
        hints = self._extract_listing_hints(listing)
        oe_from_listing = [str(x).strip() for x in hints.get("oe", []) if str(x).strip()]
        if oe_from_listing:
            return ", ".join(oe_from_listing)
        return ""

    def _build_listing_fitment_oe_copy(self, listing: ListingData) -> str:
        """标准图与高级 A+ 共用：车型适配 + OE 来自 listing（必要时已译为英文）。"""
        if self._current_fitment_oe_copy:
            return self._current_fitment_oe_copy
        compat = self._resolve_listing_compatibility_text(listing)
        oe_body = self._resolve_listing_oe_text(listing)
        return self._format_fitment_oe_copy(compat, oe_body)

    def _resolve_full_compatibility(
        self,
        listing: ListingData,
        analysis: ProductAnalysis,
        product_info: dict[str, Any] | None = None,
    ) -> str:
        """兼容旧调用：车型适配仅来自 listing。"""
        _ = analysis, product_info
        return self._resolve_listing_compatibility_text(listing)

    def _resolve_full_oe_text(
        self,
        listing: ListingData,
        analysis: ProductAnalysis,
    ) -> str:
        """兼容旧调用：OE 仅来自 listing。"""
        _ = analysis
        return self._resolve_listing_oe_text(listing)

    def _build_standard_fitment_oe_copy(
        self,
        listing: ListingData,
        analysis: ProductAnalysis | None = None,
        product_info: dict[str, Any] | None = None,
    ) -> str:
        _ = analysis, product_info
        return self._build_listing_fitment_oe_copy(listing)

    def _build_premium_fitment_oe_copy(
        self,
        listing: ListingData,
        analysis: ProductAnalysis | None = None,
        product_info: dict[str, Any] | None = None,
    ) -> str:
        _ = analysis, product_info
        return self._build_listing_fitment_oe_copy(listing)

    def _apply_canonical_fitment_oe_cards(
        self,
        requirements: list[ImageRequirement],
        listing: ListingData,
        analysis: ProductAnalysis,
        product_info: dict[str, Any] | None = None,
        *,
        is_premium: bool = False,
        fitment_oe_copy: str | None = None,
    ) -> None:
        """标准图与高级 A+ 适配图使用完全相同的 listing 文案（含英文翻译）。"""
        _ = analysis, product_info, is_premium
        copy_text = fitment_oe_copy or self._build_listing_fitment_oe_copy(listing)
        for req in requirements:
            if not self._is_fitment_oe_theme(req.theme, is_premium=is_premium):
                continue
            req.copy_text = copy_text
            req.design_request = self._build_fitment_oe_design_request(copy_text, req.index)

    def _build_premium_card1_copy(
        self,
        listing: ListingData,
        compat: str,
        quality: str,
        function: str,
        oe: str,
        product_info: dict[str, Any] | None = None,
        analysis: ProductAnalysis | None = None,
    ) -> str:
        """Card 1 车型适配+OE：纯车型适配和OE号信息，不含产品特点、不含验证条目。"""
        if analysis is not None:
            return self._build_premium_fitment_oe_copy(listing, analysis, product_info)
        title_line = self._build_premium_card1_title(listing)
        parts: list[str] = [title_line, "", "VEHICLE FITMENT", compat or "(see listing for full fitment details)"]
        oe_body = " / ".join(listing.oe_numbers) if listing.oe_numbers else oe
        if oe_body:
            parts.extend(["", "OE NUMBER", oe_body])
        return "\n".join(parts)

    def _build_premium_fallback_copy(
        self,
        theme: str,
        listing: ListingData,
        analysis: ProductAnalysis,
        compat: str,
        quality: str,
        function: str,
        oe: str,
    ) -> str:
        """高级A+降级模式下的简洁文案：6个独立产品信息维度。"""
        bullets = listing.bullet_points or []
        oe_body = " / ".join(listing.oe_numbers) if listing.oe_numbers else oe

        # ── Card 1: 车型适配+OE (Only fitment/OE, no product features, no verification bullets) ──
        if "车型适配" in theme or "OE" in theme.upper():
            return self._build_listing_fitment_oe_copy(listing)

        # ── Card 2: 产品特点 (Key selling points from listing data) ──
        if "特点" in theme or "FEATURES" in theme.upper():
            lines = ["PRODUCT FEATURES"]
            # From bullets
            feature_bullets = [b for b in bullets if not any(k.lower() in b.lower() for k in ("fit", "compatible", "oe", "part number", "vehicle", "year", "model", "make"))]
            for b in feature_bullets[:4]:
                lines.append(f"• {self._clip_line(b, 95)}")
            # From analysis
            function_lines = self._bullet_lines_from_text(function or "", 3)
            for line in function_lines:
                if len(lines) < 8:
                    lines.append(f"• {line}")
            quality_lines = self._bullet_lines_from_text(quality or "", 3)
            for line in quality_lines:
                if len(lines) < 9:
                    lines.append(f"• {line}")
            # Ensure minimum content
            if len(lines) < 5:
                lines.extend([
                    "• Precision-engineered to OEM specifications",
                    "• Quality materials for reliable performance",
                    "• Rigorous testing before shipment",
                ])
            return "\n".join(lines[:10])

        # ── Card 3: 产品介绍 (Product introduction — what it IS/DOES) ──
        if "介绍" in theme:
            lines = ["PRODUCT INTRODUCTION"]
            # 1. What it IS
            product_type = self._extract_product_type(listing, analysis)
            lines.append(f"• {product_type}")
            # 2. What it DOES
            func_summary = self._extract_function_summary(function, bullets, listing)
            lines.append(f"• {func_summary}")
            # 3. Key differentiator
            diff = self._extract_differentiator(bullets, quality, listing)
            lines.append(f"• {diff}")
            # 4. Compatibility scope
            comp_summary = self._extract_compat_summary(compat, listing)
            lines.append(f"• {comp_summary}")
            return "\n".join(lines)

        # ── Card 4: 产品耐用性/可靠性 (Durability & Reliability — materials, testing, certifications) ──
        if "耐用性" in theme or "可靠性" in theme or "DURABILITY" in theme.upper():
            lines = ["PRODUCT DURABILITY & RELIABILITY"]
            # 1-2 Materials & construction
            quality_lines = self._bullet_lines_from_text(quality or "", 3)
            material_bullets = [b for b in bullets if any(k.lower() in b.lower() for k in ("material", "steel", "alloy", "brass", "metal", "forged", "coated", "sealed", "reinforced", "heavy-duty", "heavy duty"))]
            if material_bullets:
                for b in material_bullets[:2]:
                    lines.append(f"• {self._clip_line(b, 95)}")
            for line in quality_lines[:2]:
                if len(lines) < 5:
                    lines.append(f"• {line}")
            # 1-2 Testing / certifications
            if quality and len(quality) > 20:
                lines.append(f"• {self._clip_line(quality, 100)}")
            # Fallback testing data
            lines.append("• Rigorously factory tested to ensure consistent quality across every batch")
            # Wear resistance / longevity
            lines.append("• Designed for extended service life with wear-resistant construction")
            return "\n".join(lines[:9])

        # ── Card 5: 使用与安装方法 (Usage & Installation) ──
        if "使用" in theme or "安装" in theme or "USAGE" in theme.upper() or "INSTALLATION" in theme.upper():
            lines = ["USAGE & INSTALLATION"]
            # Pre-installation preparation
            lines.append("• Verify all parts are included and inspect for shipping damage")
            lines.append("• Review vehicle service manual for proper installation location")
            # Step-by-step installation
            install_lines = self._bullet_lines_from_text(analysis.installation or "", 4)
            if install_lines:
                for line in install_lines[:3]:
                    lines.append(f"• {self._clip_line(line, 100)}")
            else:
                lines.append("• Remove old part and clean mounting surface thoroughly")
                lines.append("• Install new part following factory torque specifications")
                lines.append("• Double-check all connections are secure and properly seated")
            # Post-installation checks
            lines.append("• Test operation before returning vehicle to service")
            # Safe usage tips
            lines.append("• Follow recommended maintenance schedule for optimal performance")
            return "\n".join(lines[:10])

        # ── Card 6: 品牌保障 (Brand Promise + Maintenance) ──
        if "品牌" in theme or "保障" in theme or "ASSURANCE" in theme.upper():
            lines = ["WHY CHOOSE US"]
            lines.extend([
                "• Factory-direct quality control and testing",
                "• Meets or exceeds OEM specifications",
                "• Protective packaging for safe delivery",
                "• Dedicated after-sales customer support",
                "• Cost-effective alternative to dealership parts",
                "• Consistent quality across every batch",
            ])
            lines.append("")
            lines.append("CARE & MAINTENANCE")
            care_lines = self._bullet_lines_from_text(analysis.maintenance or "", 5)
            if care_lines:
                for line in care_lines[:5]:
                    lines.append(f"• {line}")
            else:
                lines.extend([
                    "• Perform periodic visual checks for wear or damage",
                    "• Keep mounting points clean and properly torqued",
                    "• Avoid harsh operating conditions and overload",
                    "• Replace at first sign of performance degradation",
                    "• Follow vehicle service intervals for inspection",
                ])
            return "\n".join(lines)

        # Fallback to card 1
        return self._build_premium_card1_copy(listing, compat, quality, function, oe)

    @staticmethod
    def _copy_has_oe(copy_text: str) -> bool:
        text = (copy_text or "").upper()
        if not text.strip():
            return False
        oe_markers = (
            r"\bOE\b",
            r"\bOEM\b",
            r"OE NUMBER",
            r"OE NUMBERS",
            r"REPLACEMENT PART",
            r"PART NUMBER",
            r"\bMPN\b",
            r"INTERCHANGE",
        )
        return any(re.search(marker, text) for marker in oe_markers)

    @staticmethod
    def _pick_variant(options: list[str], seed: str, idx: int) -> str:
        if not options:
            return ""
        key = f"{seed}|{idx}"
        return options[(hash(key) & 0x7FFFFFFF) % len(options)]

    def _build_composition_line(self, theme: str, copy_text: str, idx: int) -> str:
        slot = max(idx - 1, 0)
        if "适配" in theme or "OE" in theme.upper():
            options = [
                "1. 构图：产品居左占约40%，适配/OE文案居右纵向排列。",
                "1. 构图：产品居中偏下，文案区块居上横向展开。",
                "1. 构图：产品居右，车型列表居左纵向排列。",
                "1. 构图：产品细节与场景参考图上下分割，文案叠加于留白区。",
            ]
        elif "安装" in theme or re.search(r"(?m)^\d+[\.)]\s", copy_text or ""):
            options = [
                "1. 构图：产品居左，安装步骤居右分步纵向排列。",
                "1. 构图：产品居中，步骤编号环绕产品分布。",
                "1. 构图：产品居右，步骤说明居左按序号纵向排列。",
            ]
        elif "巡检" in theme or "故障" in theme or "症状" in theme or "SIGNS" in (copy_text or "").upper():
            options = [
                "1. 构图：产品居中偏上，症状列表居下横向排列。",
                "1. 构图：产品居左，症状条目居右纵向排列。",
                "1. 构图：产品居中，症状围绕产品呈扇形分布。",
            ]
        elif "品质" in theme or "细节" in theme:
            options = [
                "1. 构图：产品居中放大展示，细节标注围绕产品排列。",
                "1. 构图：产品质感特写居左，品质卖点居右纵向排列。",
                "1. 构图：产品居中偏右，标注线指向关键材质细节。",
            ]
        elif "维护" in theme or "寿命" in theme:
            options = [
                "1. 构图：产品居左，保养建议居右纵向排列。",
                "1. 构图：产品居中偏下，保养条目居上横向卡片排列。",
            ]
        elif "功能" in theme:
            options = [
                "1. 构图：产品居中偏左，功能卖点居右纵向排列。",
                "1. 构图：产品居中，功能图标+短句横向排列于下方。",
                "1. 构图：产品居右，功能条目居左分两列排列。",
            ]
        else:
            options = [
                "1. 构图：产品居中偏左，文案居右排列。",
                "1. 构图：产品居中偏下，标题+条目居上横向展开。",
                "1. 构图：产品居右，文案区块居左纵向排列。",
            ]
        return self._pick_variant(options, theme + (copy_text or "")[:80], slot)

    def _build_copy_layout_line(self, theme: str, copy_text: str, idx: int) -> str:
        text = copy_text or ""
        slot = max(idx - 1, 0)
        has_oe = self._copy_has_oe(text)
        numbered = len(re.findall(r"(?m)^\d+[\.)]\s", text))
        bullets = len(re.findall(r"(?m)^[•\-]\s", text))
        sections = len(re.findall(r"(?m)^[A-Z][A-Z0-9 &/+\-]{3,}$", text))
        no_title = (idx % 5) in (0, 2, 4)

        if "适配" in theme or "OE" in theme.upper():
            if has_oe and sections >= 2:
                options = [
                    "2. 文案排版：上下双区块——上部车型适配标题+列表，下部OE号标题+编号列表。",
                    "2. 文案排版：左右分栏——左栏车型适配，右栏OE号列表。",
                    "2. 文案排版：车型条目用标签/卡片横向排列，OE号小字脚注置底，标题仅占一行。",
                    "2. 文案排版：左侧窄栏列车型，右侧宽栏列OE，不用半屏大标题。",
                ]
            elif has_oe:
                options = [
                    "2. 文案排版：标题仅占一行置顶，车型条目纵向排列，OE号独立区块置底。",
                    "2. 文案排版：车型与OE分两段纵向排列，标题弱化或小字标注。",
                    "2. 文案排版：车型标签云+OE编号列表混排，无大标题区。",
                    "2. 文案排版：首条车型加粗作引导，OE号以脚注形式置底。",
                ]
            else:
                options = [
                    "2. 文案排版：标题仅占一行，车型条目分两列纵向排列。",
                    "2. 文案排版：车型条目图标+文字卡片横向排列，无半屏标题。",
                    "2. 文案排版：首条车型加粗引导，其余条目纵向排列。",
                ]
        elif "安装" in theme or numbered >= 2:
            options = [
                "2. 文案排版：步骤按1-2-3纵向编号排列，不使用大标题。" if no_title else
                "2. 文案排版：标题仅占一行置顶，步骤按1-2-3纵向编号排列。",
                "2. 文案排版：安装步骤横向分栏排列，首条加粗引导。" if no_title else
                "2. 文案排版：标题仅占一行，安装步骤横向分栏排列。",
                "2. 文案排版：左侧序号列+右侧步骤说明，无独立标题区。",
            ]
        elif "巡检" in theme or "故障" in theme or "症状" in theme or "SIGNS" in text.upper():
            options = [
                "2. 文案排版：症状条目横向三列排列，不使用大标题。" if no_title else
                "2. 文案排版：KNOW THE SIGNS标题置顶，症状条目横向三列排列。",
                "2. 文案排版：左侧勾选图标+右侧症状列表，无标题区。",
                "2. 文案排版：症状条目围绕产品分布，首条加粗作引导语。",
            ]
        elif "品质" in theme or "细节" in theme:
            options = [
                "2. 文案排版：品质卖点图标+短句横向排列，无大标题。" if no_title else
                "2. 文案排版：标题置顶，品质卖点图标+短句横向排列。",
                "2. 文案排版：3-4条品质条目纵向等距排列，首条加粗。",
                "2. 文案排版：品质条目分两组左右对称排列。",
            ]
        elif "维护" in theme or "寿命" in theme:
            options = [
                "2. 文案排版：保养建议条目纵向排列带序号，无大标题。" if no_title else
                "2. 文案排版：标题置顶，保养建议条目纵向排列带序号。",
                "2. 文案排版：保养条目横向卡片排列，首条作引导语。",
            ]
        elif "功能" in theme:
            options = [
                "2. 文案排版：功能卖点横向图标+文字排列，无大标题。" if no_title else
                "2. 文案排版：KEY BENEFITS标题置顶，功能条目纵向排列。",
                "2. 文案排版：功能条目分两列纵向排列，首条加粗引导。",
            ]
        elif "特点" in theme or "FEATURES" in theme.upper():
            options = [
                "2. 文案排版：3-4条特点横向卡片排列，无大标题。" if no_title else
                "2. 文案排版：PRODUCT FEATURES标题置顶，卖点条目纵向排列。",
            ]
        elif "介绍" in theme or "INTRODUCTION" in text.upper():
            options = [
                "2. 文案排版：4条介绍分两列排列，无独立标题。" if no_title else
                "2. 文案排版：PRODUCT INTRODUCTION标题置顶，介绍条目纵向排列。",
            ]
        elif bullets >= 4:
            options = [
                "2. 文案排版：条目分两列纵向排列，不使用大标题。" if no_title else
                "2. 文案排版：标题置顶，条目分两列纵向排列。",
                "2. 文案排版：条目横向卡片式排列，首条加粗引导。",
                "2. 文案排版：左侧图标列+右侧条目，无标题区。",
            ]
        else:
            options = [
                "2. 文案排版：条目纵向排列，首条加粗引导，无大标题。" if no_title else
                "2. 文案排版：标题置顶加粗，条目纵向排列。",
                "2. 文案排版：条目分两列排列。",
                "2. 文案排版：短句横向排列，无标题区。",
            ]

        return self._pick_variant(options, text[:120] + theme, slot)

    def _build_design_request_from_copy(
        self,
        theme: str,
        copy_text: str,
        idx: int,
    ) -> str:
        if idx == 1:
            return "1. 构图：产品居中。\n2. 文案排版：无文案。"
        comp = self._build_composition_line(theme, copy_text, idx)
        layout = self._build_copy_layout_line(theme, copy_text, idx)
        return f"{comp}\n{layout}"

    @staticmethod
    def _build_fitment_oe_design_request(copy_text: str = "", idx: int = 2) -> str:
        return AiService._build_design_request_from_copy_static("适配与OE号", copy_text, idx)

    @staticmethod
    def _build_design_request_from_copy_static(
        theme: str,
        copy_text: str,
        idx: int,
    ) -> str:
        svc = object.__new__(AiService)
        return svc._build_design_request_from_copy(theme, copy_text, idx)

    def _build_premium_design_request(
        self,
        theme: str,
        idx: int,
        copy_text: str = "",
    ) -> str:
        """高级A+设计需求：根据文案结构生成差异化排版。"""
        return self._build_design_request_from_copy(theme, copy_text, idx)

    # ── Card 3 & 4 降级文案辅助方法 ──

    @staticmethod
    def _extract_product_type(listing: ListingData, analysis: ProductAnalysis) -> str:
        """提取产品类型描述 — Card 3 bullet 1"""
        title = listing.title or listing.sku
        # 从标题中提取产品名
        lowered = title.lower()
        for keyword in ["replacement", "direct fit", "aftermarket", "assembly", "set", "kit", "pair"]:
            if keyword in lowered:
                return f"{title[:100]} — direct-fit aftermarket replacement part"
        return f"{title[:100]} — a precision-engineered aftermarket replacement component"

    @staticmethod
    def _extract_function_summary(function: str, bullets: list[str], listing: ListingData) -> str:
        """提取功能摘要 — Card 3 bullet 2"""
        if function:
            clipped = AiService._clip_line(function, 110)
            if clipped:
                return clipped
        if bullets:
            b = bullets[0] if bullets else ""
            return AiService._clip_line(b, 110) if b else "Restores factory-intended performance and functionality"
        return "Restores factory-intended performance and functionality for the specified application"

    @staticmethod
    def _extract_differentiator(bullets: list[str], quality: str, listing: ListingData) -> str:
        """提取产品差异点 — Card 3 bullet 3"""
        # 从 quality 或 bullets 中找区分点
        if quality:
            clipped = AiService._clip_line(quality, 110)
            if clipped and len(clipped) > 10:
                return clipped
        # 从 bullets 中找第2-3条
        for b in bullets[1:3]:
            if b and not any(k in b.lower() for k in ("fit", "compatible", "oe", "vehicle", "year", "make", "model")):
                return AiService._clip_line(b, 110)
        return "Built with quality materials for reliable, long-lasting performance"

    @staticmethod
    def _extract_compat_summary(compat: str, listing: ListingData) -> str:
        """提取兼容范围摘要 — Card 3 bullet 4"""
        if compat and len(compat) > 5:
            clipped = AiService._clip_line(compat, 110)
            if clipped:
                return f"Compatible with {clipped.lower()}"
        title = listing.title or listing.sku
        return f"Designed for vehicles referenced in: {AiService._clip_line(title, 80)}"

    @staticmethod
    def _build_why_matters(listing: ListingData, analysis: ProductAnalysis) -> str:
        """为什么重要 — Card 4 bullet 1"""
        title = listing.title or listing.sku
        # 提取产品名
        prod = title.split(" for ")[0].strip() if " for " in title.lower() else title[:60]
        return f"Essential {prod} ensures optimal vehicle system performance and safety"

    @staticmethod
    def _build_design_advantage(function: str, quality: str) -> str:
        """设计优势 — Card 4 bullet 2"""
        if function:
            lines = [s.strip() for s in re.split(r"[;.]", function) if s.strip()]
            if lines:
                return f"{lines[0][:100]} for dependable operation"
        if quality:
            return f"{AiService._clip_line(quality, 95)} for consistent performance"
        return "Engineered to meet or exceed OE design and performance standards"

    @staticmethod
    def _build_durability_insight(quality: str, analysis: ProductAnalysis) -> str:
        """耐久性洞察 — Card 4 bullet 3"""
        if quality and len(quality) > 15:
            return f"{AiService._clip_line(quality, 100)} — designed for extended service intervals"
        maint = analysis.maintenance or ""
        if maint and len(maint) > 10:
            return f"{AiService._clip_line(maint, 100)} for longer lifespan"
        return "Built with durable materials and precision manufacturing for extended service life"

    @staticmethod
    def _build_value_proposition(listing: ListingData) -> str:
        """价值主张 — Card 4 bullet 4"""
        title = listing.title or listing.sku
        prod = title.split(" for ")[0].strip()[:40] if " for " in title.lower() else title[:40]
        return f"Cost-effective {prod} alternative to dealership parts without compromising quality or fit"

    @staticmethod
    def _build_usage_insight(analysis: ProductAnalysis, bullets: list[str]) -> str:
        """安装/使用洞察 — Card 4 bullet 5"""
        install = analysis.installation or ""
        if install and len(install) > 10:
            return f"Direct replacement installation — {AiService._clip_line(install, 85)}"
        return "Direct-fit replacement installation with standard tools for most applications"

    @staticmethod
    def _build_sixth_insight(listing: ListingData, analysis: ProductAnalysis, bullets: list[str]) -> str:
        """AI分析产品洞察 — Card 4 bullet 6 (additional AI-generated insight)"""
        # 从产品分析中提取独特优势或性能亮点
        quality = analysis.quality or ""
        function = analysis.function or ""
        compat = analysis.compatibility or ""
        maint = analysis.maintenance or ""

        if compat and len(compat) > 15:
            return f"Broad compatibility — {AiService._clip_line(compat, 85)}"
        if quality and len(quality) > 15:
            return f"{AiService._clip_line(quality, 100)} — tested for real-world conditions"
        if maint and len(maint) > 10:
            return f"{AiService._clip_line(maint, 100)} — extends service life"
        if function:
            lines = [s.strip() for s in re.split(r"[;.]", function) if s.strip()]
            if len(lines) > 1:
                return f"{lines[-1][:100]} for enhanced vehicle performance"
            if lines:
                return f"{lines[0][:100]} — critical for reliable vehicle operation"
        title = listing.title or listing.sku
        prod = title.split(" for ")[0].strip()[:45] if " for " in title.lower() else title[:45]
        return f"Precision-engineered {prod} delivers consistent performance across all operating conditions"

    async def _analyze_product_deeply(
        self,
        listing: ListingData,
        sku: str,
    ) -> dict[str, Any]:
        """【第一步】基于领星 Listing 数据深度分析产品。

        提取：产品名称、类别、核心特征（五点）、图片搜索关键词、典型使用场景、
        视觉外观、安装位置等，为后续图片搜索提供精准上下文。
        """
        listing_context = self._build_listing_context(listing)

        if self._is_ebay_listing(listing):
            compliance_note = (
                "COMPLIANCE: This is an eBay listing for image SOP copy. "
                "Follow eBay compliance — no absolute/superlative/price claims, no unsubstantiated "
                "health/eco claims, no counterfeit language, no free shipping or off-eBay contact. "
                "Standard replacement-part install language is OK."
            )
        else:
            compliance_note = (
                "COMPLIANCE: This is an Amazon US listing for a standard replacement aftermarket part. "
                "Do NOT generate any content suggesting removal/deletion/bypass/modification of factory equipment "
                "or emission/exhaust/fuel system tampering. The product is a direct-fit replacement, not a modification device."
            )

        system_prompt = (
            "You are an expert Amazon automotive/powersports/marine aftermarket product analyst. "
            "Your task is to deeply analyze a product listing and extract structured product information. "
            "Focus on understanding exactly WHAT this product is, its physical characteristics, "
            "typical usage scenarios, and how it would appear in real-world photographs. "
            "Output strict JSON only, no markdown. "
            f"{compliance_note}"
        )
        user_prompt = (
            "Analyze the listing data below and return a detailed product profile as JSON.\n\n"
            "Return JSON with this structure:\n"
            "{\n"
            '  "product_name": "Concise English product name (e.g. Throttle Body, Brake Pad Set, Ignition Coil)",\n'
            '  "product_category": "Precise category: throttle body / brake pad / ignition coil / turbocharger / fuel pump / control arm / shock absorber / ball joint / etc.",\n'
            '  "product_type": "Product type qualifier: automotive / PWC / marine outboard / motorcycle / ATV / powersports / heavy equipment",\n'
            '  "core_features": [\n'
            '    "5 key feature sentences in English extracted from listing bullets and title",\n'
            '    "Each should describe a distinct value proposition or specification"\n'
            "  ],\n"
            '  "image_search_keywords": [\n'
            '    "5-8 English keyword phrases optimal for image search engines",\n'
            '    "Include: product name + part type + vehicle context + photo type qualifiers",\n'
            '    "Example: [\'throttle body installed engine bay\', \'throttle body mechanic installation\', ...]"\n'
            "  ],\n"
            '  "typical_usage_scene": "1-2 English sentences describing where and how this product is used in reality (e.g. installed in engine bay near intake manifold, visible when hood is open)",\n'
            '  "visual_appearance": "1-2 English sentences describing the product\'s physical look: shape, color, materials, key visible components, size",\n'
            '  "install_location": "Where this part is installed on the vehicle/equipment (e.g. engine bay, undercarriage, wheel assembly, dashboard)",\n'
            '  "compatible_vehicles": [\n'
            '    "List ONLY vehicle make/model/series, equipment model, engine code, or platform explicitly mentioned in the listing title, bullets, or description",\n'
            '    "Do NOT infer or supplement popular models not present in listing product info"\n'
            "  ],\n"
            '  "is_part_of_larger_assembly": true/false,\n'
            '  "parent_assembly": "If part of a larger system, name it (e.g. intake system, brake system, suspension). Empty string if standalone."\n'
            "}\n\n"
            "Rules:\n"
            "- product_name: Extract the core product name from the title. Strip brand prefixes, 'New', 'Replacement', etc.\n"
            "- product_category: Be specific. Don't say 'auto part' — say 'throttle body' or 'brake pad'.\n"
            "- product_type: Determine from the listing content whether this is for cars (automotive), PWC (Sea-Doo, WaveRunner, Jet Ski), marine outboard, motorcycle, ATV, heavy equipment, air compressors, etc.\n"
            "- core_features: Extract exactly 5 key selling points from the listing — these are equivalent to Amazon bullet points (五点). Focus on: function, compatibility, quality, ease of install, durability.\n"
            "- image_search_keywords: These are for finding REAL PHOTOS of the product. Include scene context. MUST be specific enough to avoid generic/watermarked stock photos. Include vehicle make/model if mentioned.\n"
            "- typical_usage_scene: Describe the real-world environment where this product is used. For car parts, mention engine bay/undercarriage/etc.\n"
            "- visual_appearance: Describe what the product physically looks like so image search can match visually similar results.\n"
            "- install_location: Be precise about WHERE on the vehicle this part goes.\n"
            "- compatible_vehicles: Extract ONLY models explicitly mentioned in the listing. Do NOT infer or supplement popular models.\n"
            "- All text MUST be in English.\n"
            "- DO NOT invent exact model years or trim levels not implied by the listing. Inferred models should be common/popular examples only.\n\n"
            f"{listing_context}"
        )

        body = {
            "model": self.settings.active_ai_model,
            "temperature": 0.3,  # 低温获取更精确的分析
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        result = await self._post_ai_json(
            "product_analysis",
            body,
            timeout=90,
        )

        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        # 规范化返回结果
        return {
            "product_name": str(parsed.get("product_name", "")).strip(),
            "product_category": str(parsed.get("product_category", "")).strip(),
            "product_type": str(parsed.get("product_type", "")).strip(),
            "core_features": self._normalize_str_list(parsed.get("core_features", [])),
            "image_search_keywords": self._normalize_str_list(parsed.get("image_search_keywords", [])),
            "typical_usage_scene": str(parsed.get("typical_usage_scene", "")).strip(),
            "visual_appearance": str(parsed.get("visual_appearance", "")).strip(),
            "install_location": str(parsed.get("install_location", "")).strip(),
            "compatible_vehicles": self._normalize_str_list(parsed.get("compatible_vehicles", [])),
            "is_part_of_larger_assembly": bool(parsed.get("is_part_of_larger_assembly", False)),
            "parent_assembly": str(parsed.get("parent_assembly", "")).strip(),
        }

    async def recommend_popular_vehicles(
        self,
        listing: ListingData,
        product_info: dict[str, Any],
    ) -> list[str]:
        """为 AI 车型搜索推荐 10-15 款热门适配车型（listing 明确车型 + 市场热门补充）。"""
        explicit = self._normalize_str_list(product_info.get("compatible_vehicles", []))
        listing_mentions = self._extract_listing_vehicle_mentions(listing)
        seed = self._merge_vehicle_list(explicit, listing_mentions)

        if not self.settings.active_ai_api_key:
            return seed[:15]

        listing_context = self._build_listing_context(listing, product_info)
        product_name = product_info.get("product_name", "") or (listing.title or listing.sku)
        product_type = product_info.get("product_type", "")
        category = product_info.get("product_category", "")

        system_prompt = (
            "You are a US automotive/powersports aftermarket fitment expert. "
            "Recommend popular vehicle or equipment models for marketing and image reference. "
            "Output strict JSON only, no markdown."
        )
        user_prompt = (
            "Based on the product listing below, recommend 10-15 POPULAR vehicle models "
            "or equipment that this replacement part fits or is commonly associated with in the US market.\n\n"
            "Rules:\n"
            "- ALWAYS include every model explicitly stated in the listing fitment first\n"
            "- Then ADD other high-search-volume / best-selling compatible models in the same platform, generation, or engine family\n"
            "- If fitment spans a year range, list several popular year+trim combos "
            "(e.g. '1988 Jeep Wrangler YJ 4.0L', '1989 Jeep Wrangler YJ 2.5L', '1990 Jeep Wrangler YJ')\n"
            "- Format each entry: 'YYYY-YYYY Make Model [Trim/Engine]' or 'Make Model Generation'\n"
            "- Target 10-15 distinct entries when fitment allows; minimum 8 when listing has clear compatibility\n"
            "- For PWC/marine/motorcycle/ATV use equipment model names instead of passenger cars\n"
            "- Do NOT include models clearly incompatible with the listing fitment\n"
            "- English only, one model per array item, no duplicates\n\n"
            f"Product: {product_name}\n"
            f"Category: {category or 'auto part'}\n"
            f"Type: {product_type or 'automotive'}\n"
            f"Known listing fitment ({len(seed)}): {', '.join(seed[:10]) or 'none'}\n\n"
            f"{listing_context}\n\n"
            'Return JSON: {"popular_vehicles": ["model 1", "model 2", "..."]}'
        )

        body = {
            "model": self.settings.active_ai_model,
            "temperature": 0.45,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            result = await self._post_ai_json(
                "vehicle_recommendations",
                body,
                timeout=45,
            )
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            ai_list = self._normalize_str_list(parsed.get("popular_vehicles", []))
            merged = self._merge_vehicle_list(seed, ai_list)
            if len(merged) >= 6:
                return merged[:15]
            # AI 返回过少时，保留 seed 并尽量补全
            return self._merge_vehicle_list(merged, seed)[:15]
        except Exception as exc:
            logger.warning("热门车型推荐 AI 调用失败，回退 listing 解析: %s", exc)
            return seed[:15] if seed else explicit[:15]

    @staticmethod
    def _merge_vehicle_list(*lists: list[str], max_items: int = 15) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for lst in lists:
            for item in lst:
                cleaned = re.sub(r"\s+", " ", str(item).strip())
                if not cleaned:
                    continue
                key = cleaned.lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(cleaned)
                if len(merged) >= max_items:
                    return merged
        return merged

    def _extract_listing_vehicle_mentions(self, listing: ListingData) -> list[str]:
        """从 listing 标题/适配描述中解析车型条目，作为热门推荐的基础种子。"""
        hints = self._extract_listing_hints(listing)
        raw_parts: list[str] = []

        for text in hints["compatibility"]:
            raw_parts.extend(re.split(r"[\n\r;；|]+", text))
            raw_parts.extend(re.split(r"\s*/\s*", text))

        title = listing.title or ""
        if re.search(r"\bfor\b", title, re.I):
            after_for = re.split(r"\bfor\b", title, maxsplit=1, flags=re.I)[-1]
            raw_parts.extend(re.split(r"[,，;；|/]+", after_for))

        vehicle_hint = re.compile(
            r"\b(?:19|20)\d{2}(?:\s*[-–~]\s*(?:19|20)\d{2})?\s+"
            r"[A-Za-z][A-Za-z0-9\s\-./]{2,}|"
            r"\b(?:Jeep|Ford|Chevrolet|Chevy|Honda|Toyota|BMW|Mercedes|Audi|Nissan|"
            r"Dodge|Ram|GMC|Volkswagen|VW|Subaru|Mazda|Hyundai|Kia|Lexus|Volvo|Porsche|"
            r"Harley|Sea-Doo|Yamaha|Polaris|Can-Am|Arctic Cat)\b[A-Za-z0-9\s\-./]{0,40}",
            re.I,
        )

        results: list[str] = []
        for part in raw_parts:
            chunk = re.sub(r"\s+", " ", part.strip(" .,-"))
            if len(chunk) < 5:
                continue
            for match in vehicle_hint.finditer(chunk):
                value = re.sub(r"\s+", " ", match.group(0).strip(" .,-"))
                if len(value) >= 5:
                    results.append(value[:120])
            if vehicle_hint.search(chunk) and chunk not in results:
                results.append(chunk[:120])

        return self._dedupe_texts(results)[:12]

    @staticmethod
    def _normalize_str_list(raw: Any) -> list[str]:
        """将各种输入格式规范化为字符串列表。"""
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str):
            parts = re.split(r"[\n,，;；|]+", raw)
            return [part.strip() for part in parts if part.strip()]
        return []

    def _normalize_product_info(
        self,
        raw: Any,
        listing: ListingData,
    ) -> dict[str, Any]:
        value = raw if isinstance(raw, dict) else {}
        title = (listing.title or listing.sku).strip()
        return {
            "product_name": str(value.get("product_name") or title).strip(),
            "product_category": str(value.get("product_category", "")).strip(),
            "product_type": str(value.get("product_type", "")).strip(),
            "core_features": self._normalize_str_list(
                value.get("core_features") or listing.bullet_points[:5]
            ),
            "image_search_keywords": self._normalize_str_list(
                value.get("image_search_keywords") or listing.keywords[:8]
            ),
            "typical_usage_scene": str(value.get("typical_usage_scene", "")).strip(),
            "visual_appearance": str(value.get("visual_appearance", "")).strip(),
            "install_location": str(value.get("install_location", "")).strip(),
            "compatible_vehicles": self._normalize_str_list(
                value.get("compatible_vehicles")
            ),
            "is_part_of_larger_assembly": bool(
                value.get("is_part_of_larger_assembly", False)
            ),
            "parent_assembly": str(value.get("parent_assembly", "")).strip(),
        }

    @staticmethod
    def _enrich_analysis_with_product_info(
        analysis: ProductAnalysis,
        product_info: dict[str, Any],
    ) -> None:
        """将产品深度分析结果注入 ProductAnalysis，供搜索词构建使用。

        通过添加自定义属性存储图像搜索所需的关键上下文。
        """
        analysis._product_info = product_info  # type: ignore[attr-defined]

    async def _call_ai_model(
        self,
        listing: ListingData,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        image_count: int,
        has_operator_references: bool = False,
        product_info: dict[str, Any] | None = None,
        scene_link_sources: list[bool] | None = None,
    ) -> dict[str, Any]:
        listing_context = self._build_listing_context(listing, product_info)
        detail_text = ", ".join(detail_references) if detail_references else "无"
        scene_text = ", ".join(scene_references) if scene_references else "无"
        has_refs = has_operator_references and (detail_references or scene_references)
        detail_count = len(detail_references) if detail_references else 0
        scene_count = len(scene_references) if scene_references else 0
        link_flags = scene_link_sources or []
        link_scene_count = sum(1 for flag in link_flags if flag)
        category_hints = self.match_category_display_hints(listing, product_info)
        compliance_platform = (
            "eBay" if self._is_ebay_listing(listing) else "亚马逊"
        )
        is_ebay = compliance_platform == "eBay"
        if is_ebay:
            image1_rules = (
                "- Image #1 (eBay hero): ONE main product image + the FIRST scene item image combined in layout.\n"
                "- Image #1 reference_source MUST be \"main_scene\" when a scene image exists (NOT Amazon white-bg-only \"main\").\n"
                "- Image #1 copy_text: exactly \"Main image composite (no text)\".\n"
                "- Image #1 design_request: line 1 = composition (main ~80% + first scene); line 2 MUST add reference rule: match link scene #1 composition (scene, product position, angle).\n"
            )
        else:
            image1_rules = (
                "- Image #1 copy_text: exactly \"Main image - white background (no text)\".\n"
                "- Image #1 MUST be pure white background main image: NO text, NO badges, NO OE numbers.\n"
                "- Image #1 uses white-bg main product only; images #2+ are composite designs.\n"
            )
        reference_mode_note = (
            f"运营已提供素材图：\n"
            f"  - 细节图/产品特写 {detail_count} 张（{detail_text}）\n"
            f"  - 场景物品图/使用环境图 {scene_count} 张（{scene_text}）\n"
            "你需要分析这两类图片的内容——细节图展示产品材质/工艺/结构，场景图展示安装环境/使用场景/车型关联。\n"
            "结合领星产品数据，为每张需求图生成针对性的 copy_text 和 design_request，"
            "并且必须为每张需求图输出 reference_source 字段来指定它需要哪种参考图。"
            "design_request 中应明确引用运营提供的参考图的可用元素，告诉设计师如何利用已有素材。"
            if has_refs
            else "运营未提供参考图。design_request 只写构图/背景/文案排版方案。"
        )
        if link_scene_count > 0:
            reference_mode_note += (
                f"\n链接场景图规则：运营已通过链接/eBay 获取 {link_scene_count} 张场景物品图（位于场景图池前部）。"
                "当某张需求图分配了链接来源的场景参考图时，design_request 须写明："
                "依次参考对应链接场景图，制作内容构图相近的图片（场景、角度、安装位置尽量一致），"
                f"且图片文案必须符合{compliance_platform}合规，禁止出现违禁词。"
            )
        if category_hints:
            reference_mode_note += (
                "\n品类展示重点（须在相关图片 design_request 中体现）：\n"
                + "\n".join(f"- {hint}" for hint in category_hints)
            )

        # ── 构建产品深度分析上下文 ──
        product_analysis_context = ""
        if product_info and product_info.get("product_name"):
            features_text = "\n".join(
                f"  {idx}. {feat}"
                for idx, feat in enumerate(product_info.get("core_features", []), 1)
            )
            keywords_text = ", ".join(product_info.get("image_search_keywords", []))
            vehicles = product_info.get("compatible_vehicles", [])
            vehicles_text = (
                "\n".join(f"  {idx}. {v}" for idx, v in enumerate(vehicles, 1))
                if vehicles
                else "  (none in listing — do NOT use for fitment/OE card copy)"
            )
            product_analysis_context = (
                "\n=== PRE-ANALYZED PRODUCT PROFILE (已完成的产品深度分析) ===\n"
                f"Product Name: {product_info.get('product_name', '')}\n"
                f"Category: {product_info.get('product_category', '')}\n"
                f"Product Type: {product_info.get('product_type', '')}\n"
                f"Core Features (五点):\n{features_text}\n"
                f"Image Search Keywords: {keywords_text}\n"
                f"Typical Usage Scene: {product_info.get('typical_usage_scene', '')}\n"
                f"Visual Appearance: {product_info.get('visual_appearance', '')}\n"
                f"Install Location: {product_info.get('install_location', '')}\n"
                f"Parent Assembly: {product_info.get('parent_assembly', '') or 'N/A'}\n"
                f"Listing-only vehicle mentions (NOT for fitment card — card uses listing verbatim):\n{vehicles_text}\n"
            )

        profile_instruction = (
            "A cached product profile is provided. Validate and reuse it; return it in product_profile. "
            if product_info and product_info.get("product_name")
            else
            "First derive a concise product_profile from the listing, then use it for all remaining fields. "
        )
        strategist_role = (
            "You are a senior eBay US automotive, powersports, and marine aftermarket listing strategist, "
            if is_ebay
            else "You are a senior Amazon US automotive, powersports, and marine aftermarket listing strategist, "
        )
        system_prompt = (
            f"{strategist_role}"
            "technical writer, and visual creative director for high-converting image sets. "
            f"{profile_instruction}"
            "Use that product profile to build a thorough product_analysis summary, "
            "then DISTILL the profile plus listing facts into rich on-image copy and actionable designer briefs. "
            "For OE numbers: directly COPY the raw text from the listing VERBATIM — do NOT rewrite, reformat, truncate, or supplement.\n"
            "For vehicle fitment/compatibility: directly COPY the raw text from the listing VERBATIM — do NOT rewrite, truncate, or append AI-inferred models.\n"
            "For other fields: extract and maintenance guidance from the source text whenever present; "
            "infer conservatively when implied. "
            "When the listing mentions Sea-Doo, WaveRunner, Jet Ski, Yamaha Waverunner, or Kawasaki Jet Ski, "
            "treat them as PERSONAL WATERCRAFT (PWC), not generic boats or marine vessels. "
            "When the listing mentions Mercury Marine, Yamaha Outboard, Honda Marine, Suzuki Marine, or outboard motors, "
            "treat them as marine outboard engines. "
            "IMPORTANT: 运营已手动上传的参考图片路径已提供在上下文中。"
            "你需要仔细分析这些图片文件名和路径中可能包含的产品信息，结合产品数据，"
            "生成精准的 copy_text 和 design_request。图片不再由系统在线搜索，"
            "所有参考素材均由运营手动提供。"
            f"{_build_compliance_system_prompt(is_ebay)}"
            "Output strict JSON only, no markdown."
        )
        user_prompt = (
            "Produce the product profile and complete image SOP package from the listing data below in one response.\n\n"
            "Return JSON with this structure:\n"
            "{\n"
            '  "product_profile": {\n'
            '    "product_name": "concise English product name",\n'
            '    "product_category": "specific product category",\n'
            '    "product_type": "automotive / marine / PWC / motorcycle / other",\n'
            '    "core_features": ["exactly 5 distinct listing-backed features"],\n'
            '    "image_search_keywords": ["5-8 specific English image-search phrases"],\n'
            '    "typical_usage_scene": "real-world usage environment",\n'
            '    "visual_appearance": "physical appearance and material",\n'
            '    "install_location": "installation location",\n'
            '    "compatible_vehicles": ["explicit models first, then conservative popular examples"],\n'
            '    "is_part_of_larger_assembly": false,\n'
            '    "parent_assembly": ""\n'
            "  },\n"
            '  "product_analysis": {\n'
            '    "function": "2-4 English sentences: core product function, purpose, and customer benefits",\n'
            '    "installation": "2-4 English sentences: install approach, tools, difficulty, alignment/torque tips",\n'
            '    "inspection": "2-4 English sentences: how to inspect the part and symptoms when it is damaged/failing",\n'
            '    "maintenance": "2-4 English sentences: daily use habits and maintenance to extend service life",\n'
            '    "compatibility": "DIRECT COPY — copy vehicle fitment/compatibility text from listing data VERBATIM only. Do NOT rewrite, truncate, or append models.",\n'
            '    "oe_numbers": "DIRECT COPY — copy OE/OEM part numbers from listing data VERBATIM only. Do NOT rewrite, reformat, truncate, or abbreviate.",\n'
            '    "quality": "2-4 English sentences: material, construction, testing, durability, and quality positioning"\n'
            "  },\n"
            '  "copy": {\n'
            '    "headline": "English headline for listing/image marketing copy",\n'
            '    "subheadline": "English subheadline",\n'
            '    "body": "4-6 English sentences covering function, quality, install, inspection, maintenance. Do NOT include vehicle fitment or OE numbers here — those are already fully covered in the compatibility and oe_numbers fields.",\n'
            '    "keywords": ["10-15 English Amazon backend search terms derived from listing content"]\n'
            "  },\n"
            '  "image_requirements": [\n'
            "    {\n"
            '      "index": 1,\n'
            '      "theme": "主图",\n'
            '      "size": "1600*1600",\n'
            '      "reference_source": "main",\n'
            '      "copy_text": "Rich ENGLISH on-image copy (see copy_text rules below)",\n'
            '      "design_request": "详细中文设计师作图需求（见 design_request rules below）"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "reference_source rules (images 2+):\n"
            '- 根据每张图的主题语义、文案内容以及运营提供的参考图数量，从 "detail" / "scene" / "composite" 中选择：\n'
            '  • "detail" = 该图主要由产品细节图驱动（材质/工艺/结构特写）\n'
            '  • "scene"  = 该图主要由场景物品图/使用环境图驱动（安装环境/使用场景/车型关联）\n'
            '  • "composite" = 同时需要场景图+细节图叠加（场景作为背景，产品细节作为前景焦点）\n'
            '  • "main"   = 仅需主图（亚马逊 index=1；eBay index=1 请用 composite）\n'
            '- 不要按主题死磕：如果安装指南需要用细节特写来展示关键结构，就选 "detail" 或 "composite"；如果品质细节想展示产品装在车上的样子，也可以选 "scene" 或 "composite"。\n'
            '- 每个需求图的参考图不得超过 2 张：1 张 detail、或 1 张 scene、或各 1 张的 composite。严禁把多个细节图或多个场景图堆进同一个需求图。\n'
            f'- 运营已提供 {detail_count} 张细节图和 {scene_count} 张场景图。系统会为每张需求图同时分配一张细节图和一张场景图（两者均循环复用：不够时从头重复使用）。你只需根据主题语义为每个需求选择正确的 reference_source（场景图在上/细节图在下时选 composite，仅需一种时选 scene 或 detail），系统会自动完成图源循环。\n'
            "- 如果运营没有提供该类参考图，仍输出正确的 reference_source（系统会降级兜底）。\n\n"
            "Analysis rules:\n"
            "- compatibility: Directly copy vehicle fitment/compatibility from listing VERBATIM only. Do NOT append AI-inferred models.\n"
            "- oe_numbers: Directly copy OE/OEM numbers from listing VERBATIM only — no rewriting, formatting, merging, or truncation.\n"
            "- Derive quality from bullets about brand new, direct-fit, tested, durable, reliable, heavy-duty, OEM-level.\n"
            "- Derive inspection from failure symptoms: noise, vibration, wear, cracks, poor fit, overheating, etc.\n"
            "- Derive maintenance from proper torque, periodic checks, avoid overload, clean/lubricate if relevant.\n"
            "- If Search keywords from API is N/A or empty, you MUST derive 10-15 Amazon backend search terms from title, bullets, description, OE, and compatibility.\n"
            "- Keywords should be concise English terms/phrases buyers would search (part type, vehicle, OE, engine, year range).\n\n"
            "Language rules:\n"
            "- product_analysis and copy MUST be in English.\n"
            "- image_requirements theme MUST use Chinese labels: 主图, 核心功能, 安装指南, 适配与OE号, 品质细节, 巡检与故障症状, 维护与延长寿命.\n"
            "- image_requirements copy_text MUST be in English — this is the ACTUAL text to typeset ON the image.\n"
            "- image_requirements design_request MUST be in Chinese — a detailed brief FOR the designer.\n"
            f"- image_requirements size MUST be {self.settings.sop_image_size} for every entry.\n\n"
            "copy_text rules (images 2+):\n"
            "- DO NOT output a one-line slogan. Distill listing bullets, keywords, description, OE, and product_analysis "
            "into substantial on-image copy a designer can place directly.\n"
            "- Structure with line breaks (\\n): (1) ALL-CAPS headline, (2) 3-8 bullet lines starting with •, "
            "(3) optional OE/replaces line when relevant.\n"
            "- Each bullet must carry a concrete fact: year range, make/model, engine, torque, symptom, install step, "
            "quality claim, or maintenance tip — sourced from listing or analysis.\n"
            "- Theme guidance:\n"
            "  • 核心功能: headline like KEY BENEFITS / RESTORE PERFORMANCE + benefit bullets from function analysis\n"
            "  • 安装指南: headline like INSTALLATION GUIDE / EASY INSTALL + numbered or bulleted steps from installation\n"
            "  • 适配与OE号: headline COMPATIBLE WITH / VEHICLE FITMENT + copy listing fitment VERBATIM + headline OE NUMBERS / REPLACEMENT PART NUMBERS + copy listing OE numbers VERBATIM (same content as premium A+ Card 1; no AI additions)\n"
            "  • 品质细节: headline PREMIUM QUALITY / BUILT TO LAST + material/construction bullets\n"
            "  • 巡检与故障症状: headline KNOW THE SIGNS / WHEN TO REPLACE + symptom/check bullets\n"
            "  • 维护与延长寿命: headline EXTEND SERVICE LIFE / PROPER CARE + maintenance bullets\n"
            "- Target length: 80-350 English characters per image (excluding image #1).\n"
            "- EXCEPTION: 适配与OE号 card may exceed 350 characters when copying full listing fitment/OE verbatim. Do NOT truncate or add models not in listing.\n"
            f"{image1_rules}\n"
            "design_request rules:\n"
            "- Analyze EACH card's copy_text structure before writing layout — every card MUST have a DIFFERENT layout style.\n"
            "- Match layout to actual copy content: only mention OE/part-number placement when copy_text contains OE/OEM/part numbers.\n"
            "- Vary composition across cards: left/right split, top/bottom split, multi-column bullets, numbered steps, icon rows, etc.\n"
            "- Write 1-2 SHORT Chinese lines only. ONLY describe composition (构图) and copy layout (文案排版).\n"
            "- Do NOT describe: background color/style, reference images, scene placement, vehicle placement, element positioning details, product placement specifics, source materials, or any other design details.\n"
            "- Focus SOLELY on two things: (1) how the product and text areas are arranged relative to each other (left/right, top/bottom, centered), (2) how the copy text is structured on the image (headline position, bullet layout direction).\n"
            "- Format example (symptoms card, no OE in copy):\n"
            "  1. 构图：产品居中偏上，症状列表居下横向排列。\n"
            "  2. 文案排版：KNOW THE SIGNS标题置顶，症状条目横向三列排列。\n"
            "- Do NOT default every card to 'title on top + vertical bullets + OE at bottom'.\n"
            "- NOT every card needs a visible title/headline on the image — vary across cards: "
            "some with headline, some bullet-only, some icon+text rows, some numbered steps without a title block.\n"
            "- Keep it extremely simple and minimal — designer only needs composition and copy layout guidance.\n\n"
            f"{_build_compliance_user_prompt(is_ebay)}"
            f"Other rules:\n"
            f"- Output exactly {image_count} image_requirements entries.\n"
            f"{'' if is_ebay else '- Image #1 MUST be pure white background main image: NO text, NO badges, NO OE numbers.\n'}"
            "- Images 2+ must be visually diverse and map to the analysis dimensions above.\n"
            "- Each design_request must be concise (3-4 lines max).\n"
            "- At least 1 image must highlight compatibility with full year/make/model detail; "
            "at least 1 must highlight OE numbers when available.\n"
            "- copy_text = distilled ENGLISH on-image copy; design_request = detailed Chinese brief FOR the designer.\n"
            f"- {reference_mode_note}\n"
            f"{'' if is_ebay else '- Image #1 uses white-bg main product only; images #2+ are composite designs.\n'}\n"
            f"Main image (white background product): {main_image}\n"
            f"Detail images (product close-ups): {detail_text}\n"
            f"Scene images (environment/installation): {scene_text}\n\n"
            f"{product_analysis_context}"
            f"{listing_context}"
        )

        body = {
            "model": self.settings.active_ai_model,
            "temperature": 0.55,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        result = await self._post_ai_json(
            "standard_sop",
            body,
            timeout=120,
        )

        content = result["choices"][0]["message"]["content"]
        return json.loads(content)

    def _build_listing_context(
        self,
        listing: ListingData,
        product_info: dict[str, Any] | None = None,
    ) -> str:
        bullets = [str(value)[:450] for value in (listing.bullet_points or [])[:8]]
        bullet_lines = "\n".join(f"{idx}. {text}" for idx, text in enumerate(bullets, 1))
        keywords = ", ".join(listing.keywords[:15]) if listing.keywords else "N/A"
        oe_list = ", ".join(listing.oe_numbers[:12]) if listing.oe_numbers else "N/A"
        tags = ", ".join(listing.listing_tags[:10]) if listing.listing_tags else "N/A"
        hints = self._extract_listing_hints(listing)

        lines = [
            "=== LISTING DATA (from Lingxing product search API) ===",
            f"MSKU: {listing.sku}",
            f"ASIN: {listing.asin or 'N/A'}",
            f"Title: {listing.title or 'N/A'}",
            f"Bullet points:\n{bullet_lines or 'N/A'}",
            f"Product description: {listing.description[:3500] or 'N/A'}",
            f"Search keywords (API, may be empty): {keywords if keywords != 'N/A' else 'N/A — derive from listing content'}",
            f"Extracted OE numbers: {oe_list}",
            f"Listing tags: {tags}",
        ]
        if hints["compatibility"]:
            lines.append(f"Compatibility hints: {' | '.join(hints['compatibility'][:4])}")
        if hints["quality"]:
            lines.append(f"Quality hints: {' | '.join(hints['quality'][:4])}")
        if hints["oe"]:
            lines.append(f"OE hints from bullets: {', '.join(hints['oe'])}")
        return "\n".join(lines)

    def _extract_listing_hints(self, listing: ListingData) -> dict[str, list[str]]:
        corpus_parts = [listing.title, listing.description, *listing.bullet_points]
        corpus = "\n".join(part for part in corpus_parts if part)
        compatibility: list[str] = []
        quality: list[str] = []
        oe: list[str] = list(listing.oe_numbers)

        for bullet in listing.bullet_points:
            text = bullet.strip()
            if not text:
                continue
            lowered = text.lower()
            if any(re.search(pattern, lowered) for pattern in COMPAT_PATTERNS):
                compatibility.append(text)
            if any(re.search(pattern, lowered) for pattern in QUALITY_PATTERNS):
                quality.append(text)
            oe.extend(self._extract_oe_from_text(text))

        if listing.title and any(
            re.search(pattern, listing.title, re.IGNORECASE) for pattern in COMPAT_PATTERNS
        ):
            clause = self._extract_fitment_clause(listing.title)
            compatibility.insert(0, clause or listing.title)

        return {
            "compatibility": self._dedupe_texts(compatibility),
            "quality": self._dedupe_texts(quality),
            "oe": self._dedupe_texts(oe),
        }

    @staticmethod
    def _extract_oe_from_text(text: str) -> list[str]:
        patterns = [
            r"(?:OEM\s*(?:Part\s*(?:Number|No\.?|#)?|#|Number|No\.?)|"
            r"OE\s*(?:Part\s*(?:Number|No\.?|#)?|#|Number|No\.?)|"
            r"Part\s*(?:Number|No\.?|#)|"
            r"Replaces?|Replace\s+for)"
            r"[:：]?\s*"
            r"([A-Z0-9][A-Z0-9\-./]*(?:\s*/\s*[A-Z0-9][A-Z0-9\-./]*)*)",
        ]
        found: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                chunk = match.group(1)
                for part in re.split(r"\s*/\s*", chunk):
                    value = part.strip(" ,.;")
                    if len(value) >= 4 and re.search(r"\d", value):
                        found.append(value)
        return found

    @staticmethod
    def _dedupe_texts(values: list[str]) -> list[str]:
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

    def _parse_payload(
        self,
        payload: dict[str, Any],
        listing: ListingData,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        image_count: int,
        is_premium: bool = False,
    ) -> tuple[ProductAnalysis, CopyBlock, list[ImageRequirement]]:
        analysis_data = payload.get("product_analysis", {})
        copy_data = payload.get("copy", {})
        image_items = payload.get("image_requirements", [])

        analysis = self._analysis_from_dict(analysis_data, listing)
        copy = CopyBlock(
            headline=str(copy_data.get("headline", "")).strip(),
            subheadline=str(copy_data.get("subheadline", "")).strip(),
            body=str(copy_data.get("body", "")).strip(),
            keywords=self._parse_keywords_from_payload(copy_data, payload),
        )

        requirements = self._build_requirements_from_items(
            image_items, listing, main_image, detail_references, scene_references, image_count, copy, analysis,
            is_premium=is_premium,
        )
        if not analysis.function:
            analysis = self._fallback_analysis(listing)
        return analysis, copy, requirements

    def _parse_keywords_from_payload(self, copy_data: dict[str, Any], payload: dict[str, Any]) -> list[str]:
        raw = copy_data.get("keywords")
        if raw in (None, "", []):
            raw = payload.get("keywords")
        if isinstance(raw, str):
            parts = re.split(r"[\n,，;；|/]+", raw)
            if len(parts) == 1 and " " in raw.strip():
                parts = raw.strip().split()
            return [part.strip() for part in parts if part.strip()]
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return []

    def _finalize_listing_keywords(self, listing: ListingData, copy: CopyBlock) -> None:
        api_keywords = [str(item).strip() for item in listing.keywords if str(item).strip()]
        ai_keywords = [str(item).strip() for item in copy.keywords if str(item).strip()]

        if api_keywords:
            listing.keywords = self._dedupe_texts(api_keywords)
            if not copy.keywords:
                copy.keywords = listing.keywords
            return

        if ai_keywords:
            listing.keywords = self._dedupe_texts(ai_keywords)
            copy.keywords = listing.keywords
            return

        fallback = self._fallback_keywords(listing)
        listing.keywords = fallback
        copy.keywords = fallback

    def _fallback_keywords(self, listing: ListingData) -> list[str]:
        hints = self._extract_listing_hints(listing)
        keywords: list[str] = []
        keywords.extend(listing.oe_numbers[:6])

        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "your",
            "our",
            "are",
            "was",
            "has",
            "have",
            "new",
            "all",
            "not",
            "you",
            "can",
            "will",
            "into",
            "also",
            "part",
            "parts",
            "replacement",
            "compatible",
            "compatibility",
            "notice",
            "function",
            "quality",
            "direct",
            "fit",
            "oem",
            "style",
        }

        sources = [listing.title, listing.description, *listing.bullet_points[:5], *hints["compatibility"]]
        for text in sources:
            if not text:
                continue
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-./]{2,}", text):
                cleaned = token.strip("-./")
                if len(cleaned) < 3:
                    continue
                lowered = cleaned.lower()
                if lowered in stopwords:
                    continue
                if re.fullmatch(r"\d{7,14}", cleaned):
                    keywords.append(cleaned)
                elif any(ch.isdigit() for ch in cleaned) and any(ch.isalpha() for ch in cleaned):
                    keywords.append(cleaned)
                elif cleaned[0].isupper() or lowered in {"bmw", "turbocharger", "turbo", "engine", "mount"}:
                    keywords.append(cleaned)

        for text in hints["compatibility"]:
            for match in re.finditer(
                r"\b(?:BMW|Audi|Mercedes|Toyota|Honda|Ford|Chevrolet|Nissan|Volkswagen|VW|Lexus|"
                r"Hyundai|Kia|Mazda|Subaru|Jeep|Dodge|Ram|GMC|Cadillac|Volvo|Porsche|Mini)\b"
                r"(?:\s+[A-Za-z0-9\-./]{2,}){0,3}",
                text,
                re.I,
            ):
                phrase = re.sub(r"\s+", " ", match.group(0)).strip()
                if phrase:
                    keywords.append(phrase)

        for match in re.finditer(r"\b(?:N20|N26|B58|2\.0L|3\.0L|4\.0L)\b", " ".join(sources), re.I):
            keywords.append(match.group(0))

        return self._dedupe_texts(keywords)[:15]

    def _analysis_from_dict(self, data: dict[str, Any], listing: ListingData) -> ProductAnalysis:
        fallback = self._fallback_analysis(listing)
        return ProductAnalysis(
            function=str(data.get("function", "")).strip() or fallback.function,
            installation=str(data.get("installation", "")).strip() or fallback.installation,
            inspection=str(data.get("inspection", "")).strip() or fallback.inspection,
            maintenance=str(data.get("maintenance", "")).strip() or fallback.maintenance,
            compatibility=str(data.get("compatibility", "")).strip() or fallback.compatibility,
            oe_numbers=str(data.get("oe_numbers", "")).strip() or fallback.oe_numbers,
            quality=str(data.get("quality", "")).strip() or fallback.quality,
        )

    def _normalize_premium_requirements(
        self,
        requirements: list[ImageRequirement],
        listing: ListingData,
        analysis: ProductAnalysis,
        standard_analysis: ProductAnalysis | None = None,
        product_info: dict[str, Any] | None = None,
        fitment_oe_copy: str | None = None,
    ) -> list[ImageRequirement]:
        """强制高级A+ 6张卡结构：按索引固定主题，Card1固定为车型适配+OE。"""
        source_analysis = standard_analysis or analysis
        info = product_info or getattr(source_analysis, "_product_info", None) or {}
        oe = self._resolve_full_oe_text(listing, source_analysis)
        compat = self._resolve_full_compatibility(listing, source_analysis, info)
        quality = source_analysis.quality or analysis.quality
        function = source_analysis.function or analysis.function
        card1_copy = fitment_oe_copy or self._build_listing_fitment_oe_copy(listing)

        normalized: list[ImageRequirement] = []
        for idx in range(1, 7):
            theme, _ = PREMIUM_IMAGE_THEMES[idx - 1]
            req = requirements[idx - 1] if idx - 1 < len(requirements) else None

            if idx == 1:
                copy_text = card1_copy
            else:
                # Card 2-6 优先使用 AI 文案，过短则 fallback
                ai_copy = (req.copy_text if req else "").strip()
                if ai_copy and len(ai_copy) >= 80:
                    copy_text = ai_copy
                else:
                    copy_text = self._build_premium_fallback_copy(
                        theme, listing, analysis, compat, quality, function, oe
                    )

            design_request = self._build_premium_design_request(theme, idx, copy_text)

            # 保留 AI 参考图分配（高级A+ Card 1 不强制主图，使用场景/细节图）
            ref_primary = req.reference_image if req else ""
            ref_images = req.reference_images if req else []
            detail_img = req.detail_image if req else ""
            scene_img = req.scene_image if req else ""
            reference_source = req.reference_source if req else "none"
            if not ref_images:
                ref_images = [""]
                ref_primary = ""
                reference_source = "none"

            normalized.append(
                ImageRequirement(
                    index=idx,
                    theme=theme,
                    size=self.settings.sop_premium_image_size,
                    copy_text=copy_text,
                    design_request=design_request,
                    reference_image=ref_primary,
                    reference_images=ref_images,
                    detail_image=detail_img,
                    scene_image=scene_img,
                    reference_source=reference_source,
                    reference_search_query="",
                )
            )
        return normalized

    def _build_requirements_from_items(
        self,
        image_items: list[Any],
        listing: ListingData,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        image_count: int,
        copy: CopyBlock,
        analysis: ProductAnalysis,
        is_premium: bool = False,
    ) -> list[ImageRequirement]:
        oe_text = self._resolve_listing_oe_text(listing)
        requirements: list[ImageRequirement] = []

        # 每个文案/行都需要：细节图（循环复用）+ 场景物品图（循环复用）
        _detail_idx = [0]
        _scene_idx = [0]
        detail_pool = detail_references or []
        scene_pool = scene_references or []

        def _next_detail() -> str:
            """循环取细节图，不够从头复用"""
            if not detail_pool:
                return ""
            img = detail_pool[_detail_idx[0] % len(detail_pool)]
            return img

        def _next_scene() -> str:
            """循环取场景物品图，取完从头来"""
            if not scene_pool:
                return ""
            img = scene_pool[_scene_idx[0] % len(scene_pool)]
            return img

        for idx in range(1, image_count + 1):
            item = image_items[idx - 1] if idx - 1 < len(image_items) else {}
            if not isinstance(item, dict):
                item = {}
            theme_default, brief_default = (PREMIUM_IMAGE_THEMES if is_premium else IMAGE_THEMES)[
                min(idx - 1, len(PREMIUM_IMAGE_THEMES if is_premium else IMAGE_THEMES) - 1)
            ]
            theme = str(item.get("theme", theme_default)).strip() or theme_default
            copy_text = str(item.get("copy_text", "")).strip()
            design_request = str(item.get("design_request", "")).strip()
            size = self._normalize_image_size(str(item.get("size", "")).strip())

            if idx == 1 and not is_premium:
                if self._is_ebay_listing(listing):
                    hero = self._ebay_hero_allocation(main_image, scene_pool, _scene_idx)
                    theme = hero["theme"]
                    detail_img = hero["detail_img"]
                    scene_img = hero["scene_img"]
                    ref_images = hero["ref_images"]
                    ref_primary = hero["ref_primary"]
                    reference_source = hero["reference_source"]
                    copy_text = hero["copy_text"]
                    design_request = hero["design_request"]
                else:
                    # 第1张：主图白底产品图（亚马逊标准模式）
                    detail_img = ""
                    scene_img = ""
                    ref_images = [main_image]
                    ref_primary = main_image
                    reference_source = "main"
                    copy_text = "Main image - white background (no text)"
                    design_request = "1. 构图：产品居中。\n2. 文案排版：无文案。"
            else:
                # 每行都分配：细节图（循环复用）+ 场景物品图（循环复用）
                # 高级A+ Card 1 也是车型适配+OE文案卡片，使用场景图/细节图，不占用主图
                detail_img = _next_detail()
                scene_img = _next_scene()
                _detail_idx[0] += 1
                _scene_idx[0] += 1

                # 参考图：场景图 + 细节图（每行各一张）
                ref_images: list[str] = []
                if detail_img:
                    ref_images.append(detail_img)
                if scene_img:
                    ref_images.append(scene_img)

                ref_primary = ref_images[0] if ref_images else ""
                reference_source = "composite" if (detail_img and scene_img) else ("detail" if detail_img else ("scene" if scene_img else "none"))

                if is_premium:
                    if not copy_text or len(copy_text) < 80:
                        copy_text = self._build_premium_fallback_copy(
                            theme, listing, analysis,
                            analysis.compatibility or "",
                            analysis.quality or "",
                            analysis.function or "",
                            oe_text,
                        )
                    else:
                        copy_text = self._normalize_copy_text(copy_text)
                    if not design_request:
                        design_request = self._build_premium_design_request(theme, idx, copy_text)
                    else:
                        design_request = self._condense_design_request(design_request)
                else:
                    if self._is_fitment_oe_theme(theme, is_premium=False):
                        copy_text = self._build_listing_fitment_oe_copy(listing)
                    elif not copy_text or len(copy_text) < 80:
                        copy_text = self._build_rich_copy_text(theme, listing, analysis, copy)
                    else:
                        copy_text = self._normalize_copy_text(copy_text)
                    if not design_request:
                        design_request = self._build_concise_design_request(theme, copy_text, idx)
                    else:
                        design_request = self._condense_design_request(design_request)

            logger.info(
                f"[IMAGE-ALLOC] idx={idx} theme={theme} source={reference_source} "
                f"detail={_detail_idx[0]}/{len(detail_pool)} "
                f"scene={_scene_idx[0]}/{len(scene_pool)} "
                f"refs={ref_images}"
            )

            requirements.append(
                ImageRequirement(
                    index=idx,
                    theme=theme,
                    size=size,
                    copy_text=copy_text,
                    design_request=design_request,
                    reference_image=ref_primary,
                    reference_images=ref_images,
                    detail_image=detail_img,
                    scene_image=scene_img,
                    reference_source=reference_source,
                    reference_search_query="",
                )
            )
        return requirements

    def _fallback_generate(
        self,
        listing: ListingData,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        image_count: int,
    ) -> tuple[ProductAnalysis, CopyBlock, list[ImageRequirement]]:
        analysis = self._fallback_analysis(listing)
        headline = listing.title[:100] if listing.title else f"{listing.sku} Premium Replacement Part"
        copy = CopyBlock(
            headline=headline,
            subheadline="Engineered for reliable performance and straightforward installation",
            body=(
                f"{analysis.function} {analysis.compatibility} {analysis.oe_numbers} "
                f"{analysis.quality} {analysis.installation} {analysis.inspection} {analysis.maintenance}"
            ).strip()[:900],
            keywords=self._fallback_keywords(listing),
        )

        oe_text = self._resolve_listing_oe_text(listing)
        requirements: list[ImageRequirement] = []

        # 每行都分配：细节图（循环复用）+ 场景物品图（循环复用）
        _detail_idx = [0]
        _scene_idx = [0]
        detail_pool = detail_references or []
        scene_pool = scene_references or []

        for idx in range(1, image_count + 1):
            theme, brief = IMAGE_THEMES[min(idx - 1, len(IMAGE_THEMES) - 1)]

            if idx == 1:
                if self._is_ebay_listing(listing):
                    hero = self._ebay_hero_allocation(main_image, scene_pool, _scene_idx)
                    theme = hero["theme"]
                    detail_img = hero["detail_img"]
                    scene_img = hero["scene_img"]
                    ref_images = hero["ref_images"]
                    ref_primary = hero["ref_primary"]
                    reference_source = hero["reference_source"]
                    copy_text = hero["copy_text"]
                    design_request = hero["design_request"]
                else:
                    detail_img, scene_img = "", ""
                    ref_images = [main_image]
                    ref_primary = main_image
                    reference_source = "main"
                    copy_text = "Main image - white background (no text)"
                    design_request = "1. 构图：产品居中。\n2. 文案排版：无文案。"
            else:
                detail_img = detail_pool[_detail_idx[0] % len(detail_pool)] if detail_pool else ""
                scene_img = scene_pool[_scene_idx[0] % len(scene_pool)] if scene_pool else ""
                _detail_idx[0] += 1
                _scene_idx[0] += 1

                ref_images = []
                if detail_img:
                    ref_images.append(detail_img)
                if scene_img:
                    ref_images.append(scene_img)
                ref_primary = ref_images[0] if ref_images else ""
                reference_source = "composite" if (detail_img and scene_img) else ("detail" if detail_img else ("scene" if scene_img else "none"))

                copy_text = self._build_rich_copy_text(theme, listing, analysis, copy)
                design_request = self._build_concise_design_request(theme, copy_text, idx)

            requirements.append(
                ImageRequirement(
                    index=idx,
                    theme=theme,
                    size=self.settings.sop_image_size,
                    copy_text=copy_text,
                    design_request=design_request,
                    reference_image=ref_primary,
                    reference_images=ref_images,
                    detail_image=detail_img,
                    scene_image=scene_img,
                    reference_source=reference_source,
                    reference_search_query="",
                )
            )
        return analysis, copy, requirements

    def _fallback_analysis(self, listing: ListingData) -> ProductAnalysis:
        hints = self._extract_listing_hints(listing)
        bullets = listing.bullet_points
        title = listing.title or listing.sku
        oe_values = hints["oe"] or listing.oe_numbers
        oe_joined = ", ".join(oe_values) if oe_values else ""

        compatibility_text = ""
        if hints["compatibility"]:
            compatibility_text = " ".join(hints["compatibility"][:2])
        elif re.search(r"for\s+[A-Za-z0-9]", title, re.I):
            compatibility_text = f"Designed for applications referenced in the listing title: {title}."

        quality_text = ""
        if hints["quality"]:
            quality_text = " ".join(hints["quality"][:2])
        else:
            quality_text = (
                "Built as a direct-fit replacement component with emphasis on stable operation and durable construction."
            )

        function_source = bullets[:2] or [title]
        return ProductAnalysis(
            function=(
                f"{title} restores intended component performance for the target application. "
                f"Key benefits include: {'; '.join(function_source[:2])}."
            ),
            installation=(
                "Direct bolt-on replacement for this part category. "
                "Use basic hand tools, verify alignment before final torque, and test operation after installation."
            ),
            inspection=(
                "Inspect for cracks, deformation, abnormal wear, leaks, or loose mounting points before and after install. "
                "Common failure symptoms include noise, vibration, poor fit, reduced performance, or premature wear."
            ),
            maintenance=(
                "Avoid overload, harsh impacts, and contaminated operating conditions during daily use. "
                "Perform periodic visual checks and maintain proper torque to extend service life."
            ),
            compatibility=compatibility_text or "Refer to listing bullet points for exact vehicle/application fitment.",
            oe_numbers=(
                f"Key OE/OEM references: {oe_joined}."
                if oe_joined
                else "Refer to listing bullet points for replacement part numbers."
            ),
            quality=quality_text,
        )

    @staticmethod
    def _normalize_copy_text(text: str) -> str:
        cleaned = text.replace("\\n", "\n").strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    # ── 平台合规过滤（Amazon / eBay 分流）──

    @staticmethod
    def _filter_compliance_violations(
        text: str,
        platform: str = "amazon",
    ) -> tuple[str, list[str]]:
        """检查文本中的合规违禁词，返回 (过滤后文本, 违禁词列表)。"""
        if not text:
            return text, []
        lowered = text.lower()
        violations: list[str] = []
        for banned in _compliance_banned_set(platform):
            pattern = re.compile(rf"(?<!\w){re.escape(banned)}(?!\w)", re.IGNORECASE)
            if pattern.search(lowered):
                violations.append(banned)
        return text, violations

    @staticmethod
    def _filter_compliance_emission_warnings(text: str) -> list[str]:
        """检测排放/气体相关的"软禁用"词（仅 Amazon），返回命中的词列表。"""
        if not text:
            return []
        lowered = text.lower()
        warnings: list[str] = []
        for term in _AMAZON_COMPLIANCE_EMISSION_SOFT:
            pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
            if pattern.search(lowered):
                warnings.append(term)
        return warnings

    @staticmethod
    def _scan_compliance(
        analysis: ProductAnalysis,
        copy: CopyBlock,
        requirements: list[ImageRequirement],
        sku: str,
        listing: ListingData | None = None,
    ) -> None:
        """扫描 AI 生成的全文案，检查合规违禁词并记录日志。"""
        platform = _compliance_platform_key(listing)
        platform_label = "eBay" if platform == "ebay" else "亚马逊"
        text_fields: dict[str, str] = {}
        for name in ("function", "installation", "inspection", "maintenance", "compatibility", "oe_numbers", "quality"):
            val = getattr(analysis, name, "")
            if val:
                text_fields[f"analysis.{name}"] = str(val)
        for name in ("headline", "subheadline", "body"):
            val = getattr(copy, name, "")
            if val:
                text_fields[f"copy.{name}"] = str(val)
        for kw in copy.keywords:
            if kw:
                text_fields[f"copy.keyword:{kw}"] = str(kw)
        for req in requirements:
            if req.copy_text and req.copy_text not in (
                "Main image - white background (no text)",
                "Main image composite (no text)",
                "",
            ):
                text_fields[f"image[{req.index}].copy_text"] = str(req.copy_text)

        all_violations: dict[str, list[str]] = {}
        all_emissions: dict[str, list[str]] = {}

        for field_name, text in text_fields.items():
            _, violations = AiService._filter_compliance_violations(text, platform)
            if violations:
                all_violations[field_name] = violations
            if platform == "amazon":
                emissions = AiService._filter_compliance_emission_warnings(text)
                if emissions:
                    all_emissions[field_name] = emissions

        if all_violations:
            detail = "; ".join(
                f"{k}: {', '.join(v)}" for k, v in all_violations.items()
            )
            logger.warning(
                f"⚠ {platform_label}合规违禁词检测 SKU={sku} — 以下字段包含硬禁用词: {detail}"
            )
        if all_emissions:
            detail = "; ".join(
                f"{k}: {', '.join(v)}" for k, v in all_emissions.items()
            )
            logger.info(
                f"🔶 排放/气体相关词检测 SKU={sku} — 请运营核查竞品用法: {detail}"
            )

    # ── 合规文本自动清洗映射 ──
    _COMPLIANCE_REPLACEMENTS_SHARED: list[tuple[str, str]] = [
        (r"(?<!\w)100%\s*new\s+components?(?!\w)", "brand-new components"),
        (r"(?<!\w)100%\s*new(?!\w)", "brand-new"),
        (r"(?<!\w)100%\s*tested(?!\w)", "rigorously tested"),
        (r"(?<!\w)100%\s*satisfaction(?!\w)", "complete satisfaction"),
        (r"(?<!\w)100%\s*fitment(?!\w)", "precise fitment"),
        (r"(?<!\w)100%\s*guaranteed?(?!\w)", "rigorously tested"),
        (r"(?<!\w)100%\s*safe(?!\w)", "thoroughly tested"),
        (r"(?<!\w)quality\s+assurance(?!\w)", "quality control"),
        (r"(?<!\w)customer\s+assurance(?!\w)", "customer support"),
        (r"(?<!\w)brand\s+assurance(?!\w)", "brand commitment"),
        (r"(?<!\w)assurances?(?!\w)", "reliability"),
        (r"(?<!\w)guaranteed?(?!\w)", "reliable"),
        (r"(?<!\w)guarantees?(?!\w)", "commitments"),
        (r"(?<!\w)warranties?(?!\w)", "support coverage"),
        (r"(?<!\w)100%\s*coverage(?!\w)", "full coverage"),
        (r"(?<!\w)100%(?!\w)", "fully"),
        (r"(?<!\w)#1(?!\w)", "top-quality"),
        (r"(?<!\w)lowest\s+price(?!\w)", "competitive pricing"),
        (r"(?<!\w)cheapest(?!\w)", "value pricing"),
        (r"(?<!\w)free\s+shipping(?!\w)", "fast dispatch"),
        (r"(?<!\w)best(?!\w)", "premium"),
    ]
    _COMPLIANCE_REPLACEMENTS_AMAZON: list[tuple[str, str]] = [
        (r"(?<!\w)no\s+modifications?\s+needed(?!\w)", "straightforward installation"),
        (r"(?<!\w)without\s+modifications?(?!\w)", "as a direct fit"),
        (r"(?<!\w)modifications?(?!\w)", "adjustments"),
        (r"(?<!\w)remove\s+and\s+replace(?!\w)", "direct replacement"),
        (r"(?<!\w)delete(?!\w)", "clear"),
        (r"(?<!\w)bypass(?!\w)", "alternative"),
        (r"(?<!\w)override(?!\w)", "compatible with"),
        (r"(?<!\w)eliminate(?!\w)", "prevent"),
        (r"(?<!\w)disable(?!\w)", "manage"),
        (r"(?<!\w)tamper(?!\w)", "adjust"),
        (r"(?<!\w)defeat(?!\w)", "work with"),
    ]

    @classmethod
    def _compliance_replacements(cls, platform: str) -> list[tuple[str, str]]:
        replacements = list(cls._COMPLIANCE_REPLACEMENTS_SHARED)
        if platform == "amazon":
            replacements.extend(cls._COMPLIANCE_REPLACEMENTS_AMAZON)
        return replacements

    @classmethod
    def sanitize_compliance_text(cls, text: str, platform: str = "amazon") -> str:
        """将 AI 输出中的违禁词自动替换为安全表达。"""
        if not text:
            return text
        result = text
        for pattern, replacement in cls._compliance_replacements(platform):
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def sanitize_compliance_output(
        cls,
        analysis: ProductAnalysis,
        copy: CopyBlock,
        requirements: list[ImageRequirement],
        listing: ListingData | None = None,
    ) -> None:
        """对 AI 生成的全文案执行合规清洗（原地修改）。"""
        platform = _compliance_platform_key(listing)
        for name in ("function", "installation", "inspection", "maintenance", "compatibility", "oe_numbers", "quality"):
            val = getattr(analysis, name, "")
            if val:
                setattr(analysis, name, cls.sanitize_compliance_text(str(val), platform))
        for name in ("headline", "subheadline", "body"):
            val = getattr(copy, name, "")
            if val:
                setattr(copy, name, cls.sanitize_compliance_text(str(val), platform))
        copy.keywords = [cls.sanitize_compliance_text(kw, platform) for kw in copy.keywords]
        for req in requirements:
            if req.copy_text:
                req.copy_text = cls.sanitize_compliance_text(req.copy_text, platform)

    @staticmethod
    def _clip_line(text: str, limit: int = 110) -> str:
        line = re.sub(r"\s+", " ", str(text).strip())
        if len(line) <= limit:
            return line
        return line[: limit - 3].rstrip() + "..."

    def _bullet_lines_from_text(self, text: str, max_lines: int = 5) -> list[str]:
        if not text:
            return []
        lines: list[str] = []
        for chunk in re.split(r"[\n;]+", text):
            sentence = self._clip_line(chunk, 100)
            if sentence and sentence not in lines:
                lines.append(sentence)
            if len(lines) >= max_lines:
                break
        if not lines:
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                clipped = self._clip_line(sentence, 100)
                if clipped:
                    lines.append(clipped)
                if len(lines) >= max_lines:
                    break
        return lines[:max_lines]

    def _compat_bullet_lines(self, listing: ListingData, analysis: ProductAnalysis) -> list[str]:
        lines: list[str] = []
        for bullet in listing.bullet_points:
            if any(re.search(pattern, bullet.lower()) for pattern in COMPAT_PATTERNS):
                clipped = self._clip_line(bullet, 95)
                if clipped not in lines:
                    lines.append(clipped)
        if not lines:
            lines.extend(self._bullet_lines_from_text(analysis.compatibility, 4))
        if not lines and listing.title:
            lines.append(self._clip_line(listing.title, 95))
        return lines[:6]

    def _format_copy_block(self, headline: str, bullets: list[str], footer: str = "") -> str:
        parts = [headline.strip()]
        for bullet in bullets:
            text = bullet.strip()
            if not text:
                continue
            parts.append(f"• {text}" if not text.startswith("•") else text)
        if footer.strip():
            parts.append(footer.strip())
        return "\n".join(parts)

    def _build_rich_copy_text(
        self,
        theme: str,
        listing: ListingData,
        analysis: ProductAnalysis,
        copy: CopyBlock,
    ) -> str:
        oe = " / ".join(listing.oe_numbers) if listing.oe_numbers else ""
        bullets = listing.bullet_points

        if "功能" in theme:
            benefit_lines = self._bullet_lines_from_text(analysis.function, 4)
            if not benefit_lines:
                benefit_lines = [self._clip_line(b, 95) for b in bullets[:4] if b]
            if copy.headline and copy.headline not in benefit_lines:
                benefit_lines.insert(0, self._clip_line(copy.headline, 95))
            return self._format_copy_block("KEY BENEFITS", benefit_lines[:5])

        if "安装" in theme:
            steps = self._bullet_lines_from_text(analysis.installation, 5)
            if not steps:
                steps = [
                    "Direct bolt-on replacement — straightforward installation",
                    "Use standard hand tools; verify alignment before final torque",
                    "Test operation after installation",
                ]
            return self._format_copy_block("INSTALLATION GUIDE", steps)

        if "OE" in theme or "适配" in theme:
            return self._build_listing_fitment_oe_copy(listing)

        if "品质" in theme or "细节" in theme:
            quality_lines = self._bullet_lines_from_text(analysis.quality, 4)
            if not quality_lines:
                quality_lines = [self._clip_line(b, 95) for b in bullets if b][:4]
            return self._format_copy_block("PREMIUM QUALITY", quality_lines[:5])

        if "巡检" in theme or "故障" in theme or "症状" in theme:
            symptom_lines = self._bullet_lines_from_text(analysis.inspection, 5)
            if not symptom_lines:
                symptom_lines = [
                    "Inspect for cracks, wear, leaks, or abnormal noise",
                    "Replace when performance drops or fitment loosens",
                ]
            return self._format_copy_block("KNOW THE SIGNS", symptom_lines)

        if "维护" in theme or "寿命" in theme:
            care_lines = self._bullet_lines_from_text(analysis.maintenance, 5)
            if not care_lines:
                care_lines = [
                    "Avoid overload and harsh operating conditions",
                    "Perform periodic visual checks",
                    "Maintain proper torque to extend service life",
                ]
            return self._format_copy_block("EXTEND SERVICE LIFE", care_lines)

        fallback_lines = self._bullet_lines_from_text(copy.body or analysis.function, 4)
        if not fallback_lines and copy.subheadline:
            fallback_lines = [copy.subheadline]
        return self._format_copy_block("PRODUCT HIGHLIGHTS", fallback_lines[:4])

    @staticmethod
    def _build_category_context_text(
        listing: ListingData,
        product_info: dict[str, Any] | None = None,
    ) -> str:
        parts = [listing.title or "", listing.description or ""]
        parts.extend(listing.bullet_points or [])
        if product_info:
            parts.append(str(product_info.get("product_category", "") or ""))
            parts.append(str(product_info.get("product_name", "") or ""))
            parts.append(str(product_info.get("visual_appearance", "") or ""))
        return " ".join(p for p in parts if p).lower()

    @classmethod
    def match_category_display_hints(
        cls,
        listing: ListingData,
        product_info: dict[str, Any] | None = None,
    ) -> list[str]:
        text = cls._build_category_context_text(listing, product_info)
        if not text.strip():
            return []
        matched: list[str] = []
        seen: set[str] = set()
        is_window_regulator = any(
            kw in text
            for kw in (
                "window regulator", "power window regulator", "glass regulator",
                "玻璃升降", "升降器",
            )
        )
        for keywords, hint in CATEGORY_DISPLAY_RULES:
            if not any(kw in text for kw in keywords):
                continue
            if is_window_regulator and hint.startswith("电机类"):
                continue
            if hint not in seen:
                seen.add(hint)
                matched.append(hint)
        return matched

    @classmethod
    def format_category_display_hints(
        cls,
        listing: ListingData,
        product_info: dict[str, Any] | None = None,
    ) -> str:
        hints = cls.match_category_display_hints(listing, product_info)
        return " ".join(hints)

    @staticmethod
    def _link_scene_ordinal(scene_index: int, scene_link_sources: list[bool]) -> int:
        if scene_index < 0 or scene_index >= len(scene_link_sources):
            return 0
        if not scene_link_sources[scene_index]:
            return 0
        return sum(1 for flag in scene_link_sources[: scene_index + 1] if flag)

    def _append_design_request_extras(
        self,
        design_request: str,
        *,
        theme: str,
        idx: int,
        scene_image: str,
        scene_refs: list[str],
        scene_link_sources: list[bool] | None,
        category_hints: list[str],
        is_premium: bool,
        compliance_platform: str = "亚马逊",
    ) -> str:
        if idx <= 1 and not is_premium:
            return design_request

        extras: list[str] = []
        scene_link_sources = scene_link_sources or []
        if scene_image and scene_refs:
            try:
                scene_idx = scene_refs.index(scene_image)
            except ValueError:
                scene_idx = -1
            if scene_idx >= 0 and scene_idx < len(scene_link_sources) and scene_link_sources[scene_idx]:
                ordinal = self._link_scene_ordinal(scene_idx, scene_link_sources)
                extras.append(
                    f"参考图要求：依次参考链接获取的场景图第 {ordinal} 张"
                    f"（当前分配的场景参考图），制作一张内容构图相近的图片"
                    f"（场景、产品位置、拍摄角度尽量一致）；"
                    f"图片文案须符合{compliance_platform}合规，禁止出现违禁词。"
                )

        if category_hints and idx > 1:
            extras.append("产品展示重点：" + " ".join(category_hints))

        if not extras:
            return design_request

        base = (design_request or "").strip()
        start_no = 1
        if base:
            numbered = re.findall(r"^(\d+)\.", base, flags=re.MULTILINE)
            if numbered:
                start_no = max(int(n) for n in numbered) + 1
        extra_lines = [
            f"{start_no + offset}. {line}"
            for offset, line in enumerate(extras)
        ]
        if base:
            return base + "\n" + "\n".join(extra_lines)
        return "\n".join(extra_lines)

    def _build_concise_design_request(
        self,
        theme: str,
        copy_text: str,
        idx: int,
    ) -> str:
        return self._build_design_request_from_copy(theme, copy_text, idx)

    def _condense_design_request(self, text: str) -> str:
        cleaned = str(text).replace("\\n", "\n").strip()
        if not cleaned:
            return cleaned

        filler_patterns = (
            r"整体风格[：:].*?(?=。|$)",
            r"转化目标[：:].*?(?=。|$)",
            r"符合亚马逊.*?审美。?",
            r"专业可信。?",
            r"层次清晰.*?。",
            r"建立购买信心。?",
        )
        for pattern in filler_patterns:
            cleaned = re.sub(pattern, "", cleaned)

        raw_lines: list[str] = []
        for chunk in re.split(r"[\n。]+", cleaned):
            line = self._strip_design_request_number_prefix(chunk)
            if len(line) < 4:
                continue
            if any(skip in line for skip in ("整体风格", "转化目标", "购买信心", "专业可信", "素材")):
                continue
            raw_lines.append(line)
            if len(raw_lines) >= 6:
                break

        if not raw_lines:
            return cleaned[:280]

        comp_body = ""
        layout_body = ""
        extras: list[str] = []
        for line in raw_lines:
            if "构图" in line and not comp_body:
                comp_body = line.split("：", 1)[-1].strip() if "：" in line else line
            elif ("排版" in line or "文案" in line) and not layout_body:
                layout_body = line.split("：", 1)[-1].strip() if "：" in line else line
            else:
                extras.append(line)

        if not comp_body and raw_lines:
            comp_body = raw_lines[0]
        if not layout_body and len(raw_lines) > 1:
            layout_body = raw_lines[1]

        lines: list[str] = []
        if comp_body:
            lines.append(f"1. 构图：{comp_body}" if not comp_body.startswith("构图") else f"1. {comp_body}")
        if layout_body:
            prefix = "2. 文案排版：" if "排版" not in layout_body else "2. "
            lines.append(
                f"{prefix}{layout_body}" if layout_body.startswith("文案排版") else f"2. 文案排版：{layout_body}"
            )
        for extra_idx, extra in enumerate(extras[:2], start=len(lines) + 1):
            lines.append(f"{extra_idx}. {extra}")

        return "\n".join(lines[:4])

    async def _finalize_image_references(
        self,
        requirements: list[ImageRequirement],
        listing: ListingData,
        analysis: ProductAnalysis,
        main_image: str,
        detail_refs: list[str],
        scene_refs: list[str],
        has_operator_references: bool,
        sku: str,
        main_image_path: Path | None = None,
        is_premium: bool = False,
        scene_link_sources: list[bool] | None = None,
    ) -> dict[str, Path]:
        """最终整理各需求的参考图（已由 _build_requirements_from_items 分配完，这里只做清理）"""
        from backend.image_sop.services.main_image_edit_service import MainImageEditService

        main_editor = MainImageEditService(self.settings)
        extra_files: dict[str, Path] = {}
        product_info = getattr(analysis, "_product_info", None)
        if not isinstance(product_info, dict):
            product_info = None
        category_hints = self.match_category_display_hints(listing, product_info)
        link_flags = scene_link_sources or [False] * len(scene_refs)
        compliance_platform = (
            "eBay" if "ebay" in (listing.data_source or "").lower() else "亚马逊"
        )

        for req in requirements:
            req.main_image = main_image
            if not hasattr(req, 'reference_images') or req.reference_images is None:
                req.reference_images = []

            if not is_premium and req.index == 1:
                if self._is_ebay_listing(listing):
                    hero = self._ebay_hero_allocation(main_image, scene_refs, [0])
                    req.main_image = main_image
                    req.reference_image = hero["ref_primary"]
                    req.detail_image = hero["detail_img"]
                    req.scene_image = hero["scene_img"]
                    req.reference_images = hero["ref_images"]
                    req.reference_source = hero["reference_source"]
                    req.copy_text = hero["copy_text"]
                    req.design_request = self._append_ebay_hero_reference_requirement(
                        hero["design_request"],
                        hero["scene_img"],
                        link_flags,
                    )
                    if req.theme in ("", "主图"):
                        req.theme = hero["theme"]
                    logger.info(
                        f"[IMAGE-FINAL] idx=1 theme={req.theme} source={req.reference_source} "
                        f"ebay_hero main={bool(main_image)} scene={bool(hero['scene_img'])}"
                    )
                    continue
                # 亚马逊标准模式第1张始终是白底主图
                req.reference_image = main_image
                req.reference_images = [main_image]
                req.reference_source = "main"
                req.detail_image = ""
                req.scene_image = ""
                req.design_request = self._build_concise_design_request(req.theme, req.copy_text, req.index)
                continue

            # 后续行/高级A+：保留 AI 已分配的参考图，不强制主图
            # 不再用主图兜底。如果没有参考图（场景池和细节池都为空），才尝试主图编辑变体
            if not req.reference_images and main_image_path and main_editor.should_edit(req.theme, req.index):
                path, url, edit_desc = main_editor.create_detail_variant(
                    main_image_path, req.theme, req.index, sku
                )
                if path and url:
                    if path.name not in extra_files:
                        extra_files[path.name] = path
                    req.reference_images.append(url)
                    req.detail_image = url
                    req.reference_source = "main_edit"

            req.reference_image = req.reference_images[0] if req.reference_images else ""
            req.reference_search_query = ""
            if self._is_fitment_oe_theme(req.theme, is_premium=is_premium):
                req.design_request = self._build_fitment_oe_design_request(
                    req.copy_text, req.index
                )
            elif not is_premium:
                if not (req.design_request or "").strip():
                    req.design_request = self._build_concise_design_request(
                        req.theme, req.copy_text, req.index
                    )
                else:
                    req.design_request = self._condense_design_request(req.design_request)
            else:
                if (req.design_request or "").strip():
                    req.design_request = self._condense_design_request(req.design_request)
                elif not (req.design_request or "").strip():
                    req.design_request = self._build_concise_design_request(
                        req.theme, req.copy_text, req.index
                    )
            req.design_request = self._append_design_request_extras(
                req.design_request,
                theme=req.theme,
                idx=req.index,
                scene_image=req.scene_image or "",
                scene_refs=scene_refs,
                scene_link_sources=link_flags,
                category_hints=category_hints,
                is_premium=is_premium,
                compliance_platform=compliance_platform,
            )

            logger.info(
                f"[IMAGE-FINAL] idx={req.index} theme={req.theme} source={req.reference_source} "
                f"detail_img={req.detail_image} scene_img={req.scene_image} "
                f"refs={req.reference_images}"
            )

        return extra_files

    def _normalize_image_size(self, size: str) -> str:
        if not size:
            return self.settings.sop_image_size
        normalized = size.lower().replace("x", "*").replace(" ", "")
        if normalized in {"1600*1600", "2000*2000"}:
            return self.settings.sop_image_size
        return size or self.settings.sop_image_size

    @staticmethod
    def _safe_sku(sku: str) -> str:
        return re.sub(r"[^\w\-]+", "_", sku)[:40] or "sku"

    @staticmethod
    def _extract_product_keywords(text: str) -> list[str]:
        """从文本提取产品核心关键词，过滤泛词。"""
        stop_words = {
            "compatible", "with", "for", "fits", "replacement", "oem", "new",
            "brand", "quality", "direct", "fit", "and", "the", "part",
            "high", "free", "set", "kit", "pack", "pair", "x", "mm", "inch",
        }
        parts: list[str] = []
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-/]{2,}", text):
            t = token.lower()
            if len(token) < 20 and t not in stop_words and not t.isdigit():
                parts.append(token)
        return parts

    @staticmethod
    def _extract_vehicles(text: str, max_vehicles: int = 3) -> list[str]:
        """提取车型品牌+型号，支持汽车、摩托、PWC、ATV、农机等。"""
        brand_pattern = (
            r"\b(?:"
            # Cars / SUVs / Trucks
            r"BMW|Audi|Mercedes[-\s]?Benz|Toyota|Honda|Ford|Chevrolet|Nissan|"
            r"Volkswagen|VW|Lexus|Hyundai|Kia|Mazda|Subaru|Jeep|Dodge|Ram|GMC|Cadillac|"
            r"Volvo|Porsche|Mini|Buick|Chrysler|Acura|Infiniti|Lincoln|Mitsubishi|Fiat|"
            r"Jaguar|Land\s*Rover|Tesla|Suzuki|Renault|Peugeot|Citroen|Opel|Seat|Skoda|"
            r"Ferrari|Lamborghini|Maserati|Bentley|Rolls\s*Royce|Alfa\s*Romeo|"
            # Marine / PWC
            r"Sea[-\s]?Doo|SeaDoo|Yamaha\s*WaveRunner|WaveRunner|Kawasaki\s*Jet\s*Ski|Jet\s*Ski|"
            r"Mercury\s*Marine|Mercury|Mariner|Evinrude|Johnson|Tohatsu|Force|OMC|"
            r"Honda\s*Marine|Suzuki\s*Marine|Yamaha\s*Outboard|"
            # Motorcycle / ATV / UTV / Powersports
            r"Harley[-\s]?Davidson|Ducati|KTM|Aprilia|Triumph|Indian|Can[-\s]?Am|BRP|Polaris|"
            r"Arctic\s*Cat|Ski[-\s]?Doo|Honda|Yamaha|Kawasaki|Suzuki|"
            # Agriculture / Heavy equipment
            r"John\s*Deere|Kubota|Bobcat|New\s*Holland|Case\s*IH|Mahindra|Yanmar|"
            r"Caterpillar|CAT|Komatsu|JohnDeere"
            r")\b"
            r"(?:\s+(?:[A-Z][A-Za-z0-9\-]{1,10}|[0-9]{1,3}[A-Z]{1,2})\b){0,3}"
        )
        results: list[str] = []
        seen: set[str] = set()
        for match in re.finditer(brand_pattern, text, re.I):
            v = match.group(0).strip()
            key = re.sub(r"\s+", " ", v).lower()
            if key not in seen:
                seen.add(key)
                results.append(v)
        return results[:max_vehicles]

    @staticmethod
    def _extract_year_ranges(text: str) -> list[str]:
        """提取年份范围，如 2009-2020、2009 to 2020、2010-2015。"""
        pattern = r"\b(?:19|20)\d{2}\s*(?:[-–—]|\s+to\s+)\s*(?:19|20)\d{2}\b"
        return re.findall(pattern, text, re.I)

    @staticmethod
    def _extract_engines(text: str) -> list[str]:
        """提取发动机型号。"""
        pattern = (
            r"\b(?:N20|N26|N52|N54|N55|B48|B58|S55|S63|M54|M57|N57|N63|"
            r"2\.0L|3\.0L|4\.0L|1\.8T|2\.0T|3\.5L|5\.0L|5\.7L|6\.2L|6\.7L|"
            r"V6|V8|V10|V12|L4|L6|LFX|L83|L86|L8T|LY6|"
            r"EcoBoost|Coyote|Hemi|Pentastar|Vortec|Duramax|Powerstroke|Cummins|"
            r"TSI|TDI|FSI|TFSI|CDI|BlueTEC|SkyActiv|i-VTEC|Earth\s*Dreams|"
            r"MultiAir|TwinPower|BiTurbo|Turbo|Supercharged)\b"
        )
        return re.findall(pattern, text, re.I)

    @staticmethod
    def _vehicle_install_context(vehicle: str) -> str:
        """根据车型返回合适的安装位置/场景词。"""
        v = vehicle.lower()
        # 个人摩托艇 (PWC) — 不是普通船只
        if any(x in v for x in ("sea-doo", "seadoo", "waverunner", "wave runner", "jet ski", "pwc")):
            return "PWC engine compartment installed"
        # 船外机 / 船用发动机
        if any(x in v for x in ("outboard", "marine", "mercury marine", "yamaha outboard", "honda marine", "suzuki marine")):
            return "outboard engine installed"
        # 摩托/ATV/UTV/农机
        if any(x in v for x in ("atv", "utv", "motorcycle", "quad", "dirt bike", "polaris", "can-am", "brp")):
            return "engine installed"
        return "engine bay installed"

    @staticmethod
    def _extract_material(text: str) -> str:
        """提取材质关键词。"""
        materials = {
            "aluminum": "aluminum", "aluminium": "aluminum",
            "stainless steel": "stainless steel", "steel": "steel",
            "rubber": "rubber", "silicone": "silicone",
            "carbon fiber": "carbon fiber", "carbon": "carbon fiber",
            "plastic": "plastic", "nylon": "nylon",
            "copper": "copper", "brass": "brass",
            "cast iron": "cast iron", "iron": "iron",
            "leather": "leather", "ceramic": "ceramic",
        }
        t = text.lower()
        for key, val in materials.items():
            if key in t:
                return val
        return ""

    @staticmethod
    def _ensure_search_query_has_vehicle(
        query: str,
        theme: str,
        listing: ListingData,
        analysis: ProductAnalysis | None,
        copy_text: str,
    ) -> str:
        """确保图片搜索词包含 listing/copy 中提到的具体车型。

        如果 listing 里能提取到车型，但 AI 生成的 query 里一个车型都没有，
        说明 AI 没有按文案/产品信息搜图，此时用默认构建的精准搜索词替换。
        同时利用产品深度分析中的信息来补充车辆提取。
        """
        # 主图/品质细节图不需要车型场景
        if theme in ("主图", "品质细节") or "品质" in theme or "细节" in theme:
            return query
        if not query:
            return AiService._build_default_search_query(theme, listing, analysis, copy_text)

        # ── 合并文本来源（含产品深度分析结果） ──
        text_parts = [
            listing.title or "",
            listing.description or "",
            *(listing.bullet_points or []),
            copy_text or "",
            (analysis.compatibility or "") if analysis else "",
        ]
        # 加入产品深度分析中的核心特征和典型场景，辅助车型提取
        if analysis is not None:
            product_info = getattr(analysis, '_product_info', None) or {}
            for feat in product_info.get("core_features", []):
                if feat:
                    text_parts.append(feat)
            usage = str(product_info.get("typical_usage_scene", "")).strip()
            if usage:
                text_parts.append(usage)
        all_text = " ".join(text_parts)

        vehicles = AiService._extract_vehicles(all_text, max_vehicles=5)
        if not vehicles:
            return query

        ql = query.lower()
        # 只要 query 包含任一车型核心词即可
        has_any_vehicle = any(
            re.sub(r"\s+", " ", v).lower().strip() in ql
            or v.lower().split()[0] in ql  # 至少包含品牌
            for v in vehicles
        )
        if has_any_vehicle:
            return query

        # AI 漏了车型，使用默认构建词（它会强制带上车型 + engine bay/install context）
        default_query = AiService._build_default_search_query(theme, listing, analysis, copy_text)
        logger.info(
            f"img 搜索词缺少车型，从 AI='{query[:80]}' 替换为 default='{default_query[:80]}'"
        )
        return default_query

    @staticmethod
    def _sanitize_search_query(query: str, theme: str, listing: ListingData, analysis: ProductAnalysis | None = None) -> str:
        """对 AI 生成的图片搜索词做后处理，提升搜索结果相关性。

        利用 listing 数据 + 产品深度分析来判断车辆类型并补充上下文关键词。
        """
        if not query:
            return query
        q = query
        ql = q.lower()

        # 合并文本用于判断车辆类型（含产品深度分析）
        text_sources = [listing.title or listing.sku]
        if listing.description:
            text_sources.append(listing.description)
        for bp in (listing.bullet_points or []):
            text_sources.append(bp)
        # 加入产品深度分析中的类型判断
        if analysis is not None:
            product_info = getattr(analysis, '_product_info', None) or {}
            analyzed_type = str(product_info.get("product_type", "")).strip().lower()
            for feat in product_info.get("core_features", []):
                if feat:
                    text_sources.append(feat)
            usage = str(product_info.get("typical_usage_scene", "")).strip()
            if usage:
                text_sources.append(usage)
        else:
            analyzed_type = ""
        all_text = " ".join(text_sources)

        vehicles = AiService._extract_vehicles(all_text, max_vehicles=1)
        vehicle = vehicles[0] if vehicles else ""

        # 优先用产品深度分析的类型判断
        if analyzed_type:
            is_automotive = "automotive" in analyzed_type or "car" in analyzed_type
        else:
            is_automotive = bool(vehicle) and not any(
                x in vehicle.lower()
                for x in ("sea-doo", "seadoo", "waverunner", "wave runner", "jet ski", "pwc",
                          "outboard", "marine", "atv", "utv", "motorcycle", "quad", "dirt bike")
            )

        # 如果 listing 有具体车型，但 query 里没有，强制补上（防止 AI 漏掉车型）
        if vehicle and vehicle.lower() not in ql and vehicle.lower().split()[0] not in ql:
            q = f"{vehicle} {q}"
            ql = q.lower()

        # 汽车类场景类搜索词，强制包含 engine bay / engine compartment，避免返回整车外观
        # 物品图主题（品质/细节/巡检/故障/症状）不追加 engine_bay，聚焦产品本身
        _ITEM_IMAGE_THEMES = {"品质", "细节", "巡检", "故障", "症状"}
        if is_automotive and theme not in ("主图", "品质细节") and not any(t in theme for t in _ITEM_IMAGE_THEMES):
            if not any(x in ql for x in ("engine bay", "engine compartment", "under hood", "under the hood")):
                if vehicle:
                    q = q.replace(vehicle, f"{vehicle} engine bay", 1)
                else:
                    q = f"{q} engine bay"

        # 过滤掉会导致整车外观/无关场景的词
        for bad in ("full car exterior", "car profile", "side view of car", "car parked on street"):
            q = re.sub(re.escape(bad), "", q, flags=re.I)

        return " ".join(q.split())

    @staticmethod
    def _build_default_search_query(
        theme: str,
        listing: ListingData,
        analysis: ProductAnalysis | None = None,
        copy_text: str = "",
    ) -> str:
        """根据主题 + 产品信息 + 文案构建精准图片搜索词。

        会综合 title、description、bullet_points、ProductAnalysis.compatibility、
        当前文案内容，以及产品深度分析结果来抽取车型、发动机、材质等信息。
        优先使用产品深度分析中的 product_name, image_search_keywords, install_location 等。
        """
        title = listing.title or listing.sku

        # ── 提取产品深度分析结果 ──
        product_info: dict[str, Any] = {}
        if analysis is not None:
            product_info = getattr(analysis, '_product_info', None) or {}

        # 优先使用深度分析中的精准产品名
        analyzed_product_name = str(product_info.get("product_name", "")).strip()
        analyzed_category = str(product_info.get("product_category", "")).strip()
        analyzed_install_location = str(product_info.get("install_location", "")).strip()
        analyzed_search_keywords = product_info.get("image_search_keywords", [])

        # ── 合并所有文本来源 ──
        text_sources = [title]
        if listing.description:
            text_sources.append(listing.description)
        for bp in (listing.bullet_points or []):
            text_sources.append(bp)
        if copy_text:
            text_sources.append(copy_text)
        # 加入核心特征文本
        for feat in product_info.get("core_features", []):
            if feat:
                text_sources.append(feat)
        # 加入典型使用场景
        usage = str(product_info.get("typical_usage_scene", "")).strip()
        if usage:
            text_sources.append(usage)
        all_text = " ".join(text_sources)

        # 额外加入 ProductAnalysis 的兼容性段落（车型信息通常在这里）
        if analysis:
            compat = (analysis.compatibility or "")[:500]
            if compat:
                all_text += " " + compat

        # ── 提取产品关键词 ──
        # 优先使用深度分析的精准产品名来提取关键词，更准确
        primary_title = analyzed_product_name or title
        product_keywords = AiService._extract_product_keywords(primary_title)
        # 如果分析出的品类名不在关键词中，补上
        if analyzed_category and analyzed_category.lower() not in " ".join(product_keywords).lower():
            product_keywords.insert(0, analyzed_category)

        # ── 提取车型 ──
        vehicles = AiService._extract_vehicles(all_text, max_vehicles=3)
        vehicle = vehicles[0] if vehicles else ""
        # 合并年份范围
        year_ranges = AiService._extract_year_ranges(all_text)
        if vehicle and year_ranges:
            vehicle = f"{vehicle} {year_ranges[0]}"

        # 过滤产品关键词中已被车型覆盖的品牌/年份，避免搜索词重复
        vehicle_lower = vehicle.lower()
        product_keywords = [
            k for k in product_keywords
            if k.lower() not in vehicle_lower and not any(k.lower() in y.lower() for y in year_ranges)
        ]
        product = " ".join(product_keywords[:5])

        # ── 提取发动机 ──
        engines = AiService._extract_engines(all_text)
        engine = engines[0] if engines else ""

        # ── 提取 OE 号 ──
        oe = listing.oe_numbers[0] if listing.oe_numbers else ""

        # ── 提取材质 ──
        material = AiService._extract_material(copy_text or all_text)

        # ── 按主题构建搜索词（场景/物品类和产品细节类策略不同） ──
        def _safe(*parts: str) -> str:
            return " ".join(p for p in parts if p).strip()

        # 根据车型确定安装位置词， PWC / marine outboard / ATV / motorcycle / 汽车不同
        # 优先使用产品深度分析中的 install_location
        if analyzed_install_location:
            if "engine bay" in analyzed_install_location.lower() or "engine compartment" in analyzed_install_location.lower():
                install_context = "engine bay installed"
            elif "undercarriage" in analyzed_install_location.lower() or "wheel" in analyzed_install_location.lower():
                install_context = "installed undercarriage"
            elif "PWC" in analyzed_install_location or "personal watercraft" in analyzed_install_location.lower():
                install_context = "PWC engine compartment installed"
            else:
                install_context = "installed"
        else:
            install_context = AiService._vehicle_install_context(vehicle) if vehicle else "engine bay installed"

        # 通用质量后缀：引导搜索引擎返回实拍照片
        quality_tail = "real photo"

        def _vehicle_type_qualifier(v: str) -> str:
            """返回产品类型修饰词，用于细节/兜底搜索。"""
            vl = v.lower()
            if any(x in vl for x in ("sea-doo", "seadoo", "waverunner", "wave runner", "jet ski", "pwc")):
                return "PWC marine"
            if any(x in vl for x in ("outboard", "marine")):
                return "marine outboard"
            if any(x in vl for x in ("atv", "utv", "motorcycle", "quad", "dirt bike")):
                return "powersports"
            return "automotive"

        # 优先用深度分析的类型判断
        analyzed_type = str(product_info.get("product_type", "")).strip().lower()
        if analyzed_type:
            if "pwc" in analyzed_type or "personal watercraft" in analyzed_type:
                type_qualifier = "PWC marine"
            elif "marine" in analyzed_type or "outboard" in analyzed_type:
                type_qualifier = "marine outboard"
            elif "motorcycle" in analyzed_type or "atv" in analyzed_type or "powersports" in analyzed_type:
                type_qualifier = "powersports"
            elif "automotive" in analyzed_type or "car" in analyzed_type:
                type_qualifier = "automotive"
            else:
                type_qualifier = _vehicle_type_qualifier(vehicle) if vehicle else "automotive"
        else:
            type_qualifier = _vehicle_type_qualifier(vehicle) if vehicle else "automotive"
        is_automotive = type_qualifier == "automotive"

        def _ensure_engine_bay(q: str) -> str:
            """汽车类场景搜索词若缺少 engine bay / engine compartment，则补上，避免返回整车外观。"""
            if not is_automotive:
                return q
            ql = q.lower()
            if any(x in ql for x in ("engine bay", "engine compartment", "under hood", "under the hood")):
                return q
            # 在 vehicle 后追加 engine bay（若已有 vehicle）或在末尾追加
            if vehicle:
                return q.replace(vehicle, f"{vehicle} engine bay", 1)
            return _safe(q, "engine bay")

        if "功能" in theme:
            # 功能说明图：显示产品安装在机舱内的位置和功能
            return _ensure_engine_bay(_safe(product, vehicle, engine, install_context, quality_tail))
        if "安装" in theme:
            # 安装图：展示产品安装过程
            return _ensure_engine_bay(_safe("installing", product, vehicle, engine, install_context, quality_tail))
        if "场景" in theme or "使用场景" in theme:
            # 场景图：必须是产品实际安装/使用场景，不能是 generic 车辆图
            if vehicle:
                return _ensure_engine_bay(_safe(product, vehicle, install_context, quality_tail))
            return _ensure_engine_bay(_safe(product, install_context, "real vehicle", quality_tail))
        if "OE" in theme or "适配" in theme:
            # 适配图：展示产品适配的车型机舱
            if vehicles and len(vehicles) > 1:
                # 如果两辆车是同一品牌，只保留第一辆避免重复
                if vehicles[0].lower().split()[0] == vehicles[1].lower().split()[0]:
                    return _ensure_engine_bay(_safe(product, vehicles[0], install_context, "compatible", quality_tail))
                return _ensure_engine_bay(_safe(product, vehicles[0], vehicles[1], install_context, "compatible", quality_tail))
            if vehicle:
                return _ensure_engine_bay(_safe(product, vehicle, engine, install_context, quality_tail))
            if oe:
                return _ensure_engine_bay(_safe(product, oe, install_context, quality_tail))
            return _ensure_engine_bay(_safe(product, install_context, "compatibility", quality_tail))
        if "品质" in theme or "细节" in theme:
            # 物品图：搜索产品本身的特写，强调独立的产品照片而非安装场景
            # 使用 isolated / product photo / auto part 等关键词引导搜索引擎返回产品目录式图片
            mat = material or ""
            return _safe(product, f"{type_qualifier} part", mat, "isolated product detail closeup no background", quality_tail)
        if "巡检" in theme or "故障" in theme or "症状" in theme:
            # 物品图（故障）：搜索产品磨损/损坏的实物特写照片
            # 不追加 engine_bay，让搜索聚焦在损坏部件本身而非安装场景
            q = _safe(product, f"{type_qualifier} part", "worn damaged defective closeup detail", quality_tail)
            if vehicle:
                q = f"{vehicle} {q}"
            return q
        if "维护" in theme or "寿命" in theme:
            # 维护图：产品在对应车型上的维护场景（汽车类限定发动机舱）
            base = vehicle or "vehicle"
            q = _safe(base, "engine", product, "maintenance inspection", quality_tail)
            return _ensure_engine_bay(q)
        # 默认兜底：如果深度分析提供了精准搜索关键词，尝试使用第一个
        if analyzed_search_keywords:
            fallback_kw = analyzed_search_keywords[0]
            if "品质" not in theme and "细节" not in theme:
                return _ensure_engine_bay(_safe(fallback_kw, quality_tail))
            return _safe(fallback_kw, quality_tail)
        return _ensure_engine_bay(_safe(product, type_qualifier, vehicle, install_context, quality_tail)).strip() or _safe(product, f"{type_qualifier} part", quality_tail)

    @staticmethod
    def _pick_reference(index: int, main_image: str, reference_images: list[str]) -> str:
        if index == 1:
            return main_image
        if not reference_images:
            return main_image
        return reference_images[(index - 2) % len(reference_images)]

    @staticmethod
    def _infer_reference_source(
        theme: str,
        detail_offset: int = 0,
        scene_offset: int = 0,
        detail_total: int = 0,
        scene_total: int = 0,
    ) -> str:
        """[已废弃] _build_requirements_from_items 直接分配，不再调用此方法。
        保留供可能的外部调用或回退场景使用，内部逻辑未更新（仍为旧版一一对应策略）。
        """
        detail_remaining = max(0, detail_total - detail_offset)

        if "主图" in theme:
            return "main"

        is_scene_theme = any(t in theme for t in ("安装指南", "安装", "适配与OE号", "OE", "适配", "维护与延长寿命", "维护", "寿命", "使用场景", "场景图"))
        is_detail_theme = any(t in theme for t in ("核心功能", "功能", "品质细节", "品质", "细节", "巡检", "故障", "症状"))

        if is_scene_theme:
            if scene_total > 0:
                return "scene"
            if detail_remaining > 0:
                return "detail"
            return "main"

        if is_detail_theme:
            if detail_remaining > 0:
                return "detail"
            # 细节图耗尽后不给图，不用场景图或主图兜底
            return "detail"

        # 兜底：先耗细节图，再循环场景图
        if detail_remaining > 0:
            return "detail"
        if scene_total > 0:
            return "scene"
        return "main"

    @staticmethod
    def _pick_references_by_source(
        reference_source: str,
        main_image: str,
        detail_references: list[str],
        scene_references: list[str],
        detail_offset: int = 0,
        scene_offset: int = 0,
    ) -> tuple[str, str, str, list[str]]:
        """[已废弃] _build_requirements_from_items 直接分配，不再调用此方法。
        保留供可能的外部调用或回退场景使用，内部逻辑未更新（detail 仍为一对一耗尽策略）。
        """
        def _safe_pick(pool: list[str], offset: int, cycle: bool = False) -> str:
            if not pool:
                return ""
            if cycle:
                return pool[offset % len(pool)]
            if offset >= len(pool):
                return ""
            return pool[offset]

        if reference_source == "main":
            return ("", "", main_image, [main_image])

        if reference_source == "detail":
            primary = _safe_pick(detail_references, detail_offset)
            all_refs = [primary] if primary else []
            return (primary, "", primary, all_refs)

        if reference_source == "scene":
            primary = _safe_pick(scene_references, scene_offset, cycle=True)
            all_refs = [primary] if primary else []
            return ("", primary, primary, all_refs)

        if reference_source == "composite":
            detail_img = _safe_pick(detail_references, detail_offset)
            scene_img = _safe_pick(scene_references, scene_offset, cycle=True)
            all_refs: list[str] = []
            primary = ""
            if detail_img:
                all_refs.append(detail_img)
                primary = detail_img
            if scene_img:
                all_refs.append(scene_img)
                if not primary:
                    primary = scene_img
            return (detail_img, scene_img, primary, all_refs)

        # 默认兜底：合并两池（不兜底主图）
        all_refs = list(detail_references) + list(scene_references)
        primary = all_refs[0] if all_refs else ""
        return ("", "", primary, all_refs)
