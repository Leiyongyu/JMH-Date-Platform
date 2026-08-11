from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import httpx

from backend.config import settings
from backend.repositories import amz_sop_repository as repo


BIG_CATEGORIES = (
    "补偿", "客户自身原因", "物流商问题", "不适配", "产品质量问题",
    "国内物流部", "其他", "供应商加强包装", "海外仓问题", "退货已损坏",
)

STATUS_TRANSLATIONS = {
    "approved": "已批准",
    "pending": "待处理",
    "completed": "已完成",
    "rejected": "已拒绝",
    "cancelled": "已取消",
    "canceled": "已取消",
    "unitreturnedtostock": "退货已重新入库",
    "unitreturnedtoinventory": "退货已退回库存",
}

ATTRIBUTE_TRANSLATIONS = {
    "sellable": "可售",
    "customer_damaged": "客户损坏",
    "defective": "商品有缺陷",
    "carrier_damaged": "承运商损坏",
    "warehouse_damaged": "仓库损坏",
    "expired": "已过期",
}

REASON_TRANSLATIONS = {
    "cr-ordered-wrong-item": "客户订错商品",
    "ordered_wrong_item": "客户订错商品",
    "no_longer_needed": "客户不再需要",
    "not_as_described": "商品与描述不符",
    "defective": "商品有缺陷或无法使用",
    "damaged": "商品到货破损",
    "missing_parts": "商品缺少配件",
    "wrong_item": "收到错误商品",
    "incompatible": "商品不适配",
    "not_compatible": "商品不适配",
    "part_not_compatible": "零件不适配",
    "poor_fit": "尺寸或安装不适配",
    "apparel_too_small": "尺寸过小",
    "apparel_too_large": "尺寸过大",
    "delivery_too_late": "物流送达延迟",
}

DETERMINISTIC_REASON_RULES = {
    "incompatible": ("不适配", "产品不适配"),
    "not_compatible": ("不适配", "产品不适配"),
    "part_not_compatible": ("不适配", "产品不适配"),
    "poor_fit": ("不适配", "产品不适配"),
    "apparel_too_small": ("不适配", "产品不适配"),
    "apparel_too_large": ("不适配", "产品不适配"),
    "not_as_described": ("不适配", "listing货描不符"),
}

BUYER_NOTE_TRANSLATIONS = {
    "passt nicht": "不适配",
    "nicht passend": "不适配",
}


def classification_hash(
    row: dict[str, Any], rule_version: str, platform: str = "AMZ"
) -> str:
    normalized = "|".join(
        _normalize(row.get(key))
        for key in ("after_reason", "return_status", "inventory_attributes", "buyers_note")
    )
    platform_key = str(platform or "AMZ").strip().upper()
    payload = f"{rule_version}|{settings.deepseek_model}|{platform_key}-sop-v3|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_rows(
    rows: list[dict[str, Any]], platform: str = "AMZ"
) -> dict[str, dict[str, Any]]:
    rules = repo.category_rules()
    rule_version = max(
        (str(row.get("rule_version") or "") for row in rules),
        default="2026-08-07",
    )
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = classification_hash(row, rule_version, platform)
        row["classification_hash"] = key
        unique.setdefault(key, row)

    cached = repo.cached_classifications(list(unique))
    missing = [row for key, row in unique.items() if key not in cached]
    created: list[dict[str, Any]] = []
    for index in range(0, len(missing), 15):
        batch = missing[index:index + 15]
        deterministic: dict[str, dict[str, Any]] = {}
        ai_candidates: list[dict[str, Any]] = []
        for row in batch:
            result = _fallback(row, rule_version)
            if result["classify_method"] == "rule":
                deterministic[row["classification_hash"]] = result
            else:
                ai_candidates.append(row)
        ai_results = _deepseek_batch(ai_candidates, rules, rule_version, platform)
        for row in batch:
            key = row["classification_hash"]
            result = deterministic.get(key) or ai_results.get(key) or _fallback(row, rule_version)
            created.append(result)
            cached[key] = result
    repo.upsert_classification_cache(created)
    return cached


def _deepseek_batch(
    rows: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    rule_version: str,
    platform: str = "AMZ",
) -> dict[str, dict[str, Any]]:
    if not settings.deepseek_api_key.strip() or not rows:
        return {}
    categories = [
        {
            "big": rule["big_category"],
            "small": rule["small_category"],
            "description": rule.get("classification_description") or "",
        }
        for rule in rules
    ]
    items = [
        {
            "id": row["classification_hash"],
            "after_reason": _limited(row.get("after_reason")),
            "return_status": _limited(row.get("return_status"), 300),
            "inventory_attributes": _limited(row.get("inventory_attributes"), 300),
            "buyers_note": _limited(row.get("buyers_note")),
        }
        for row in rows
    ]
    system = (
        f"你是{str(platform or 'AMZ').upper()}平台售后数据清洗分类器。必须返回合法json对象，不要Markdown。"
        "结合四个字段翻译成准确简洁的中文，并严格从提供的分类表选择一组大类和小类。"
        "大类只能是：" + "、".join(BIG_CATEGORIES) + "。"
        "没有可靠判定依据时必须选择大类‘其他’、小类‘其他’，禁止留空或编造。"
        "返回格式示例：{\"items\":[{\"id\":\"...\",\"after_reason_zh\":\"\","
        "\"return_status_zh\":\"\",\"inventory_attributes_zh\":\"\","
        "\"buyers_note_zh\":\"\",\"big_category\":\"其他\","
        "\"small_category\":\"其他\",\"confidence\":0.5,\"evidence\":\"简要依据\"}]}"
    )
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {"classification_rules": categories, "items": items},
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": max(2048, settings.deepseek_max_tokens),
    }
    try:
        with httpx.Client(timeout=max(10, settings.deepseek_request_timeout_sec)) as client:
            response = client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
        decoded = json.loads(_strip_code_fence(content))
    except Exception:
        return {}

    allowed = {
        str(rule["small_category"]): str(rule["big_category"])
        for rule in rules
    }
    source_by_hash = {row["classification_hash"]: row for row in rows}
    result: dict[str, dict[str, Any]] = {}
    for item in decoded.get("items", []):
        key = str(item.get("id") or "")
        source = source_by_hash.get(key)
        if not source:
            continue
        small = str(item.get("small_category") or "其他").strip()
        big = str(item.get("big_category") or "其他").strip()
        if small not in allowed or allowed[small] != big or big not in BIG_CATEGORIES:
            big, small = "其他", "其他"
        result[key] = _cache_row(
            source,
            rule_version,
            big,
            small,
            item.get("after_reason_zh"),
            item.get("return_status_zh"),
            item.get("inventory_attributes_zh"),
            item.get("buyers_note_zh"),
            _confidence(item.get("confidence")),
            "deepseek",
            str(item.get("evidence") or "")[:1000],
            item,
        )
    return result


def _fallback(row: dict[str, Any], rule_version: str) -> dict[str, Any]:
    combined = " ".join(
        _normalize(row.get(key))
        for key in ("after_reason", "return_status", "inventory_attributes", "buyers_note")
    )
    big, small, confidence, evidence = "其他", "其他", 0.0, "无可靠判定依据"
    reason_code = _normalize(row.get("after_reason"))
    explicit_rule = DETERMINISTIC_REASON_RULES.get(reason_code)
    if explicit_rule:
        big, small = explicit_rule
        confidence = 0.98
        evidence = "Amazon退货原因枚举确定性规则"
    keyword_rules = (
        (("wrong item", "ordered-wrong", "no longer needed", "changed mind", "拒收"),
         "客户自身原因", "客户主观退换货"),
        (("not_as_described", "not as described", "description doesn't match",
          "description doesnt match", "description inaccurate", "inaccurate description",
          "beschreibung falsch", "nicht wie beschrieben", "different from pic",
          "与描述不符", "货描不符"), "不适配", "listing货描不符"),
        (("incompatible", "not_compatible", "part_not_compatible", "poor_fit", "poor fit",
          "apparel_too_small", "apparel_too_large", "not compatible", "not fit",
          "doesn't fit", "doesnt fit", "doesn’t fit", "wrong size", "incorrect size",
          "too small", "too large", "passt nicht", "nicht passend", "nicht kompatibel",
          "non compatibile", "non è compatibile", "pas compatible", "n'est pas compatible",
          "no es compatible", "no compatible", "incompatibilidad", "不适配", "不匹配"),
         "不适配", "产品不适配"),
        (("missing part", "缺少配件", "缺件"), "国内物流部", "产品缺少配件"),
        (("defective", "not work", "无法使用", "故障"), "产品质量问题", "产品无法使用"),
        (("damaged", "broken", "破损"), "供应商加强包装", "到货破损"),
        (("late", "delivery delay", "物流延迟"), "物流商问题", "物流延迟补偿"),
    )
    if not explicit_rule:
        for keywords, candidate_big, candidate_small in keyword_rules:
            if any(keyword in combined for keyword in keywords):
                big, small, confidence = candidate_big, candidate_small, 0.65
                evidence = "关键词规则匹配"
                break
    return _cache_row(
        row,
        rule_version,
        big,
        small,
        _translate_reason(row.get("after_reason")),
        _translate_fixed(row.get("return_status"), STATUS_TRANSLATIONS),
        _translate_fixed(row.get("inventory_attributes"), ATTRIBUTE_TRANSLATIONS),
        _translate_note(row.get("buyers_note")),
        confidence,
        "rule" if confidence else "fallback",
        evidence,
        {},
    )


def _cache_row(
    source: dict[str, Any],
    rule_version: str,
    big: str,
    small: str,
    reason_zh: Any,
    status_zh: Any,
    attributes_zh: Any,
    note_zh: Any,
    confidence: float,
    method: str,
    evidence: str,
    raw_response: Any,
) -> dict[str, Any]:
    return {
        "classification_hash": source["classification_hash"],
        "after_reason": _text(source.get("after_reason")),
        "return_status": _text(source.get("return_status")),
        "inventory_attributes": _text(source.get("inventory_attributes")),
        "buyers_note": _text(source.get("buyers_note")),
        "after_reason_zh": _text(reason_zh) or _translate_reason(source.get("after_reason")),
        "return_status_zh": _text(status_zh) or _translate_fixed(source.get("return_status"), STATUS_TRANSLATIONS),
        "inventory_attributes_zh": _text(attributes_zh) or _translate_fixed(source.get("inventory_attributes"), ATTRIBUTE_TRANSLATIONS),
        "buyers_note_zh": _text(note_zh) or _translate_note(source.get("buyers_note")),
        "big_category": big,
        "small_category": small,
        "confidence": confidence,
        "classify_method": method,
        "model_name": settings.deepseek_model if method == "deepseek" else None,
        "rule_version": rule_version,
        "evidence": evidence,
        "response_json": json.dumps(raw_response, ensure_ascii=False),
    }


def _translate_reason(value: Any) -> str:
    text = _text(value)
    key = text.lower().strip()
    return REASON_TRANSLATIONS.get(key, text)


def _translate_fixed(value: Any, mapping: dict[str, str]) -> str:
    text = _text(value)
    normalized = re.sub(r"[^a-z0-9_]", "", text.lower())
    return mapping.get(normalized, text)


def _translate_note(value: Any) -> str:
    text = _text(value)
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return BUYER_NOTE_TRANSLATIONS.get(normalized, text)


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except Exception:
        return 0.0


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value).lower()).strip()


def _limited(value: Any, limit: int = 1000) -> str:
    return _text(value)[:limit]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text
